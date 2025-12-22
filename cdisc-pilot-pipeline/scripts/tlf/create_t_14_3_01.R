#!/usr/bin/env Rscript
#' ============================================================================
#' Table 14-3.01: ADAS-Cog(11) - Change from Baseline to Week 24 - LOCF
#' ============================================================================
#'
#' Study: CDISCPILOT01
#' Population: Efficacy (ITT with baseline and post-baseline)
#'
#' PRIMARY EFFICACY TABLE
#'
#' Analysis: ANCOVA with baseline value and pooled site as covariates
#' Output: RTF table with LS means and treatment comparisons
#' ============================================================================

library(haven)
library(dplyr)
library(tidyr)
library(stringr)
library(emmeans)

# Get file paths from Snakemake
input_adqsadas <- snakemake@input$adqsadas
input_adsl <- snakemake@input$adsl
output_rtf <- snakemake@output$rtf
log_file <- snakemake@log[[1]]

# Start logging
sink(log_file, split = TRUE)
cat("Table 14-3.01 Creation Log - PRIMARY EFFICACY\n")
cat("==============================================\n")
cat(paste("Start time:", Sys.time(), "\n\n"))

# ----------------------------------------------------------------------------
# Load Data
# ----------------------------------------------------------------------------
cat("Loading data...\n")

adqsadas <- read_xpt(input_adqsadas)
adsl <- read_xpt(input_adsl)

cat(paste("  ADQSADAS records:", nrow(adqsadas), "\n"))
cat(paste("  ADSL records:", nrow(adsl), "\n\n"))

# ----------------------------------------------------------------------------
# Filter to Analysis Population
# ----------------------------------------------------------------------------
cat("Filtering to efficacy population at Week 24...\n")

# Get Week 24 data for primary analysis
# Using ANL01FL flag or filtering to Week 24 with efficacy population
analysis_data <- adqsadas %>%
  filter(PARAMCD == "ACTOT" & AVISITN == 11) %>%  # Week 24
  filter(!is.na(CHG) & !is.na(BASE))

# Join with ADSL for site grouping if not present
if (!"SITEGR1" %in% names(analysis_data)) {
  site_data <- adsl %>%
    select(USUBJID, SITEGR1) %>%
    distinct()
  analysis_data <- analysis_data %>%
    left_join(site_data, by = "USUBJID")
}

cat(paste("  Analysis records:", nrow(analysis_data), "\n\n"))

# ----------------------------------------------------------------------------
# Calculate Big N by Treatment
# ----------------------------------------------------------------------------
big_n <- analysis_data %>%
  group_by(TRT01P) %>%
  summarise(N = n(), .groups = "drop")

cat("Sample sizes:\n")
print(big_n)
cat("\n")

# ----------------------------------------------------------------------------
# Descriptive Statistics
# ----------------------------------------------------------------------------
cat("Calculating descriptive statistics...\n")

desc_stats <- analysis_data %>%
  group_by(TRT01P) %>%
  summarise(
    n = n(),
    base_mean = mean(BASE, na.rm = TRUE),
    base_sd = sd(BASE, na.rm = TRUE),
    wk24_mean = mean(AVAL, na.rm = TRUE),
    wk24_sd = sd(AVAL, na.rm = TRUE),
    chg_mean = mean(CHG, na.rm = TRUE),
    chg_sd = sd(CHG, na.rm = TRUE),
    .groups = "drop"
  )

cat("\nDescriptive statistics:\n")
print(desc_stats)
cat("\n")

# ----------------------------------------------------------------------------
# ANCOVA Model
# ----------------------------------------------------------------------------
cat("Fitting ANCOVA model...\n")
cat("  Model: CHG ~ TRT01P + BASE + SITEGR1\n\n")

# Ensure treatment is a factor with Placebo as reference
analysis_data <- analysis_data %>%
  mutate(
    TRT01P = factor(TRT01P, levels = c("Placebo", "Xanomeline Low Dose", "Xanomeline High Dose"))
  )

