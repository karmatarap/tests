#!/usr/bin/env Rscript
#' ============================================================================
#' ADLBH - Laboratory Hematology Analysis Dataset
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Description: Creates ADLBH from SDTM LB domain (hematology tests) and ADSL
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(lubridate)
library(stringr)

# Get file paths from Snakemake
input_lb <- snakemake@input$lb
input_adsl <- snakemake@input$adsl
output_adlbh <- snakemake@output$adlbh
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("ADLBH Creation Log\n")
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
# Filter to Hematology Tests Only
# ----------------------------------------------------------------------------
cat("Filtering to hematology tests...\n")

lb_hema <- lb %>%
  filter(LBCAT == "HEMATOLOGY")

cat(paste("  Hematology records:", nrow(lb_hema), "\n\n"))

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

adlbh <- lb_hema %>%
  left_join(adsl_vars, by = c("STUDYID", "USUBJID"))

# ----------------------------------------------------------------------------
# Create Parameter Variables
# ----------------------------------------------------------------------------
cat("Creating parameter variables...\n")

adlbh <- adlbh %>%
  mutate(
    PARAM = paste(LBTEST, "(", LBORRESU, ")"),
    PARAMCD = LBTESTCD,
    PARCAT1 = LBCAT
  )

# ----------------------------------------------------------------------------
# Derive Analysis Value
# ----------------------------------------------------------------------------
cat("Deriving analysis values...\n")

adlbh <- adlbh %>%
  mutate(
    AVAL = as.numeric(LBSTRESN),
    AVALC = LBSTRESC,
    ADT = convert_dtc(LBDTC),
    ADY = as.numeric(difftime(ADT, TRTSDT, units = "days")) +
          if_else(ADT >= TRTSDT, 1, 0)
  )

# ----------------------------------------------------------------------------
# Derive Analysis Visit
# ----------------------------------------------------------------------------
cat("Deriving analysis visits...\n")

adlbh <- adlbh %>%
  mutate(
    AVISIT = VISIT,
    AVISITN = VISITNUM
  )

# ----------------------------------------------------------------------------
# Derive Reference Ranges
# ----------------------------------------------------------------------------
cat("Deriving reference ranges...\n")

adlbh <- adlbh %>%
  mutate(
    ANRLO = as.numeric(LBSTNRLO),
    ANRHI = as.numeric(LBSTNRHI),
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

adlbh <- adlbh %>%
  mutate(
    ABLFL = case_when(
      VISITNUM == 3 & !is.na(AVAL) ~ "Y",
      TRUE ~ ""
    )
  )

baseline <- adlbh %>%
  filter(ABLFL == "Y") %>%
  select(STUDYID, USUBJID, PARAMCD, BASE = AVAL, BNRIND = ANRIND) %>%
  distinct()

adlbh <- adlbh %>%
  left_join(baseline, by = c("STUDYID", "USUBJID", "PARAMCD"))

# ----------------------------------------------------------------------------
# Derive Change from Baseline
# ----------------------------------------------------------------------------
cat("Deriving change from baseline...\n")

adlbh <- adlbh %>%
  mutate(
    CHG = if_else(!is.na(AVAL) & !is.na(BASE), AVAL - BASE, NA_real_),
    PCHG = if_else(!is.na(CHG) & BASE != 0, (CHG / BASE) * 100, NA_real_),
    SHIFT1 = case_when(
      !is.na(BNRIND) & !is.na(ANRIND) ~ paste(BNRIND, "to", ANRIND),
      TRUE ~ NA_character_
    ),
    ANL01FL = if_else(AVISITN >= 3, "Y", "")
  )

# ----------------------------------------------------------------------------
# Select and order final variables
# ----------------------------------------------------------------------------
cat("Selecting final variables...\n")

adlbh_final <- adlbh %>%
  select(
    STUDYID, USUBJID, SITEID,
    TRT01P, TRT01PN, TRT01A, TRT01AN,
    TRTSDT, TRTEDT, AGE, AGEGR1, SEX, RACE,
    SAFFL,
    PARAM, PARAMCD, PARCAT1,
    AVISIT, AVISITN, VISIT, VISITNUM,
    ADT, ADY,
    AVAL, AVALC, BASE, CHG, PCHG,
    ANRLO, ANRHI, ANRIND, BNRIND, SHIFT1,
    ABLFL, ANL01FL,
    LBSEQ
  )

# ----------------------------------------------------------------------------
# Export to XPT
# ----------------------------------------------------------------------------
cat("\nExporting ADLBH...\n")

write_xpt(adlbh_final, output_adlbh, version = 5, name = "ADLBH")

cat(paste("  Output:", nrow(adlbh_final), "records\n"))
cat(paste("  File:", output_adlbh, "\n"))

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
