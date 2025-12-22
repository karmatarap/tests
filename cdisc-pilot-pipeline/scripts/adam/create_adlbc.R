#!/usr/bin/env Rscript
#' ============================================================================
#' ADLBC - Laboratory Chemistry Analysis Dataset
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Description: Creates ADLBC from SDTM LB domain (chemistry tests) and ADSL
#'
#' Key Variables Derived:
#' - Baseline flag (ABLFL)
#' - Baseline value (BASE)
#' - Change from baseline (CHG)
#' - Reference range flags (ANRLO, ANRHI, ANRIND)
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(lubridate)
library(stringr)

# Get file paths from Snakemake
input_lb <- snakemake@input$lb
input_adsl <- snakemake@input$adsl
output_adlbc <- snakemake@output$adlbc
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("ADLBC Creation Log\n")
cat("==================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Data
# ----------------------------------------------------------------------------
cat("Loading data...\n")

lb <- read_xpt(input_lb)
adsl <- read_xpt(input_adsl)

cat(paste("  LB:", nrow(lb), "records\n"))
cat(paste("  ADSL:", nrow(adsl), "records\n\n"))

# Helper function
convert_dtc <- function(dtc) {
  date_str <- substr(dtc, 1, 10)
  as.Date(date_str, format = "%Y-%m-%d")
}

# ----------------------------------------------------------------------------
# Filter to Chemistry Tests Only
# ----------------------------------------------------------------------------
cat("Filtering to chemistry tests...\n")

# Chemistry category
lb_chem <- lb %>%
  filter(LBCAT == "CHEMISTRY")

cat(paste("  Chemistry records:", nrow(lb_chem), "\n\n"))

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

adlbc <- lb_chem %>%
  left_join(adsl_vars, by = c("STUDYID", "USUBJID"))

# ----------------------------------------------------------------------------
# Create Parameter Variables
# ----------------------------------------------------------------------------
cat("Creating parameter variables...\n")

adlbc <- adlbc %>%
  mutate(
    PARAM = paste(LBTEST, "(", LBORRESU, ")"),
    PARAMCD = LBTESTCD,
    PARCAT1 = LBCAT
  )

# ----------------------------------------------------------------------------
# Derive Analysis Value
# ----------------------------------------------------------------------------
cat("Deriving analysis values...\n")

adlbc <- adlbc %>%
  mutate(
    AVAL = as.numeric(LBSTRESN),
    AVALC = LBSTRESC,

    # Analysis date
    ADT = convert_dtc(LBDTC),
    ADY = as.numeric(difftime(ADT, TRTSDT, units = "days")) +
          if_else(ADT >= TRTSDT, 1, 0)
  )

# ----------------------------------------------------------------------------
# Derive Analysis Visit
# ----------------------------------------------------------------------------
cat("Deriving analysis visits...\n")

adlbc <- adlbc %>%
  mutate(
    AVISIT = VISIT,
    AVISITN = VISITNUM
  )

# ----------------------------------------------------------------------------
# Derive Reference Ranges
# ----------------------------------------------------------------------------
cat("Deriving reference ranges...\n")

adlbc <- adlbc %>%
  mutate(
    ANRLO = as.numeric(LBSTNRLO),
    ANRHI = as.numeric(LBSTNRHI),

    # Reference range indicator
    ANRIND = case_when(
      !is.na(AVAL) & !is.na(ANRLO) & AVAL < ANRLO ~ "LOW",
      !is.na(AVAL) & !is.na(ANRHI) & AVAL > ANRHI ~ "HIGH",
      !is.na(AVAL) & !is.na(ANRLO) & !is.na(ANRHI) ~ "NORMAL",
      TRUE ~ NA_character_
    )
  )

# ----------------------------------------------------------------------------
# Derive Baseline
# ----------------------------------------------------------------------------
cat("Deriving baseline...\n")

# Baseline is at VISITNUM = 3 (BASELINE visit)
adlbc <- adlbc %>%
  mutate(
    ABLFL = case_when(
      VISITNUM == 3 & !is.na(AVAL) ~ "Y",
      TRUE ~ ""
    )
  )

# Get baseline values
baseline <- adlbc %>%
  filter(ABLFL == "Y") %>%
  select(STUDYID, USUBJID, PARAMCD, BASE = AVAL, BNRIND = ANRIND) %>%
  distinct()

# Merge baseline
adlbc <- adlbc %>%
  left_join(baseline, by = c("STUDYID", "USUBJID", "PARAMCD"))

# ----------------------------------------------------------------------------
# Derive Change from Baseline
# ----------------------------------------------------------------------------
cat("Deriving change from baseline...\n")

adlbc <- adlbc %>%
  mutate(
    CHG = if_else(!is.na(AVAL) & !is.na(BASE), AVAL - BASE, NA_real_),
    PCHG = if_else(!is.na(CHG) & BASE != 0, (CHG / BASE) * 100, NA_real_)
  )

# ----------------------------------------------------------------------------
# Derive Shift Variables
# ----------------------------------------------------------------------------
cat("Deriving shift variables...\n")

adlbc <- adlbc %>%
  mutate(
    # Shift from baseline
    SHIFT1 = case_when(
      !is.na(BNRIND) & !is.na(ANRIND) ~ paste(BNRIND, "to", ANRIND),
      TRUE ~ NA_character_
    )
  )

# ----------------------------------------------------------------------------
# Derive Analysis Flags
# ----------------------------------------------------------------------------
cat("Deriving analysis flags...\n")

adlbc <- adlbc %>%
  mutate(
    ANL01FL = if_else(AVISITN >= 3, "Y", "")
  )

# ----------------------------------------------------------------------------
# Set Variable Attributes
# ----------------------------------------------------------------------------
cat("Setting variable attributes...\n")

attr(adlbc$STUDYID, "label") <- "Study Identifier"
attr(adlbc$USUBJID, "label") <- "Unique Subject Identifier"
attr(adlbc$PARAM, "label") <- "Parameter"
attr(adlbc$PARAMCD, "label") <- "Parameter Code"
attr(adlbc$PARCAT1, "label") <- "Parameter Category 1"
attr(adlbc$AVAL, "label") <- "Analysis Value"
attr(adlbc$BASE, "label") <- "Baseline Value"
attr(adlbc$CHG, "label") <- "Change from Baseline"
attr(adlbc$ANRLO, "label") <- "Analysis Normal Range Lower Limit"
attr(adlbc$ANRHI, "label") <- "Analysis Normal Range Upper Limit"
attr(adlbc$ANRIND, "label") <- "Analysis Reference Range Indicator"
attr(adlbc$BNRIND, "label") <- "Baseline Reference Range Indicator"
attr(adlbc$ABLFL, "label") <- "Baseline Record Flag"
attr(adlbc$AVISIT, "label") <- "Analysis Visit"
attr(adlbc$AVISITN, "label") <- "Analysis Visit (N)"

# ----------------------------------------------------------------------------
# Select and order final variables
# ----------------------------------------------------------------------------
cat("Selecting final variables...\n")

adlbc_final <- adlbc %>%
  select(
    # Identifiers
    STUDYID, USUBJID, SITEID,
    # ADSL variables
    TRT01P, TRT01PN, TRT01A, TRT01AN,
    TRTSDT, TRTEDT, AGE, AGEGR1, SEX, RACE,
    SAFFL,
    # Parameter
    PARAM, PARAMCD, PARCAT1,
    # Visit
    AVISIT, AVISITN, VISIT, VISITNUM,
    # Dates
    ADT, ADY,
    # Values
    AVAL, AVALC, BASE, CHG, PCHG,
    # Reference ranges
    ANRLO, ANRHI, ANRIND, BNRIND, SHIFT1,
    # Flags
    ABLFL, ANL01FL,
    # Original LB variables
    LBSEQ
  )

# ----------------------------------------------------------------------------
# Export to XPT
# ----------------------------------------------------------------------------
cat("\nExporting ADLBC...\n")

write_xpt(adlbc_final, output_adlbc, version = 5, name = "ADLBC")

cat(paste("  Output:", nrow(adlbc_final), "records\n"))
cat(paste("  File:", output_adlbc, "\n"))

# Summary statistics
cat("\n=== Summary ===\n")
cat(paste("Unique parameters:", n_distinct(adlbc_final$PARAMCD), "\n"))
cat(paste("Baseline records:", sum(adlbc_final$ABLFL == "Y"), "\n"))

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