# Check if SITEGR1 exists and has variation
if ("SITEGR1" %in% names(analysis_data) && n_distinct(analysis_data$SITEGR1) > 1) {
  model <- lm(CHG ~ TRT01P + BASE + SITEGR1, data = analysis_data)
} else {
  cat("  Note: SITEGR1 not available or no variation, using model without site\n")
  model <- lm(CHG ~ TRT01P + BASE, data = analysis_data)
}

cat("\nModel summary:\n")
print(summary(model))
cat("\n")

# ----------------------------------------------------------------------------
# LS Means
# ----------------------------------------------------------------------------
cat("Calculating LS Means...\n")

lsmeans_result <- emmeans(model, "TRT01P")
lsmeans_df <- as.data.frame(lsmeans_result)

cat("\nLS Means:\n")
print(lsmeans_df)
cat("\n")

# ----------------------------------------------------------------------------
# Treatment Comparisons
# ----------------------------------------------------------------------------
cat("Calculating treatment comparisons vs Placebo...\n")

contrasts_result <- contrast(lsmeans_result, method = "trt.vs.ctrl", ref = 1)
contrasts_df <- as.data.frame(contrasts_result)

# Add confidence intervals
confint_result <- confint(contrasts_result)
confint_df <- as.data.frame(confint_result)

cat("\nTreatment Comparisons:\n")
print(confint_df)
cat("\n")

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
  "\\pard\\qc\\b Table 14-3.01\\b0\\par\n",
  "\\pard\\qc ADAS-Cog(11) - Change from Baseline to Week 24 - LOCF\\par\n",
  "\\pard\\qc Efficacy Population\\par\n",
  "\\pard\\qc CDISCPILOT01\\par\n",
  "\\par\n"
)

# Descriptive statistics section
rtf_content <- paste0(rtf_content,
  "\\pard\\b Descriptive Statistics\\b0\\par\n",
  "\\par\n",
  "\\trowd\\trgaph108\\trleft-108\n",
  "\\cellx2500\\cellx4500\\cellx6500\\cellx8500\n",
  "\\pard\\intbl\\b Statistic\\cell Placebo\\cell Xanomeline Low\\cell Xanomeline High\\cell\\b0\\row\n"
)

for (i in 1:nrow(desc_stats)) {
  trt <- desc_stats$TRT01P[i]
  col_idx <- case_when(
    trt == "Placebo" ~ 2,
    trt == "Xanomeline Low Dose" ~ 3,
    trt == "Xanomeline High Dose" ~ 4
  )
}

# Add N row
n_pbo <- desc_stats$n[desc_stats$TRT01P == "Placebo"]
n_xlo <- desc_stats$n[desc_stats$TRT01P == "Xanomeline Low Dose"]
n_xhi <- desc_stats$n[desc_stats$TRT01P == "Xanomeline High Dose"]

rtf_content <- paste0(rtf_content,
  sprintf("\\pard\\intbl N\\cell %d\\cell %d\\cell %d\\cell\\row\n", n_pbo, n_xlo, n_xhi)
)

# Add Baseline Mean (SD)
base_pbo <- sprintf("%.1f (%.2f)", desc_stats$base_mean[desc_stats$TRT01P == "Placebo"],
                    desc_stats$base_sd[desc_stats$TRT01P == "Placebo"])
base_xlo <- sprintf("%.1f (%.2f)", desc_stats$base_mean[desc_stats$TRT01P == "Xanomeline Low Dose"],
                    desc_stats$base_sd[desc_stats$TRT01P == "Xanomeline Low Dose"])
base_xhi <- sprintf("%.1f (%.2f)", desc_stats$base_mean[desc_stats$TRT01P == "Xanomeline High Dose"],
                    desc_stats$base_sd[desc_stats$TRT01P == "Xanomeline High Dose"])

rtf_content <- paste0(rtf_content,
  sprintf("\\pard\\intbl Baseline Mean (SD)\\cell %s\\cell %s\\cell %s\\cell\\row\n", base_pbo, base_xlo, base_xhi)
)

# Add Change Mean (SD)
chg_pbo <- sprintf("%.1f (%.2f)", desc_stats$chg_mean[desc_stats$TRT01P == "Placebo"],
                   desc_stats$chg_sd[desc_stats$TRT01P == "Placebo"])
