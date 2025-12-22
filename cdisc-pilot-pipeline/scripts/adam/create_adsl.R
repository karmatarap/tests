#!/usr/bin/env Rscript
#' ============================================================================
#' ADSL - Subject Level Analysis Dataset
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Description: Creates ADSL from SDTM DM, DS, EX, SV domains
#'
#' Key Variables Derived:
#' - Treatment variables (TRT01P, TRT01A, TRT01PN, TRT01AN)
#' - Population flags (SAFFL, ITTFL, EFFFL)
#' - Treatment dates (TRTSDT, TRTEDT)
#' - Age groups (AGEGR1, AGEGR1N)
#' - Duration (TRTDURD)
#' ============================================================================

# Load required libraries
library(haven)
library(dplyr)
library(tidyr)
library(lubridate)
library(stringr)

# Get file paths from Snakemake
input_dm <- snakemake@input$dm
input_ds <- snakemake@input$ds
input_ex <- snakemake@input$ex
input_sv <- snakemake@input$sv
input_sc <- snakemake@input$sc
input_mh <- snakemake@input$mh
input_qs <- snakemake@input$qs
output_adsl <- snakemake@output$adsl
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("ADSL Creation Log\n")
cat("=================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load SDTM Domains
# ----------------------------------------------------------------------------
cat("Loading SDTM domains...\n")

dm <- read_xpt(input_dm)
ds <- read_xpt(input_ds)
ex <- read_xpt(input_ex)
sv <- read_xpt(input_sv)

cat(paste("  DM:", nrow(dm), "records\n"))
cat(paste("  DS:", nrow(ds), "records\n"))
cat(paste("  EX:", nrow(ex), "records\n"))
cat(paste("  SV:", nrow(sv), "records\n\n"))

# ----------------------------------------------------------------------------
# Helper function: Convert CDISC date to R Date
# ----------------------------------------------------------------------------
convert_dtc <- function(dtc) {
  # Handle partial dates - take first 10 characters (YYYY-MM-DD)
  date_str <- substr(dtc, 1, 10)
  as.Date(date_str, format = "%Y-%m-%d")
}

# ----------------------------------------------------------------------------
# Start with DM domain
# ----------------------------------------------------------------------------
cat("Creating base ADSL from DM...\n")

adsl <- dm %>%
  select(
    STUDYID, USUBJID, SUBJID, SITEID,
    AGE, AGEU, SEX, RACE, ETHNIC,
    ARM, ARMCD, ACTARM, ACTARMCD,
    COUNTRY, DMDTC, RFSTDTC, RFENDTC, RFXSTDTC, RFXENDTC
  ) %>%
  mutate(
    # Derive screening date
    SCRDT = convert_dtc(DMDTC),

    # Reference start/end dates
    RFSTDT = convert_dtc(RFSTDTC),
    RFENDT = convert_dtc(RFENDTC)
  )

# ----------------------------------------------------------------------------
# Derive Treatment Variables
# ----------------------------------------------------------------------------
cat("Deriving treatment variables...\n")

# Get first and last exposure dates from EX
ex_dates <- ex %>%
  filter(!is.na(EXSTDTC)) %>%
  group_by(STUDYID, USUBJID) %>%
  summarise(
    TRTSDT = min(convert_dtc(EXSTDTC), na.rm = TRUE),
    TRTEDT = max(convert_dtc(EXENDTC), na.rm = TRUE),
    .groups = "drop"
  )

adsl <- adsl %>%
  left_join(ex_dates, by = c("STUDYID", "USUBJID")) %>%
  mutate(
    # Planned treatment
    TRT01P = ARM,
    TRT01PN = case_when(
      ARM == "Placebo" ~ 0,
      ARM == "Xanomeline Low Dose" ~ 54,
      ARM == "Xanomeline High Dose" ~ 81,
      TRUE ~ NA_real_
    ),

    # Actual treatment (same as planned for this study)
    TRT01A = ACTARM,
    TRT01AN = case_when(
      ACTARM == "Placebo" ~ 0,
      ACTARM == "Xanomeline Low Dose" ~ 54,
      ACTARM == "Xanomeline High Dose" ~ 81,
      TRUE ~ NA_real_
    ),

    # Treatment duration
    TRTDURD = as.numeric(difftime(TRTEDT, TRTSDT, units = "days")) + 1
  )

# ----------------------------------------------------------------------------
# Derive Disposition Variables
# ----------------------------------------------------------------------------
cat("Deriving disposition variables...\n")

# Get disposition for completed/discontinued status
ds_disp <- ds %>%
  filter(DSCAT == "DISPOSITION EVENT") %>%
  group_by(STUDYID, USUBJID) %>%
  summarise(
    DCDECOD = first(DSDECOD),
    DCSREAS = first(DSTERM),
    .groups = "drop"
  )

adsl <- adsl %>%
  left_join(ds_disp, by = c("STUDYID", "USUBJID")) %>%
  mutate(
    DISCONFL = if_else(DCDECOD != "COMPLETED", "Y", ""),
    DSRAEFL = if_else(str_detect(toupper(DCSREAS), "ADVERSE"), "Y", "")
  )

# ----------------------------------------------------------------------------
# Derive Population Flags
# ----------------------------------------------------------------------------
cat("Deriving population flags...\n")

adsl <- adsl %>%
  mutate(
    # Randomized flag - all subjects in DM are randomized
    RANDFL = "Y",

    # ITT flag - all randomized
    ITTFL = "Y",

    # Safety flag - received at least one dose
    SAFFL = if_else(!is.na(TRTSDT), "Y", "N"),

    # Efficacy flag - ITT with baseline and post-baseline
    # Will refine based on actual efficacy data availability
    EFFFL = if_else(ITTFL == "Y" & !is.na(TRTSDT), "Y", "N")
  )

# ----------------------------------------------------------------------------
# Derive Age Group
# ----------------------------------------------------------------------------
cat("Deriving age groups...\n")

adsl <- adsl %>%
  mutate(
    AGEGR1 = case_when(
      AGE < 65 ~ "<65",
      AGE >= 65 & AGE < 80 ~ "65-80",
      AGE >= 80 ~ ">80",
      TRUE ~ NA_character_
    ),
    AGEGR1N = case_when(
      AGE < 65 ~ 1,
      AGE >= 65 & AGE < 80 ~ 2,
      AGE >= 80 ~ 3,
      TRUE ~ NA_real_
    )
  )

# ----------------------------------------------------------------------------
# Derive Site Grouping (for stratification)
# ----------------------------------------------------------------------------
cat("Deriving site grouping...\n")

# Create pooled site groups (sites with <3 subjects pooled)
site_counts <- adsl %>%
  count(SITEID) %>%
  mutate(
    SITEGR1 = if_else(n >= 3, SITEID, "900")
  )

adsl <- adsl %>%
  left_join(site_counts %>% select(SITEID, SITEGR1), by = "SITEID")

# ----------------------------------------------------------------------------
# Derive Baseline Characteristics from other domains
# ----------------------------------------------------------------------------
cat("Deriving baseline characteristics...\n")

# Baseline weight and height from VS would go here
# For now, using placeholder
adsl <- adsl %>%
  mutate(
    HEIGHTBL = NA_real_,
    WEIGHTBL = NA_real_,
    BMIBL = NA_real_
  )

# ----------------------------------------------------------------------------
# Derive Dates of Death (if applicable)
# ----------------------------------------------------------------------------
ds_death <- ds %>%
  filter(DSDECOD == "DEATH") %>%
  select(STUDYID, USUBJID, DSSTDTC) %>%
  mutate(DTHDT = convert_dtc(DSSTDTC))

adsl <- adsl %>%
  left_join(ds_death %>% select(STUDYID, USUBJID, DTHDT),
            by = c("STUDYID", "USUBJID")) %>%
  mutate(DTHFL = if_else(!is.na(DTHDT), "Y", ""))

# ----------------------------------------------------------------------------
# Set Variable Attributes
# ----------------------------------------------------------------------------
cat("Setting variable attributes...\n")

# Add labels
attr(adsl$STUDYID, "label") <- "Study Identifier"
attr(adsl$USUBJID, "label") <- "Unique Subject Identifier"
attr(adsl$SUBJID, "label") <- "Subject Identifier for the Study"
attr(adsl$SITEID, "label") <- "Study Site Identifier"
attr(adsl$AGE, "label") <- "Age"
attr(adsl$AGEU, "label") <- "Age Units"
attr(adsl$SEX, "label") <- "Sex"
attr(adsl$RACE, "label") <- "Race"
attr(adsl$ETHNIC, "label") <- "Ethnicity"
attr(adsl$ARM, "label") <- "Description of Planned Arm"
attr(adsl$TRT01P, "label") <- "Planned Treatment for Period 01"
attr(adsl$TRT01PN, "label") <- "Planned Treatment for Period 01 (N)"
attr(adsl$TRT01A, "label") <- "Actual Treatment for Period 01"
attr(adsl$TRT01AN, "label") <- "Actual Treatment for Period 01 (N)"
attr(adsl$TRTSDT, "label") <- "Date of First Exposure to Treatment"
attr(adsl$TRTEDT, "label") <- "Date of Last Exposure to Treatment"
attr(adsl$TRTDURD, "label") <- "Total Treatment Duration (Days)"
attr(adsl$SAFFL, "label") <- "Safety Population Flag"
attr(adsl$ITTFL, "label") <- "Intent-To-Treat Population Flag"
attr(adsl$EFFFL, "label") <- "Efficacy Population Flag"
attr(adsl$AGEGR1, "label") <- "Pooled Age Group 1"
attr(adsl$AGEGR1N, "label") <- "Pooled Age Group 1 (N)"
attr(adsl$SITEGR1, "label") <- "Pooled Site Group 1"
attr(adsl$DTHFL, "label") <- "Subject Death Flag"
attr(adsl$DTHDT, "label") <- "Date of Death"

# ----------------------------------------------------------------------------
# Select and order final variables
# ----------------------------------------------------------------------------
cat("Selecting final variables...\n")

adsl_final <- adsl %>%
  select(
    # Identifiers
    STUDYID, USUBJID, SUBJID, SITEID, SITEGR1,
    # Demographics
    AGE, AGEU, AGEGR1, AGEGR1N, SEX, RACE, ETHNIC,
    # Treatment
    ARM, ARMCD, ACTARM, ACTARMCD,
    TRT01P, TRT01PN, TRT01A, TRT01AN,
    TRTSDT, TRTEDT, TRTDURD,
    # Population flags
    RANDFL, ITTFL, SAFFL, EFFFL,
    # Disposition
    DCDECOD, DISCONFL, DSRAEFL,
    # Death
    DTHFL, DTHDT,
    # Dates
    RFSTDT, RFENDT
  )

# ----------------------------------------------------------------------------
# Export to XPT
# ----------------------------------------------------------------------------
cat("\nExporting ADSL...\n")

write_xpt(adsl_final, output_adsl, version = 5, name = "ADSL")

cat(paste("  Output:", nrow(adsl_final), "records\n"))
cat(paste("  File:", output_adsl, "\n"))

# Summary statistics
cat("\n=== Summary ===\n")
cat("Treatment Groups:\n")
print(table(adsl_final$TRT01P))
cat("\nPopulation Flags:\n")
cat(paste("  ITT:", sum(adsl_final$ITTFL == "Y"), "\n"))
cat(paste("  Safety:", sum(adsl_final$SAFFL == "Y"), "\n"))
cat(paste("  Efficacy:", sum(adsl_final$EFFFL == "Y"), "\n"))

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
