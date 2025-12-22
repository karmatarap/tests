#!/usr/bin/env Rscript
#' ============================================================================
#' ADQSADAS - ADAS-Cog Efficacy Analysis Dataset
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Description: Creates ADQSADAS from SDTM QS domain and ADSL
#'
#' PRIMARY ENDPOINT DATASET
#'
#' Key Variables Derived:
#' - ADAS-Cog(11) total score (ACTOT)
#' - Baseline value (BASE)
#' - Change from baseline (CHG)
#' - LOCF imputation for missing Week 24
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(lubridate)
library(stringr)

# Get file paths from Snakemake
input_qs <- snakemake@input$qs
input_adsl <- snakemake@input$adsl
input_sv <- snakemake@input$sv
output_adqsadas <- snakemake@output$adqsadas
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("ADQSADAS Creation Log - PRIMARY ENDPOINT\n")
cat("=========================================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Data
# ----------------------------------------------------------------------------
cat("Loading data...\n")

qs <- read_xpt(input_qs)
adsl <- read_xpt(input_adsl)
sv <- read_xpt(input_sv)

cat(paste("  QS:", nrow(qs), "records\n"))
cat(paste("  ADSL:", nrow(adsl), "records\n"))
cat(paste("  SV:", nrow(sv), "records\n\n"))

# Helper function
convert_dtc <- function(dtc) {
  date_str <- substr(dtc, 1, 10)
  as.Date(date_str, format = "%Y-%m-%d")
}

# ----------------------------------------------------------------------------
# Filter to ADAS-Cog Questionnaire
# ----------------------------------------------------------------------------
cat("Filtering to ADAS-Cog questionnaire...\n")

# ADAS-Cog items have QSCAT containing "ADAS"
qs_adas <- qs %>%
  filter(str_detect(QSCAT, "ADAS"))

cat(paste("  ADAS-Cog records:", nrow(qs_adas), "\n\n"))

# ----------------------------------------------------------------------------
# Merge ADSL Variables
# ----------------------------------------------------------------------------
cat("Merging ADSL variables...\n")

adsl_vars <- adsl %>%
  select(
    STUDYID, USUBJID, SITEID, SITEGR1,
    TRT01P, TRT01PN, TRT01A, TRT01AN,
    TRTSDT, TRTEDT, AGE, AGEGR1, SEX, RACE,
    SAFFL, ITTFL, EFFFL
  )

adqsadas <- qs_adas %>%
  left_join(adsl_vars, by = c("STUDYID", "USUBJID"))

# ----------------------------------------------------------------------------
# Create Parameter Variables
# ----------------------------------------------------------------------------
cat("Creating parameter variables...\n")

adqsadas <- adqsadas %>%
  mutate(
    # Individual items
    PARAM = QSTEST,
    PARAMCD = QSTESTCD,

    # Analysis value
    AVAL = as.numeric(QSSTRESN),
    AVALC = QSSTRESC,

    # Analysis date
    ADT = convert_dtc(QSDTC)
  )

# ----------------------------------------------------------------------------
# Derive Analysis Visit
# ----------------------------------------------------------------------------
cat("Deriving analysis visits...\n")

adqsadas <- adqsadas %>%
  mutate(
    AVISIT = VISIT,
    AVISITN = VISITNUM,

    # Analysis relative day
    ADY = as.numeric(difftime(ADT, TRTSDT, units = "days")) +
          if_else(ADT >= TRTSDT, 1, 0)
  )

# ----------------------------------------------------------------------------
# Calculate ADAS-Cog(11) Total Score
# ----------------------------------------------------------------------------
cat("Calculating ADAS-Cog(11) total score...\n")

# ADAS-Cog(11) items typically include specific items
# Sum the individual item scores for each subject/visit
actot <- adqsadas %>%
  filter(!is.na(AVAL)) %>%
  group_by(STUDYID, USUBJID, VISITNUM, VISIT, ADT, TRTSDT, TRTEDT,
           TRT01P, TRT01PN, TRT01A, TRT01AN,
           SITEID, SITEGR1, AGE, AGEGR1, SEX, RACE,
           SAFFL, ITTFL, EFFFL) %>%
  summarise(
    AVAL = sum(AVAL, na.rm = TRUE),
    n_items = n(),
    .groups = "drop"
  ) %>%
  mutate(
    PARAMCD = "ACTOT",
    PARAM = "ADAS-Cog(11) Total Score",
    AVISIT = VISIT,
    AVISITN = VISITNUM,
    ADY = as.numeric(difftime(ADT, TRTSDT, units = "days")) +
          if_else(ADT >= TRTSDT, 1, 0)
  )

cat(paste("  Total score records:", nrow(actot), "\n\n"))

# ----------------------------------------------------------------------------
# Derive Baseline
# ----------------------------------------------------------------------------
cat("Deriving baseline...\n")

# Baseline is at VISITNUM = 3
actot <- actot %>%
  mutate(
    ABLFL = case_when(
      VISITNUM == 3 & !is.na(AVAL) ~ "Y",
      TRUE ~ ""
    )
  )

# Get baseline values
baseline <- actot %>%
  filter(ABLFL == "Y") %>%
  select(STUDYID, USUBJID, BASE = AVAL) %>%
  distinct()

# Merge baseline
actot <- actot %>%
  left_join(baseline, by = c("STUDYID", "USUBJID"))

# ----------------------------------------------------------------------------
# Derive Change from Baseline
# ----------------------------------------------------------------------------
cat("Deriving change from baseline...\n")

actot <- actot %>%
  mutate(
    CHG = if_else(!is.na(AVAL) & !is.na(BASE), AVAL - BASE, NA_real_),
    PCHG = if_else(!is.na(CHG) & BASE != 0, (CHG / BASE) * 100, NA_real_)
  )

# ----------------------------------------------------------------------------
# Implement LOCF for Week 24
# ----------------------------------------------------------------------------
cat("Implementing LOCF for Week 24...\n")

# Get last observation for each subject
locf_data <- actot %>%
  filter(!is.na(AVAL) & AVISITN >= 3) %>%
  group_by(STUDYID, USUBJID) %>%
  slice_max(AVISITN) %>%
  ungroup() %>%
  filter(AVISITN < 11)  # Only for subjects missing Week 24

# Create LOCF records for Week 24
# Check who has Week 24
has_wk24 <- actot %>%
  filter(AVISITN == 11) %>%
  select(USUBJID) %>%
  distinct()

needs_locf <- locf_data %>%
  anti_join(has_wk24, by = "USUBJID") %>%
  mutate(
    AVISIT = "WEEK 24",
    AVISITN = 11,
    VISIT = "WEEK 24",
    VISITNUM = 11,
    LOCF = "Y",
    # Keep original AVAL, recalculate CHG
    CHG = AVAL - BASE
  )

# Combine with main data
actot <- actot %>%
  mutate(LOCF = "") %>%
  bind_rows(needs_locf)

cat(paste("  LOCF records created:", nrow(needs_locf), "\n\n"))

# ----------------------------------------------------------------------------
# Derive Analysis Flags
# ----------------------------------------------------------------------------
cat("Deriving analysis flags...\n")

actot <- actot %>%
  mutate(
    # Primary analysis flag: Week 24 efficacy population
    ANL01FL = case_when(
      EFFFL == "Y" & AVISITN == 11 ~ "Y",
      TRUE ~ ""
    )
  )

# ----------------------------------------------------------------------------
# Set Variable Attributes
# ----------------------------------------------------------------------------
cat("Setting variable attributes...\n")

attr(actot$STUDYID, "label") <- "Study Identifier"
attr(actot$USUBJID, "label") <- "Unique Subject Identifier"
attr(actot$PARAM, "label") <- "Parameter"
attr(actot$PARAMCD, "label") <- "Parameter Code"
attr(actot$AVAL, "label") <- "Analysis Value"
attr(actot$BASE, "label") <- "Baseline Value"
attr(actot$CHG, "label") <- "Change from Baseline"
attr(actot$ABLFL, "label") <- "Baseline Record Flag"
attr(actot$AVISIT, "label") <- "Analysis Visit"
attr(actot$AVISITN, "label") <- "Analysis Visit (N)"
attr(actot$ANL01FL, "label") <- "Analysis Flag 01 - Primary Efficacy"
attr(actot$LOCF, "label") <- "LOCF Flag"

# ----------------------------------------------------------------------------
# Select and order final variables
# ----------------------------------------------------------------------------
cat("Selecting final variables...\n")

adqsadas_final <- actot %>%
  select(
    # Identifiers
    STUDYID, USUBJID, SITEID, SITEGR1,
    # ADSL variables
    TRT01P, TRT01PN, TRT01A, TRT01AN,
    TRTSDT, TRTEDT, AGE, AGEGR1, SEX, RACE,
    SAFFL, ITTFL, EFFFL,
    # Parameter
    PARAM, PARAMCD,
    # Visit
    AVISIT, AVISITN,
    # Dates
    ADT, ADY,
    # Values
    AVAL, BASE, CHG, PCHG,
    # Flags
    ABLFL, ANL01FL, LOCF
  ) %>%
  arrange(USUBJID, AVISITN)

# ----------------------------------------------------------------------------
# Export to XPT
# ----------------------------------------------------------------------------
cat("\nExporting ADQSADAS...\n")

write_xpt(adqsadas_final, output_adqsadas, version = 5, name = "ADQSADAS")

cat(paste("  Output:", nrow(adqsadas_final), "records\n"))
cat(paste("  File:", output_adqsadas, "\n"))

# Summary statistics
cat("\n=== Summary ===\n")
cat("\nTreatment Groups at Week 24:\n")
wk24_summary <- adqsadas_final %>%
  filter(AVISITN == 11 & !is.na(CHG)) %>%
  group_by(TRT01P) %>%
  summarise(
    N = n(),
    Mean_CHG = mean(CHG, na.rm = TRUE),
    SD_CHG = sd(CHG, na.rm = TRUE),
    .groups = "drop"
  )
print(wk24_summary)

cat(paste("\nPrimary analysis records (ANL01FL='Y'):", sum(adqsadas_final$ANL01FL == "Y"), "\n"))
cat(paste("LOCF records:", sum(adqsadas_final$LOCF == "Y"), "\n"))

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
