#!/usr/bin/env Rscript
#' ============================================================================
#' Dataset Comparison Script
#' ============================================================================
#'
#' Compares generated ADaM dataset against ground truth using diffdf
#' Generates HTML report with differences
#' ============================================================================

library(haven)
library(dplyr)
library(diffdf)

# Get file paths from Snakemake
generated_path <- snakemake@input$generated
expected_path <- snakemake@input$expected
output_report <- snakemake@output$report
log_file <- snakemake@log[[1]]

# Extract dataset name from path
dataset_name <- toupper(tools::file_path_sans_ext(basename(generated_path)))

# Start logging
sink(log_file, split = TRUE)
cat(sprintf("Dataset Comparison Log - %s\n", dataset_name))
cat("=================================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Datasets
# ----------------------------------------------------------------------------
cat("Loading datasets...\n")

generated <- read_xpt(generated_path)
expected <- read_xpt(expected_path)

cat(paste("  Generated:", nrow(generated), "records,", ncol(generated), "variables\n"))
cat(paste("  Expected:", nrow(expected), "records,", ncol(expected), "variables\n\n"))

# ----------------------------------------------------------------------------
# Determine Key Variables
# ----------------------------------------------------------------------------
# Standard key variables for each dataset type
key_vars <- switch(
  dataset_name,
  "ADSL" = c("STUDYID", "USUBJID"),
  "ADAE" = c("STUDYID", "USUBJID", "AESEQ"),
  "ADVS" = c("STUDYID", "USUBJID", "PARAMCD", "AVISITN", "ATPTN"),
  "ADLBC" = c("STUDYID", "USUBJID", "PARAMCD", "AVISITN"),
  "ADLBH" = c("STUDYID", "USUBJID", "PARAMCD", "AVISITN"),
  "ADQSADAS" = c("STUDYID", "USUBJID", "PARAMCD", "AVISITN"),
  "ADTTE" = c("STUDYID", "USUBJID", "PARAMCD"),
  c("STUDYID", "USUBJID")  # Default
)

# Verify key variables exist in both datasets
available_keys <- intersect(key_vars, intersect(names(generated), names(expected)))
cat(paste("  Key variables:", paste(available_keys, collapse = ", "), "\n\n"))

# ----------------------------------------------------------------------------
# Find Common Variables
# ----------------------------------------------------------------------------
common_vars <- intersect(names(generated), names(expected))
gen_only <- setdiff(names(generated), names(expected))
exp_only <- setdiff(names(expected), names(generated))

cat("Variable comparison:\n")
cat(paste("  Common variables:", length(common_vars), "\n"))
cat(paste("  Generated only:", length(gen_only), "\n"))
cat(paste("  Expected only:", length(exp_only), "\n\n"))

if (length(gen_only) > 0) {
  cat("  Variables only in generated:", paste(gen_only, collapse = ", "), "\n")
}
if (length(exp_only) > 0) {
  cat("  Variables only in expected:", paste(exp_only, collapse = ", "), "\n")
}
cat("\n")

# ----------------------------------------------------------------------------
# Run Comparison
# ----------------------------------------------------------------------------
cat("Running diffdf comparison...\n\n")

# Subset to common variables for comparison
generated_subset <- generated %>% select(all_of(common_vars))
expected_subset <- expected %>% select(all_of(common_vars))

# Run diffdf with available key variables
if (length(available_keys) > 0) {
  comparison <- diffdf(
    base = expected_subset,
    compare = generated_subset,
    keys = available_keys,
    tolerance = 0.0001
  )
} else {
  # If no keys, compare by row position
  comparison <- diffdf(
    base = expected_subset,
    compare = generated_subset,
    tolerance = 0.0001
  )
}

# Get summary
n_issues <- length(comparison)
has_differences <- n_issues > 0

cat("Comparison results:\n")
if (has_differences) {
  cat(paste("  Issues found:", n_issues, "\n"))
  print(comparison)
} else {
  cat("  No differences found!\n")
}
cat("\n")

# ----------------------------------------------------------------------------
# Calculate Match Statistics
# ----------------------------------------------------------------------------

# Variable match rate
var_match_rate <- length(common_vars) / max(length(names(expected)), 1) * 100

# For record-level matching, we'd need to compare individual values
# This is a simplified metric
if (!has_differences) {
  record_match_rate <- 100.0
} else {
  # Estimate based on number of differences
  total_cells <- nrow(expected_subset) * length(common_vars)
  diff_cells <- 0
  if ("VarDiff" %in% names(comparison)) {
    diff_cells <- nrow(comparison$VarDiff)
  }
  record_match_rate <- max(0, (1 - diff_cells / max(total_cells, 1)) * 100)
}

cat("Match statistics:\n")
cat(paste("  Variable match rate:", sprintf("%.1f%%", var_match_rate), "\n"))
cat(paste("  Record match rate:", sprintf("%.1f%%", record_match_rate), "\n\n"))

# ----------------------------------------------------------------------------
# Generate HTML Report
# ----------------------------------------------------------------------------
cat("Generating HTML report...\n")

html_content <- paste0('<!DOCTYPE html>
<html>
<head>
    <title>', dataset_name, ' Comparison Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        h1 { color: #333; }
        h2 { color: #666; margin-top: 30px; }
        .summary-box {
            background: #f5f5f5;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }
        .pass { color: #28a745; font-weight: bold; }
        .fail { color: #dc3545; font-weight: bold; }
        .warning { color: #ffc107; font-weight: bold; }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        th { background-color: #4CAF50; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .metric { font-size: 24px; font-weight: bold; }
        .metric-label { font-size: 14px; color: #666; }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin: 20px 0;
        }
        .metric-card {
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
    </style>
</head>
<body>
    <h1>', dataset_name, ' Comparison Report</h1>
    <p>Generated: ', Sys.time(), '</p>

    <div class="summary-box">
        <h2>Summary</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric">', sprintf("%.1f%%", var_match_rate), '</div>
                <div class="metric-label">Variable Match Rate</div>
            </div>
            <div class="metric-card">
                <div class="metric">', sprintf("%.1f%%", record_match_rate), '</div>
                <div class="metric-label">Record Match Rate</div>
            </div>
            <div class="metric-card">
                <div class="metric ', ifelse(!has_differences, "pass", "fail"), '">',
                    ifelse(!has_differences, "PASS", "DIFFERENCES"), '</div>
                <div class="metric-label">Overall Status</div>
            </div>
        </div>
    </div>

    <h2>Dataset Details</h2>
    <table>
        <tr>
            <th>Metric</th>
            <th>Generated</th>
            <th>Expected</th>
        </tr>
        <tr>
            <td>Records</td>
            <td>', nrow(generated), '</td>
            <td>', nrow(expected), '</td>
        </tr>
        <tr>
            <td>Variables</td>
            <td>', ncol(generated), '</td>
            <td>', ncol(expected), '</td>
        </tr>
        <tr>
            <td>Common Variables</td>
            <td colspan="2">', length(common_vars), '</td>
        </tr>
    </table>

    <h2>Variable Comparison</h2>
    <table>
        <tr>
            <th>Category</th>
            <th>Count</th>
            <th>Variables</th>
        </tr>
        <tr>
            <td>Common</td>
            <td>', length(common_vars), '</td>
            <td>', paste(head(common_vars, 10), collapse = ", "),
                ifelse(length(common_vars) > 10, "...", ""), '</td>
        </tr>
        <tr>
            <td>Generated Only</td>
            <td>', length(gen_only), '</td>
            <td>', ifelse(length(gen_only) > 0, paste(gen_only, collapse = ", "), "-"), '</td>
        </tr>
        <tr>
            <td>Expected Only</td>
            <td>', length(exp_only), '</td>
            <td>', ifelse(length(exp_only) > 0, paste(exp_only, collapse = ", "), "-"), '</td>
        </tr>
    </table>
')

# Add differences section if any
if (has_differences) {
  html_content <- paste0(html_content, '
    <h2>Differences Found</h2>
    <p class="fail">The following differences were detected:</p>
    <pre>', capture.output(print(comparison)), '</pre>
')
} else {
  html_content <- paste0(html_content, '
    <h2>Validation Result</h2>
    <p class="pass">No differences found between generated and expected datasets!</p>
')
}

# Close HTML
html_content <- paste0(html_content, '
    <h2>Files Compared</h2>
    <ul>
        <li><strong>Generated:</strong> ', generated_path, '</li>
        <li><strong>Expected:</strong> ', expected_path, '</li>
    </ul>

</body>
</html>')

# Write HTML file
writeLines(html_content, output_report)

cat(paste("  Output:", output_report, "\n"))

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
