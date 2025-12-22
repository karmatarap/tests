#!/usr/bin/env Rscript
#' ============================================================================
#' Table 14-2.01: Overall Summary of Adverse Events
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Population: Safety (Received at least one dose)
#'
#' Output: RTF table with AE overview by treatment arm
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(stringr)

# Get file paths from Snakemake
input_adae <- snakemake@input$adae
input_adsl <- snakemake@input$adsl
output_rtf <- snakemake@output$rtf
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("Table 14-2.01 Creation Log\n")
cat("==========================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Data
# ----------------------------------------------------------------------------
cat("Loading data...\n")

adae <- read_xpt(input_adae)
adsl <- read_xpt(input_adsl)

# Filter to Safety population
adsl_saf <- adsl %>%
  filter(SAFFL == "Y")

adae_saf <- adae %>%
  filter(SAFFL == "Y")

cat(paste("  Safety population:", nrow(adsl_saf), "\n"))
cat(paste("  Treatment-emergent AEs:", sum(adae_saf$TRTEMFL == "Y"), "\n\n"))

# ----------------------------------------------------------------------------
# Calculate Big N
# ----------------------------------------------------------------------------
big_n <- adsl_saf %>%
  group_by(TRT01A) %>%
  summarise(N = n(), .groups = "drop")

# ----------------------------------------------------------------------------
# Calculate AE Summary Statistics
# ----------------------------------------------------------------------------
cat("Calculating AE summary statistics...\n")

# Treatment-emergent AEs
te_ae <- adae_saf %>%
  filter(TRTEMFL == "Y")

# Subjects with any TEAE
any_teae <- te_ae %>%
  group_by(TRT01A) %>%
  summarise(n_subj = n_distinct(USUBJID), .groups = "drop") %>%
  left_join(big_n, by = "TRT01A") %>%
  mutate(
    pct = (n_subj / N) * 100,
    stat = sprintf("%d (%.1f%%)", n_subj, pct),
    category = "Subjects with any TEAE"
  )

# Subjects with serious AE
sae <- te_ae %>%
  filter(SERFL == "Y") %>%
  group_by(TRT01A) %>%
  summarise(n_subj = n_distinct(USUBJID), .groups = "drop") %>%
  left_join(big_n, by = "TRT01A") %>%
  mutate(
    pct = (n_subj / N) * 100,
    stat = sprintf("%d (%.1f%%)", n_subj, pct),
    category = "Subjects with serious AE"
  )

# Subjects with AE leading to discontinuation
disc_ae <- te_ae %>%
  filter(DCSFL == "Y") %>%
  group_by(TRT01A) %>%
  summarise(n_subj = n_distinct(USUBJID), .groups = "drop") %>%
  left_join(big_n, by = "TRT01A") %>%
  mutate(
    pct = (n_subj / N) * 100,
    stat = sprintf("%d (%.1f%%)", n_subj, pct),
    category = "Subjects with AE leading to discontinuation"
  )

# Subjects with related AE
related_ae <- te_ae %>%
  filter(RELFL == "Y") %>%
  group_by(TRT01A) %>%
  summarise(n_subj = n_distinct(USUBJID), .groups = "drop") %>%
  left_join(big_n, by = "TRT01A") %>%
  mutate(
    pct = (n_subj / N) * 100,
    stat = sprintf("%d (%.1f%%)", n_subj, pct),
    category = "Subjects with drug-related AE"
  )

# Subjects with severe AE
severe_ae <- te_ae %>%
  filter(ASEV == "SEVERE") %>%
  group_by(TRT01A) %>%
  summarise(n_subj = n_distinct(USUBJID), .groups = "drop") %>%
  left_join(big_n, by = "TRT01A") %>%
  mutate(
    pct = (n_subj / N) * 100,
    stat = sprintf("%d (%.1f%%)", n_subj, pct),
    category = "Subjects with severe AE"
  )

# Deaths
deaths <- te_ae %>%
  filter(DTHFL == "Y") %>%
  group_by(TRT01A) %>%
  summarise(n_subj = n_distinct(USUBJID), .groups = "drop") %>%
  left_join(big_n, by = "TRT01A") %>%
  mutate(
    pct = (n_subj / N) * 100,
    stat = sprintf("%d (%.1f%%)", n_subj, pct),
    category = "Deaths"
  )

# Combine all summaries
ae_summary <- bind_rows(any_teae, sae, disc_ae, related_ae, severe_ae, deaths)

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
  "\\pard\\qc\\b Table 14-2.01\\b0\\par\n",
  "\\pard\\qc Overall Summary of Treatment-Emergent Adverse Events\\par\n",
  "\\pard\\qc Safety Population\\par\n",
  "\\pard\\qc CDISCPILOT01\\par\n",
  "\\par\n"
)

# Add header row
header <- paste0(
  "\\pard\\trowd\\trgaph108\\trleft-108\n",
  "\\cellx4500\\cellx6500\\cellx8500\\cellx10500\n",
  "\\pard\\intbl\\b Category\\cell ",
  sprintf("Placebo\\line(N=%d)\\cell ", big_n$N[big_n$TRT01A == "Placebo"]),
  sprintf("Xanomeline Low Dose\\line(N=%d)\\cell ", big_n$N[big_n$TRT01A == "Xanomeline Low Dose"]),
  sprintf("Xanomeline High Dose\\line(N=%d)\\cell\\b0\\row\n", big_n$N[big_n$TRT01A == "Xanomeline High Dose"])
)

rtf_content <- paste0(rtf_content, header)

# Add data rows
categories <- c(
  "Subjects with any TEAE",
  "Subjects with serious AE",
  "Subjects with AE leading to discontinuation",
  "Subjects with drug-related AE",
  "Subjects with severe AE",
  "Deaths"
)

for (cat in categories) {
  row_data <- ae_summary %>%
    filter(category == cat) %>%
    select(TRT01A, stat) %>%
    pivot_wider(names_from = TRT01A, values_from = stat, values_fill = "0 (0.0%)")

  pbo <- ifelse("Placebo" %in% names(row_data), row_data$Placebo[1], "0 (0.0%)")
  xlo <- ifelse("Xanomeline Low Dose" %in% names(row_data), row_data$`Xanomeline Low Dose`[1], "0 (0.0%)")
  xhi <- ifelse("Xanomeline High Dose" %in% names(row_data), row_data$`Xanomeline High Dose`[1], "0 (0.0%)")

  rtf_content <- paste0(rtf_content,
    sprintf("\\pard\\intbl %s\\cell %s\\cell %s\\cell %s\\cell\\row\n",
      cat, pbo, xlo, xhi
    )
  )
}

# Close table and RTF
rtf_content <- paste0(rtf_content,
  "\\pard\\par\n",
  "\\pard Source: ADAE, ADSL\\par\n",
  "\\pard TEAE = Treatment-Emergent Adverse Event\\par\n",
  sprintf("\\pard Generated: %s\\par\n", Sys.time()),
  "}"
)

# Write RTF file
writeLines(rtf_content, output_rtf)

cat(paste("  Output:", output_rtf, "\n"))

# Summary
cat("\n=== Summary ===\n")
cat("AE Overview Table Generated\n")
print(big_n)

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
