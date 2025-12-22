#!/usr/bin/env Rscript
#' ============================================================================
#' ADVS - Vital Signs Analysis Dataset
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Description: Creates ADVS from SDTM VS domain and ADSL
#'
#' Key Variables Derived:
#' - Baseline flag (ABLFL)
#' - Baseline value (BASE)
#' - Change from baseline (CHG)
#' - Percent change (PCHG)
#' - Analysis visit (AVISIT, AVISITN)
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(lubridate)
library(stringr)

# Get file paths from Snakemake
input_vs <- snakemake@input$vs
input_adsl <- snakemake@input$adsl
output_advs <- snakemake@output$advs
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("ADVS Creation Log\n")
cat("=================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Data
# ----------------------------------------------------------------------------
cat("Loading data...\n")

vs <- read_xpt(input_vs)
adsl <- read_xpt(input_adsl)

cat(paste("  VS:", nrow(vs), "records\n"))
cat(paste("  ADSL:", nrow(adsl), "records\n\n"))

# Helper function
convert_dtc <- function(dtc) {
  date_str <- substr(dtc, 1, 10)
  as.Date(date_str, format = "%Y-%m-%d")
}

# ----------------------------------------------------------------------------
# Merge ADSL Variables
# ----------------------------------------------------------------------------
cat("Merging ADSL variables...\n")

adsl_vars <- adsl %>%
  select(
    STUDYID, USUBJID, SITEID,
    TRT01P, TRT01PN, TRT01A, TRT01AN,
    TRTSDT, TRTEDT, AGE, AGEGR1, SEX, RACE,
    SAFFL, ITTFL
  )

advs <- vs %>%
  left_join(adsl_vars, by = c("STUDYID", "USUBJID"))

# ----------------------------------------------------------------------------
# Create Parameter Variables
# ----------------------------------------------------------------------------
cat("Creating parameter variables...\n")

advs <- advs %>%
  mutate(
    PARAM = paste(VSTEST, "(", VSORRESU, ")"),
    PARAMCD = VSTESTCD,
    PARAMN = case_when(
      VSTESTCD == "SYSBP" ~ 1,
      VSTESTCD == "DIABP" ~ 2,
      VSTESTCD == "PULSE" ~ 3,
      VSTESTCD == "RESP" ~ 4,
      VSTESTCD == "TEMP" ~ 5,
      VSTESTCD == "HEIGHT" ~ 6,
      VSTESTCD == "WEIGHT" ~ 7,
      TRUE ~ NA_real_
    )
  )

# ----------------------------------------------------------------------------
# Derive Analysis Value
# ----------------------------------------------------------------------------
cat("Deriving analysis values...\n")

advs <- advs %>%
  mutate(
    AVAL = as.numeric(VSSTRESN),
    AVALC = VSSTRESC,

    # Analysis date
    ADT = convert_dtc(VSDTC),
    ADY = as.numeric(difftime(ADT, TRTSDT, units = "days")) +
          if_else(ADT >= TRTSDT, 1, 0)
  )

# ----------------------------------------------------------------------------
# Derive Analysis Visit
# ----------------------------------------------------------------------------
cat("Deriving analysis visits...\n")

advs <- advs %>%
  mutate(
    AVISIT = VISIT,
    AVISITN = VISITNUM,

    # Timepoint
    ATPT = VSTPT,
    ATPTN = VSTPTNUM
  )

# ----------------------------------------------------------------------------
# Derive Baseline
# ----------------------------------------------------------------------------
cat("Deriving baseline...\n")

# Baseline is typically the last non-missing value before first dose
# For this study, baseline is at VISITNUM = 3 (BASELINE visit)
advs <- advs %>%
  mutate(
    # Baseline flag
    ABLFL = case_when(
      VISITNUM == 3 & !is.na(AVAL) ~ "Y",
      TRUE ~ ""
    )
  )

# Get baseline values
baseline <- advs %>%
  filter(ABLFL == "Y") %>%
  select(STUDYID, USUBJID, PARAMCD, ATPTN, BASE = AVAL) %>%
  distinct()

# Merge baseline
advs <- advs %>%
  left_join(baseline, by = c("STUDYID", "USUBJID", "PARAMCD", "ATPTN"))

# ----------------------------------------------------------------------------
# Derive Change from Baseline
# ----------------------------------------------------------------------------
cat("Deriving change from baseline...\n")

advs <- advs %>%
  mutate(
    CHG = if_else(!is.na(AVAL) & !is.na(BASE), AVAL - BASE, NA_real_),
    PCHG = if_else(!is.na(CHG) & BASE != 0, (CHG / BASE) * 100, NA_real_)
  )

# ----------------------------------------------------------------------------
# Derive Analysis Flags
# ----------------------------------------------------------------------------
cat("Deriving analysis flags...\n")

advs <- advs %>%
  mutate(
    # Analysis record flag (exclude screening)
    ANL01FL = if_else(AVISITN >= 3, "Y", ""),

    # Last observation carried forward flag (for main parameters)
    LOCF = ""  # Will implement LOCF logic if needed
  )

# ----------------------------------------------------------------------------
# Set Variable Attributes
# ----------------------------------------------------------------------------
cat("Setting variable attributes...\n")

attr(advs$STUDYID, "label") <- "Study Identifier"
attr(advs$USUBJID, "label") <- "Unique Subject Identifier"
attr(advs$PARAM, "label") <- "Parameter"
attr(advs$PARAMCD, "label") <- "Parameter Code"
attr(advs$PARAMN, "label") <- "Parameter (N)"
attr(advs$AVAL, "label") <- "Analysis Value"
attr(advs$BASE, "label") <- "Baseline Value"
attr(advs$CHG, "label") <- "Change from Baseline"
attr(advs$PCHG, "label") <- "Percent Change from Baseline"
attr(advs$ABLFL, "label") <- "Baseline Record Flag"
attr(advs$AVISIT, "label") <- "Analysis Visit"
attr(advs$AVISITN, "label") <- "Analysis Visit (N)"
attr(advs$ADT, "label") <- "Analysis Date"
attr(advs$ADY, "label") <- "Analysis Relative Day"
attr(advs$ANL01FL, "label") <- "Analysis Flag 01"

# ----------------------------------------------------------------------------
# Select and order final variables
# ----------------------------------------------------------------------------
cat("Selecting final variables...\n")

advs_final <- advs %>%
  select(
    # Identifiers
    STUDYID, USUBJID, SITEID,
    # ADSL variables
    TRT01P, TRT01PN, TRT01A, TRT01AN,
    TRTSDT, TRTEDT, AGE, AGEGR1, SEX, RACE,
    SAFFL,
    # Parameter
    PARAM, PARAMCD, PARAMN,
    # Visit
    AVISIT, AVISITN, VISIT, VISITNUM,
    ATPT, ATPTN,
    # Dates
    ADT, ADY,
    # Values
    AVAL, AVALC, BASE, CHG, PCHG,
    # Flags
    ABLFL, ANL01FL,
    # Original VS variables
    VSSEQ
  )

# ----------------------------------------------------------------------------
# Export to XPT
# ----------------------------------------------------------------------------
cat("\nExporting ADVS...\n")

write_xpt(advs_final, output_advs, version = 5, name = "ADVS")

cat(paste("  Output:", nrow(advs_final), "records\n"))
cat(paste("  File:", output_advs, "\n"))

# Summary statistics
cat("\n=== Summary ===\n")
cat("Parameters:\n")
print(table(advs_final$PARAMCD))
cat("\nBaseline records:", sum(advs_final$ABLFL == "Y"), "\n")

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