chg_xlo <- sprintf("%.1f (%.2f)", desc_stats$chg_mean[desc_stats$TRT01P == "Xanomeline Low Dose"],
                   desc_stats$chg_sd[desc_stats$TRT01P == "Xanomeline Low Dose"])
chg_xhi <- sprintf("%.1f (%.2f)", desc_stats$chg_mean[desc_stats$TRT01P == "Xanomeline High Dose"],
                   desc_stats$chg_sd[desc_stats$TRT01P == "Xanomeline High Dose"])

rtf_content <- paste0(rtf_content,
  sprintf("\\pard\\intbl Change Mean (SD)\\cell %s\\cell %s\\cell %s\\cell\\row\n", chg_pbo, chg_xlo, chg_xhi)
)

# ANCOVA section
rtf_content <- paste0(rtf_content,
  "\\pard\\par\n",
  "\\pard\\b ANCOVA Results\\b0\\par\n",
  "\\pard Model: CHG = TRT01P + BASE + SITEGR1\\par\n",
  "\\par\n"
)

# LS Means
ls_pbo <- sprintf("%.2f (%.2f)", lsmeans_df$emmean[lsmeans_df$TRT01P == "Placebo"],
                  lsmeans_df$SE[lsmeans_df$TRT01P == "Placebo"])
ls_xlo <- sprintf("%.2f (%.2f)", lsmeans_df$emmean[lsmeans_df$TRT01P == "Xanomeline Low Dose"],
                  lsmeans_df$SE[lsmeans_df$TRT01P == "Xanomeline Low Dose"])
ls_xhi <- sprintf("%.2f (%.2f)", lsmeans_df$emmean[lsmeans_df$TRT01P == "Xanomeline High Dose"],
                  lsmeans_df$SE[lsmeans_df$TRT01P == "Xanomeline High Dose"])

rtf_content <- paste0(rtf_content,
  "\\trowd\\trgaph108\\trleft-108\n",
  "\\cellx2500\\cellx4500\\cellx6500\\cellx8500\n",
  sprintf("\\pard\\intbl LS Mean (SE)\\cell %s\\cell %s\\cell %s\\cell\\row\n", ls_pbo, ls_xlo, ls_xhi)
)

# Treatment comparisons
rtf_content <- paste0(rtf_content,
  "\\pard\\par\n",
  "\\pard\\b Treatment Comparisons vs Placebo\\b0\\par\n",
  "\\par\n",
  "\\trowd\\trgaph108\\trleft-108\n",
  "\\cellx3000\\cellx5000\\cellx7000\\cellx9000\n",
  "\\pard\\intbl\\b Comparison\\cell Difference\\cell 95%% CI\\cell p-value\\cell\\b0\\row\n"
)

for (i in 1:nrow(confint_df)) {
  comp_name <- as.character(confint_df$contrast[i])
  diff <- sprintf("%.2f", confint_df$estimate[i])
  ci <- sprintf("(%.2f, %.2f)", confint_df$lower.CL[i], confint_df$upper.CL[i])
  pval <- sprintf("%.4f", contrasts_df$p.value[i])

  rtf_content <- paste0(rtf_content,
    sprintf("\\pard\\intbl %s\\cell %s\\cell %s\\cell %s\\cell\\row\n", comp_name, diff, ci, pval)
  )
}

# Close RTF
rtf_content <- paste0(rtf_content,
  "\\pard\\par\n",
  "\\pard Source: ADQSADAS, ADSL\\par\n",
  "\\pard Note: Negative change indicates improvement\\par\n",
  sprintf("\\pard Generated: %s\\par\n", Sys.time()),
  "}"
)

# Write RTF file
writeLines(rtf_content, output_rtf)

cat(paste("  Output:", output_rtf, "\n"))

cat("\n=== PRIMARY EFFICACY RESULTS ===\n")
cat("\nLS Means:\n")
print(lsmeans_df[, c("TRT01P", "emmean", "SE")])
cat("\nTreatment Differences vs Placebo:\n")
print(confint_df[, c("contrast", "estimate", "lower.CL", "upper.CL")])
cat("\np-values:\n")
print(contrasts_df[, c("contrast", "p.value")])

cat(paste("\nEnd time:", Sys.time(), "\n"))
sink()
