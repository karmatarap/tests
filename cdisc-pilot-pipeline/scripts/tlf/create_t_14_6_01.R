#!/usr/bin/env Rscript
#' ============================================================================
#' Table 14-6.01: Summary of Vital Signs at Baseline and End of Treatment
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Population: Safety (Received at least one dose)
#'
#' Output: RTF table with vital signs summaries by treatment arm
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(stringr)

# Get file paths from Snakemake
input_advs <- snakemake@input$advs
input_adsl <- snakemake@input$adsl
output_rtf <- snakemake@output$rtf
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("Table 14-6.01 Creation Log\n")
cat("==========================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Data
# ----------------------------------------------------------------------------
cat("Loading data...\n")

advs <- read_xpt(input_advs)
adsl <- read_xpt(input_adsl)

# Filter to Safety population
advs_saf <- advs %>%
  filter(SAFFL == "Y")

adsl_saf <- adsl %>%
  filter(SAFFL == "Y")

cat(paste("  Safety population:", nrow(adsl_saf), "\n"))
cat(paste("  ADVS records:", nrow(advs_saf), "\n\n"))

# ----------------------------------------------------------------------------
# Calculate Big N
# ----------------------------------------------------------------------------
big_n <- adsl_saf %>%
  group_by(TRT01A) %>%
  summarise(N = n(), .groups = "drop")

# ----------------------------------------------------------------------------
# Filter to Key Parameters
# ----------------------------------------------------------------------------
cat("Filtering to key vital sign parameters...\n")

# Key parameters: SYSBP, DIABP, PULSE
key_params <- c("SYSBP", "DIABP", "PULSE", "WEIGHT")

advs_key <- advs_saf %>%
  filter(PARAMCD %in% key_params)

cat(paste("  Key parameter records:", nrow(advs_key), "\n\n"))

# ----------------------------------------------------------------------------
# Calculate Summary Statistics
# ----------------------------------------------------------------------------
cat("Calculating summary statistics...\n")

# Function to calculate stats
calc_stats <- function(data, timepoint_label, visit_filter) {
  data %>%
    filter(eval(visit_filter)) %>%
    group_by(TRT01A, PARAMCD, PARAM) %>%
    summarise(
      n = sum(!is.na(AVAL)),
      mean = mean(AVAL, na.rm = TRUE),
      sd = sd(AVAL, na.rm = TRUE),
      median = median(AVAL, na.rm = TRUE),
      min = min(AVAL, na.rm = TRUE),
      max = max(AVAL, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    mutate(timepoint = timepoint_label)
}

# Baseline statistics
baseline_stats <- calc_stats(advs_key, "Baseline", quote(ABLFL == "Y"))

# End of treatment (last observation)
eot_data <- advs_key %>%
  filter(!is.na(AVAL)) %>%
  group_by(USUBJID, PARAMCD) %>%
  slice_max(AVISITN) %>%
  ungroup()

eot_stats <- eot_data %>%
  group_by(TRT01A, PARAMCD, PARAM) %>%
  summarise(
    n = sum(!is.na(AVAL)),
    mean = mean(AVAL, na.rm = TRUE),
    sd = sd(AVAL, na.rm = TRUE),
    median = median(AVAL, na.rm = TRUE),
    min = min(AVAL, na.rm = TRUE),
    max = max(AVAL, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  mutate(timepoint = "End of Treatment")

# Change from baseline at EOT
chg_stats <- eot_data %>%
  filter(!is.na(CHG)) %>%
  group_by(TRT01A, PARAMCD, PARAM) %>%
  summarise(
    n = sum(!is.na(CHG)),
    mean = mean(CHG, na.rm = TRUE),
    sd = sd(CHG, na.rm = TRUE),
    median = median(CHG, na.rm = TRUE),
    min = min(CHG, na.rm = TRUE),
    max = max(CHG, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  mutate(timepoint = "Change from Baseline")

# Combine all statistics
all_stats <- bind_rows(baseline_stats, eot_stats, chg_stats)

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
  "\\pard\\qc\\b Table 14-6.01\\b0\\par\n",
  "\\pard\\qc Summary of Vital Signs at Baseline and End of Treatment\\par\n",
  "\\pard\\qc Safety Population\\par\n",
  "\\pard\\qc CDISCPILOT01\\par\n",
  "\\par\n"
)

# Add header
rtf_content <- paste0(rtf_content,
  "\\trowd\\trgaph108\\trleft-108\n",
  "\\cellx2200\\cellx3200\\cellx5200\\cellx7200\\cellx9200\n",
  "\\pard\\intbl\\b Parameter / Timepoint\\cell Statistic\\cell ",
  sprintf("Placebo\\line(N=%d)\\cell ", big_n$N[big_n$TRT01A == "Placebo"]),
  sprintf("Xan Low\\line(N=%d)\\cell ", big_n$N[big_n$TRT01A == "Xanomeline Low Dose"]),
  sprintf("Xan High\\line(N=%d)\\cell\\b0\\row\n", big_n$N[big_n$TRT01A == "Xanomeline High Dose"])
)

# Add data for each parameter
for (param in key_params) {
  param_label <- unique(all_stats$PARAM[all_stats$PARAMCD == param])[1]

  rtf_content <- paste0(rtf_content,
    sprintf("\\pard\\intbl\\b %s\\b0\\cell \\cell \\cell \\cell \\cell\\row\n", param_label)
  )

  for (tp in c("Baseline", "End of Treatment", "Change from Baseline")) {
    tp_data <- all_stats %>%
      filter(PARAMCD == param & timepoint == tp)

    if (nrow(tp_data) > 0) {
      # N row
      n_pbo <- tp_data$n[tp_data$TRT01A == "Placebo"]
      n_xlo <- tp_data$n[tp_data$TRT01A == "Xanomeline Low Dose"]
      n_xhi <- tp_data$n[tp_data$TRT01A == "Xanomeline High Dose"]

      rtf_content <- paste0(rtf_content,
        sprintf("\\pard\\intbl   %s\\cell n\\cell %d\\cell %d\\cell %d\\cell\\row\n",
                tp, n_pbo, n_xlo, n_xhi)
      )

      # Mean (SD) row
      mean_pbo <- sprintf("%.1f (%.2f)",
                          tp_data$mean[tp_data$TRT01A == "Placebo"],
                          tp_data$sd[tp_data$TRT01A == "Placebo"])
      mean_xlo <- sprintf("%.1f (%.2f)",
                          tp_data$mean[tp_data$TRT01A == "Xanomeline Low Dose"],
                          tp_data$sd[tp_data$TRT01A == "Xanomeline Low Dose"])
      mean_xhi <- sprintf("%.1f (%.2f)",
                          tp_data$mean[tp_data$TRT01A == "Xanomeline High Dose"],
                          tp_data$sd[tp_data$TRT01A == "Xanomeline High Dose"])

      rtf_content <- paste0(rtf_content,
        sprintf("\\pard\\intbl \\cell Mean (SD)\\cell %s\\cell %s\\cell %s\\cell\\row\n",
                mean_pbo, mean_xlo, mean_xhi)
      )
    }
  }
}

# Close RTF
rtf_content <- paste0(rtf_content,
  "\\pard\\par\n",
  "\\pard Source: ADVS, ADSL\\par\n",
  sprintf("\\pard Generated: %s\\par\n", Sys.time()),
  "}"
)

# Write RTF file
writeLines(rtf_content, output_rtf)

cat(paste("  Output:", output_rtf, "\n"))

cat("\n=== Summary ===\n")
cat("Vital Signs Table Generated\n")
print(big_n)

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
