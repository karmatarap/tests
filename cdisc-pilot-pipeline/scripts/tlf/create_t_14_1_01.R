#!/usr/bin/env Rscript
#' ============================================================================
#' Table 14-1.01: Summary of Demographic and Baseline Characteristics
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Population: ITT (All randomized subjects)
#'
#' Output: RTF table with demographic summaries by treatment arm
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(stringr)

# Get file paths from Snakemake
input_adsl <- snakemake@input$adsl
output_rtf <- snakemake@output$rtf
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("Table 14-1.01 Creation Log\n")
cat("==========================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Data
# ----------------------------------------------------------------------------
cat("Loading ADSL...\n")

adsl <- read_xpt(input_adsl)
cat(paste("  Records:", nrow(adsl), "\n\n"))

# Filter to ITT population
adsl_itt <- adsl %>%
  filter(ITTFL == "Y")

cat(paste("  ITT population:", nrow(adsl_itt), "\n\n"))

# ----------------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------------

# Format continuous variable summary
format_continuous <- function(data, var, label) {
  data %>%
    group_by(TRT01P) %>%
    summarise(
      N = sum(!is.na(.data[[var]])),
      Mean = mean(.data[[var]], na.rm = TRUE),
      SD = sd(.data[[var]], na.rm = TRUE),
      Median = median(.data[[var]], na.rm = TRUE),
      Min = min(.data[[var]], na.rm = TRUE),
      Max = max(.data[[var]], na.rm = TRUE),
      .groups = "drop"
    ) %>%
    mutate(
      category = label,
      stat_n = sprintf("%.0f", N),
      stat_mean_sd = sprintf("%.1f (%.2f)", Mean, SD),
      stat_median = sprintf("%.1f", Median),
      stat_range = sprintf("%.0f, %.0f", Min, Max)
    ) %>%
    select(TRT01P, category, stat_n, stat_mean_sd, stat_median, stat_range)
}

# Format categorical variable summary
format_categorical <- function(data, var, label) {
  total_n <- data %>%
    group_by(TRT01P) %>%
    summarise(total = n(), .groups = "drop")

  data %>%
    group_by(TRT01P, .data[[var]]) %>%
    summarise(n = n(), .groups = "drop") %>%
    left_join(total_n, by = "TRT01P") %>%
    mutate(
      pct = (n / total) * 100,
      stat = sprintf("%.0f (%.1f%%)", n, pct),
      category = paste(label, "-", .data[[var]])
    ) %>%
    select(TRT01P, category, stat)
}

# ----------------------------------------------------------------------------
# Calculate Summary Statistics
# ----------------------------------------------------------------------------
cat("Calculating summary statistics...\n")

# Age
age_summary <- format_continuous(adsl_itt, "AGE", "Age (years)")

# Sex
sex_summary <- format_categorical(adsl_itt, "SEX", "Sex")

# Race
race_summary <- format_categorical(adsl_itt, "RACE", "Race")

# Ethnicity
ethnic_summary <- format_categorical(adsl_itt, "ETHNIC", "Ethnicity")

# Age group
agegr_summary <- format_categorical(adsl_itt, "AGEGR1", "Age Group")

# ----------------------------------------------------------------------------
# Build Table Structure
# ----------------------------------------------------------------------------
cat("Building table structure...\n")

# Get big N for header
big_n <- adsl_itt %>%
  group_by(TRT01P) %>%
  summarise(N = n(), .groups = "drop") %>%
  arrange(TRT01PN = case_when(
    TRT01P == "Placebo" ~ 1,
    TRT01P == "Xanomeline Low Dose" ~ 2,
    TRT01P == "Xanomeline High Dose" ~ 3
  ))

# Combine all summaries
demographics_table <- list(
  age = age_summary,
  sex = sex_summary,
  race = race_summary,
  ethnic = ethnic_summary,
  agegr = agegr_summary
)

# ----------------------------------------------------------------------------
# Generate RTF Output
# ----------------------------------------------------------------------------
cat("Generating RTF output...\n")

# Create RTF content
rtf_content <- paste0(
  "{\\rtf1\\ansi\\deff0\n",
  "{\\fonttbl{\\f0 Courier New;}}\n",
  "\\paperw12240\\paperh15840\\margl1440\\margr1440\\margt1440\\margb1440\n",
  "\\fs18\n",
  "\\pard\\qc\\b Table 14-1.01\\b0\\par\n",
  "\\pard\\qc Summary of Demographic and Baseline Characteristics\\par\n",
  "\\pard\\qc ITT Population\\par\n",
  "\\pard\\qc CDISCPILOT01\\par\n",
  "\\par\n"
)

# Add header row with N
header <- paste0(
  "\\pard\\trowd\\trgaph108\\trleft-108\n",
  "\\cellx3600\\cellx6000\\cellx8400\\cellx10800\n",
  "\\pard\\intbl\\b Characteristic\\cell ",
  sprintf("Placebo\\line(N=%d)\\cell ", big_n$N[big_n$TRT01P == "Placebo"]),
  sprintf("Xanomeline Low Dose\\line(N=%d)\\cell ", big_n$N[big_n$TRT01P == "Xanomeline Low Dose"]),
  sprintf("Xanomeline High Dose\\line(N=%d)\\cell\\b0\\row\n", big_n$N[big_n$TRT01P == "Xanomeline High Dose"])
)

rtf_content <- paste0(rtf_content, header)

# Add Age section
rtf_content <- paste0(rtf_content,
  "\\pard\\intbl\\b Age (years)\\b0\\cell \\cell \\cell \\cell\\row\n"
)

age_wide <- age_summary %>%
  select(TRT01P, stat_mean_sd) %>%
  pivot_wider(names_from = TRT01P, values_from = stat_mean_sd)

rtf_content <- paste0(rtf_content,
  sprintf("\\pard\\intbl   Mean (SD)\\cell %s\\cell %s\\cell %s\\cell\\row\n",
    age_wide$Placebo[1],
    age_wide$`Xanomeline Low Dose`[1],
    age_wide$`Xanomeline High Dose`[1]
  )
)

# Add Sex section
rtf_content <- paste0(rtf_content,
  "\\pard\\intbl\\b Sex, n (%%)\\b0\\cell \\cell \\cell \\cell\\row\n"
)

for (sex_val in unique(adsl_itt$SEX)) {
  sex_row <- sex_summary %>%
    filter(str_detect(category, sex_val)) %>%
    select(TRT01P, stat) %>%
    pivot_wider(names_from = TRT01P, values_from = stat, values_fill = "0 (0.0%)")

  rtf_content <- paste0(rtf_content,
    sprintf("\\pard\\intbl   %s\\cell %s\\cell %s\\cell %s\\cell\\row\n",
      sex_val,
      sex_row$Placebo[1],
      sex_row$`Xanomeline Low Dose`[1],
      sex_row$`Xanomeline High Dose`[1]
    )
  )
}

# Add Race section
rtf_content <- paste0(rtf_content,
  "\\pard\\intbl\\b Race, n (%%)\\b0\\cell \\cell \\cell \\cell\\row\n"
)

for (race_val in unique(adsl_itt$RACE)) {
  race_row <- race_summary %>%
    filter(str_detect(category, fixed(race_val))) %>%
    select(TRT01P, stat) %>%
    pivot_wider(names_from = TRT01P, values_from = stat, values_fill = "0 (0.0%)")

  if (nrow(race_row) > 0) {
    rtf_content <- paste0(rtf_content,
      sprintf("\\pard\\intbl   %s\\cell %s\\cell %s\\cell %s\\cell\\row\n",
        race_val,
        ifelse(is.na(race_row$Placebo[1]), "0 (0.0%)", race_row$Placebo[1]),
        ifelse(is.na(race_row$`Xanomeline Low Dose`[1]), "0 (0.0%)", race_row$`Xanomeline Low Dose`[1]),
        ifelse(is.na(race_row$`Xanomeline High Dose`[1]), "0 (0.0%)", race_row$`Xanomeline High Dose`[1])
      )
    )
  }
}

# Close table and RTF
rtf_content <- paste0(rtf_content,
  "\\pard\\par\n",
  "\\pard Source: ADSL\\par\n",
  sprintf("\\pard Generated: %s\\par\n", Sys.time()),
  "}"
)

# Write RTF file
writeLines(rtf_content, output_rtf)

cat(paste("  Output:", output_rtf, "\n"))

# Summary
cat("\n=== Summary ===\n")
cat("Demographics Table Generated\n")
print(big_n)

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
