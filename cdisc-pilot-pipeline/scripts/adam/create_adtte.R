#!/usr/bin/env Rscript
#' ============================================================================
#' ADTTE - Time to Event Analysis Dataset
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Description: Creates ADTTE from ADAE and ADSL
#'
#' Key Variables Derived:
#' - Time to first dermatologic adverse event (TTDERM)
#' - Time to first serious AE (TTSAE)
#' - Time to discontinuation (TTDISC)
#' - Censoring indicators
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(lubridate)
library(stringr)

# Get file paths from Snakemake
input_adae <- snakemake@input$adae
input_adsl <- snakemake@input$adsl
output_adtte <- snakemake@output$adtte
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("ADTTE Creation Log\n")
cat("==================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Data
# ----------------------------------------------------------------------------
cat("Loading data...\n")

adae <- read_xpt(input_adae)
adsl <- read_xpt(input_adsl)

cat(paste("  ADAE:", nrow(adae), "records\n"))
cat(paste("  ADSL:", nrow(adsl), "records\n\n"))

# ----------------------------------------------------------------------------
# Define Parameters
# ----------------------------------------------------------------------------
params <- tibble(
  PARAMCD = c("TTDERM", "TTSAE", "TTAEWD"),
  PARAM = c(
    "Time to First Dermatologic AE",
    "Time to First Serious AE",
    "Time to AE Leading to Withdrawal"
  )
)

# ----------------------------------------------------------------------------
# Calculate Time to First Dermatologic AE
# ----------------------------------------------------------------------------
cat("Calculating time to first dermatologic AE...\n")

# Dermatologic AEs: AEBODSYS contains "SKIN"
derm_ae <- adae %>%
  filter(TRTEMFL == "Y" & str_detect(toupper(AEBODSYS), "SKIN")) %>%
  group_by(STUDYID, USUBJID) %>%
  slice_min(ASTDT) %>%
  ungroup() %>%
  select(STUDYID, USUBJID, EVNTDT = ASTDT) %>%
  mutate(CNSR = 0)  # Event occurred

ttderm <- adsl %>%
  select(STUDYID, USUBJID, TRTSDT, TRTEDT, TRT01P, TRT01PN, TRT01A, TRT01AN,
         SAFFL, SITEID, AGE, AGEGR1, SEX, RACE) %>%
  left_join(derm_ae, by = c("STUDYID", "USUBJID")) %>%
  mutate(
    PARAMCD = "TTDERM",
    PARAM = "Time to First Dermatologic AE",
    # If no event, censor at end of treatment or last known date
    CNSR = if_else(is.na(EVNTDT), 1, 0),
    ADT = coalesce(EVNTDT, TRTEDT),
    AVAL = as.numeric(difftime(ADT, TRTSDT, units = "days")) + 1,
    EVNTDESC = if_else(CNSR == 0, "Dermatologic AE", "Censored")
  )

cat(paste("  Events:", sum(ttderm$CNSR == 0), "\n"))
cat(paste("  Censored:", sum(ttderm$CNSR == 1), "\n\n"))

# ----------------------------------------------------------------------------
# Calculate Time to First Serious AE
# ----------------------------------------------------------------------------
cat("Calculating time to first serious AE...\n")

sae <- adae %>%
  filter(TRTEMFL == "Y" & SERFL == "Y") %>%
  group_by(STUDYID, USUBJID) %>%
  slice_min(ASTDT) %>%
  ungroup() %>%
  select(STUDYID, USUBJID, EVNTDT = ASTDT) %>%
  mutate(CNSR = 0)

ttsae <- adsl %>%
  select(STUDYID, USUBJID, TRTSDT, TRTEDT, TRT01P, TRT01PN, TRT01A, TRT01AN,
         SAFFL, SITEID, AGE, AGEGR1, SEX, RACE) %>%
  left_join(sae, by = c("STUDYID", "USUBJID")) %>%
  mutate(
    PARAMCD = "TTSAE",
    PARAM = "Time to First Serious AE",
    CNSR = if_else(is.na(EVNTDT), 1, 0),
    ADT = coalesce(EVNTDT, TRTEDT),
    AVAL = as.numeric(difftime(ADT, TRTSDT, units = "days")) + 1,
    EVNTDESC = if_else(CNSR == 0, "Serious AE", "Censored")
  )

cat(paste("  Events:", sum(ttsae$CNSR == 0), "\n"))
cat(paste("  Censored:", sum(ttsae$CNSR == 1), "\n\n"))

# ----------------------------------------------------------------------------
# Calculate Time to AE Leading to Withdrawal
# ----------------------------------------------------------------------------
cat("Calculating time to AE leading to withdrawal...\n")

aewd <- adae %>%
  filter(TRTEMFL == "Y" & DCSFL == "Y") %>%
  group_by(STUDYID, USUBJID) %>%
  slice_min(ASTDT) %>%
  ungroup() %>%
  select(STUDYID, USUBJID, EVNTDT = ASTDT) %>%
  mutate(CNSR = 0)

ttaewd <- adsl %>%
  select(STUDYID, USUBJID, TRTSDT, TRTEDT, TRT01P, TRT01PN, TRT01A, TRT01AN,
         SAFFL, SITEID, AGE, AGEGR1, SEX, RACE) %>%
  left_join(aewd, by = c("STUDYID", "USUBJID")) %>%
  mutate(
    PARAMCD = "TTAEWD",
    PARAM = "Time to AE Leading to Withdrawal",
    CNSR = if_else(is.na(EVNTDT), 1, 0),
    ADT = coalesce(EVNTDT, TRTEDT),
    AVAL = as.numeric(difftime(ADT, TRTSDT, units = "days")) + 1,
    EVNTDESC = if_else(CNSR == 0, "AE Leading to Withdrawal", "Censored")
  )

cat(paste("  Events:", sum(ttaewd$CNSR == 0), "\n"))
cat(paste("  Censored:", sum(ttaewd$CNSR == 1), "\n\n"))

# ----------------------------------------------------------------------------
# Combine All Parameters
# ----------------------------------------------------------------------------
cat("Combining all parameters...\n")

adtte <- bind_rows(ttderm, ttsae, ttaewd)

# ----------------------------------------------------------------------------
# Derive Additional Variables
# ----------------------------------------------------------------------------
cat("Deriving additional variables...\n")

adtte <- adtte %>%
  mutate(
    # Start date (treatment start)
    STARTDT = TRTSDT,

    # Parameter number
    PARAMN = case_when(
      PARAMCD == "TTDERM" ~ 1,
      PARAMCD == "TTSAE" ~ 2,
      PARAMCD == "TTAEWD" ~ 3,
      TRUE ~ NA_real_
    ),

    # Censoring reason
    CNSDTDSC = case_when(
      CNSR == 1 ~ "End of Treatment Period",
      TRUE ~ NA_character_
    )
  )

# ----------------------------------------------------------------------------
# Set Variable Attributes
# ----------------------------------------------------------------------------
cat("Setting variable attributes...\n")

attr(adtte$STUDYID, "label") <- "Study Identifier"
attr(adtte$USUBJID, "label") <- "Unique Subject Identifier"
attr(adtte$PARAM, "label") <- "Parameter"
attr(adtte$PARAMCD, "label") <- "Parameter Code"
attr(adtte$PARAMN, "label") <- "Parameter (N)"
attr(adtte$AVAL, "label") <- "Analysis Value (Days)"
attr(adtte$CNSR, "label") <- "Censor"
attr(adtte$STARTDT, "label") <- "Time-to-Event Origin Date"
attr(adtte$ADT, "label") <- "Analysis Date"
attr(adtte$EVNTDESC, "label") <- "Event or Censoring Description"
attr(adtte$CNSDTDSC, "label") <- "Censoring Description"

# ----------------------------------------------------------------------------
# Select and order final variables
# ----------------------------------------------------------------------------
cat("Selecting final variables...\n")

adtte_final <- adtte %>%
  filter(SAFFL == "Y") %>%  # Safety population only
  select(
    # Identifiers
    STUDYID, USUBJID, SITEID,
    # ADSL variables
    TRT01P, TRT01PN, TRT01A, TRT01AN,
    SAFFL, AGE, AGEGR1, SEX, RACE,
    # Parameter
    PARAM, PARAMCD, PARAMN,
    # Time-to-event variables
    STARTDT, ADT, AVAL, CNSR,
    EVNTDESC, CNSDTDSC
  ) %>%
  arrange(USUBJID, PARAMCD)

# ----------------------------------------------------------------------------
# Export to XPT
# ----------------------------------------------------------------------------
cat("\nExporting ADTTE...\n")

write_xpt(adtte_final, output_adtte, version = 5, name = "ADTTE")

cat(paste("  Output:", nrow(adtte_final), "records\n"))
cat(paste("  File:", output_adtte, "\n"))

# Summary statistics
cat("\n=== Summary ===\n")
cat("\nEvent Summary by Parameter:\n")
event_summary <- adtte_final %>%
  group_by(PARAM) %>%
  summarise(
    N = n(),
    Events = sum(CNSR == 0),
    Censored = sum(CNSR == 1),
    Median_Days = median(AVAL, na.rm = TRUE),
    .groups = "drop"
  )
print(event_summary)

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
