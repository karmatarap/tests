#!/usr/bin/env Rscript
#' ============================================================================
#' ADAE - Adverse Events Analysis Dataset
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Description: Creates ADAE from SDTM AE domain and ADSL
#'
#' Key Variables Derived:
#' - Treatment-emergent flag (TRTEMFL)
#' - AE start/end dates (ASTDT, AENDT)
#' - Duration (AEDUR)
#' - Severity (ASEV, ASEVN)
#' - Relatedness (AREL, ARELN)
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(lubridate)
library(stringr)

# Get file paths from Snakemake
input_ae <- snakemake@input$ae
input_adsl <- snakemake@input$adsl
input_ex <- snakemake@input$ex
output_adae <- snakemake@output$adae
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("ADAE Creation Log\n")
cat("=================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Data
# ----------------------------------------------------------------------------
cat("Loading data...\n")

ae <- read_xpt(input_ae)
adsl <- read_xpt(input_adsl)
ex <- read_xpt(input_ex)

cat(paste("  AE:", nrow(ae), "records\n"))
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

adae <- ae %>%
  left_join(adsl_vars, by = c("STUDYID", "USUBJID"))

# ----------------------------------------------------------------------------
# Derive AE Dates
# ----------------------------------------------------------------------------
cat("Deriving AE dates...\n")

adae <- adae %>%
  mutate(
    # Start date
    ASTDT = convert_dtc(AESTDTC),
    ASTDTF = case_when(
      nchar(AESTDTC) < 10 ~ "D",
      TRUE ~ NA_character_
    ),

    # End date
    AENDT = convert_dtc(AEENDTC),
    AENDTF = case_when(
      nchar(AEENDTC) < 10 ~ "D",
      TRUE ~ NA_character_
    ),

    # Duration
    AEDUR = as.numeric(difftime(AENDT, ASTDT, units = "days")) + 1
  )

# ----------------------------------------------------------------------------
# Derive Treatment-Emergent Flag
# ----------------------------------------------------------------------------
cat("Deriving treatment-emergent flag...\n")

adae <- adae %>%
  mutate(
    # Treatment-emergent: started on or after first dose
    TRTEMFL = case_when(
      !is.na(ASTDT) & !is.na(TRTSDT) & ASTDT >= TRTSDT ~ "Y",
      TRUE ~ "N"
    ),

    # Pre-treatment flag
    PREFL = case_when(
      !is.na(ASTDT) & !is.na(TRTSDT) & ASTDT < TRTSDT ~ "Y",
      TRUE ~ "N"
    )
  )

# ----------------------------------------------------------------------------
# Derive Severity Variables
# ----------------------------------------------------------------------------
cat("Deriving severity variables...\n")

adae <- adae %>%
  mutate(
    # Analysis severity
    ASEV = AESEV,
    ASEVN = case_when(
      AESEV == "MILD" ~ 1,
      AESEV == "MODERATE" ~ 2,
      AESEV == "SEVERE" ~ 3,
      TRUE ~ NA_real_
    )
  )

# ----------------------------------------------------------------------------
# Derive Relatedness Variables
# ----------------------------------------------------------------------------
cat("Deriving relatedness variables...\n")

adae <- adae %>%
  mutate(
    # Analysis relatedness
    AREL = AEREL,
    ARELN = case_when(
      AEREL %in% c("DEFINITELY RELATED", "PROBABLY RELATED", "POSSIBLY RELATED") ~ 1,
      AEREL %in% c("UNLIKELY RELATED", "NOT RELATED") ~ 0,
      TRUE ~ NA_real_
    ),

    # Related flag
    RELFL = if_else(ARELN == 1, "Y", "N")
  )

# ----------------------------------------------------------------------------
# Derive Outcome Variables
# ----------------------------------------------------------------------------
cat("Deriving outcome variables...\n")

adae <- adae %>%
  mutate(
    # Analysis outcome
    AOUT = AEOUT,
    AOUTN = case_when(
      AEOUT == "RECOVERED/RESOLVED" ~ 1,
      AEOUT == "RECOVERING/RESOLVING" ~ 2,
      AEOUT == "NOT RECOVERED/NOT RESOLVED" ~ 3,
      AEOUT == "RECOVERED/RESOLVED WITH SEQUELAE" ~ 4,
      AEOUT == "FATAL" ~ 5,
      AEOUT == "UNKNOWN" ~ 6,
      TRUE ~ NA_real_
    )
  )

# ----------------------------------------------------------------------------
# Derive Action Taken Variables
# ----------------------------------------------------------------------------
cat("Deriving action taken variables...\n")

adae <- adae %>%
  mutate(
    AACT = AEACN,
    AACTN = case_when(
      AEACN == "DRUG WITHDRAWN" ~ 1,
      AEACN == "DRUG INTERRUPTED" ~ 2,
      AEACN == "DOSE REDUCED" ~ 3,
      AEACN == "DOSE INCREASED" ~ 4,
      AEACN == "DOSE NOT CHANGED" ~ 5,
      AEACN == "NOT APPLICABLE" ~ 6,
      AEACN == "UNKNOWN" ~ 7,
      TRUE ~ NA_real_
    )
  )

# ----------------------------------------------------------------------------
# Derive Flags
# ----------------------------------------------------------------------------
cat("Deriving analysis flags...\n")

adae <- adae %>%
  mutate(
    # Serious AE flag
    AESER = if_else(is.na(AESER), "N", AESER),
    SERFL = AESER,

    # Caused death flag
    DTHFL = if_else(AEOUT == "FATAL", "Y", "N"),

    # Caused discontinuation flag
    DCSFL = if_else(AEACN == "DRUG WITHDRAWN", "Y", "N"),

    # Caused dose modification flag
    DOSMODFL = if_else(AEACN %in% c("DOSE REDUCED", "DOSE INCREASED", "DRUG INTERRUPTED"), "Y", "N")
  )

# ----------------------------------------------------------------------------
# Set Variable Attributes
# ----------------------------------------------------------------------------
cat("Setting variable attributes...\n")

attr(adae$STUDYID, "label") <- "Study Identifier"
attr(adae$USUBJID, "label") <- "Unique Subject Identifier"
attr(adae$AETERM, "label") <- "Reported Term for the Adverse Event"
attr(adae$AEDECOD, "label") <- "Dictionary-Derived Term"
attr(adae$AEBODSYS, "label") <- "Body System or Organ Class"
attr(adae$ASTDT, "label") <- "Analysis Start Date"
attr(adae$AENDT, "label") <- "Analysis End Date"
attr(adae$AEDUR, "label") <- "AE Duration (Days)"
attr(adae$TRTEMFL, "label") <- "Treatment Emergent Analysis Flag"
attr(adae$ASEV, "label") <- "Analysis Severity"
attr(adae$ASEVN, "label") <- "Analysis Severity (N)"
attr(adae$AREL, "label") <- "Analysis Relatedness"
attr(adae$ARELN, "label") <- "Analysis Relatedness (N)"
attr(adae$SERFL, "label") <- "Serious Event Flag"
attr(adae$DTHFL, "label") <- "AE Resulted in Death"
attr(adae$DCSFL, "label") <- "AE Led to Drug Discontinuation"

# ----------------------------------------------------------------------------
# Select and order final variables
# ----------------------------------------------------------------------------
cat("Selecting final variables...\n")

adae_final <- adae %>%
  select(
    # Identifiers
    STUDYID, USUBJID, SITEID, AESEQ,
    # ADSL variables
    TRT01P, TRT01PN, TRT01A, TRT01AN,
    TRTSDT, TRTEDT, AGE, AGEGR1, SEX, RACE,
    SAFFL,
    # AE variables
    AETERM, AEDECOD, AEBODSYS, AESOC,
    AESTDTC, AEENDTC, ASTDT, AENDT, ASTDTF, AENDTF,
    AEDUR,
    # Analysis variables
    TRTEMFL, PREFL,
    AESEV, ASEV, ASEVN,
    AEREL, AREL, ARELN, RELFL,
    AESER, SERFL,
    AEOUT, AOUT, AOUTN,
    AEACN, AACT, AACTN,
    DTHFL, DCSFL, DOSMODFL
  )

# ----------------------------------------------------------------------------
# Export to XPT
# ----------------------------------------------------------------------------
cat("\nExporting ADAE...\n")

write_xpt(adae_final, output_adae, version = 5, name = "ADAE")

cat(paste("  Output:", nrow(adae_final), "records\n"))
cat(paste("  File:", output_adae, "\n"))

# Summary statistics
cat("\n=== Summary ===\n")
cat(paste("Treatment-Emergent AEs:", sum(adae_final$TRTEMFL == "Y"), "\n"))
cat(paste("Serious AEs:", sum(adae_final$SERFL == "Y"), "\n"))
cat(paste("Related AEs:", sum(adae_final$RELFL == "Y", na.rm = TRUE), "\n"))

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
