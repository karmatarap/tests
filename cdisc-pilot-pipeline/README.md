# CDISC Pilot Pipeline

An automated clinical reporting pipeline for the CDISC Pilot Study (CDISCPILOT01) that transforms SDTM data into submission-ready ADaM datasets, Tables/Listings/Figures (TLFs), and validation reports.

## Overview

This pipeline implements the complete data flow:

```
SDTM → ADaM → TLFs → Validation Reports
```

### Study Information
- **Study ID:** CDISCPILOT01
- **Indication:** Alzheimer's Disease
- **Treatment Arms:** Placebo, Xanomeline Low Dose (54mg), Xanomeline High Dose (81mg)
- **Primary Endpoint:** ADAS-Cog(11) change from baseline to Week 24

## Quick Start

### Prerequisites

1. **Python 3.9+** with Snakemake:
   ```bash
   pip install -r requirements.txt
   ```

2. **R 4.3+** with pharmaverse packages:
   ```bash
   conda env create -f envs/r_env.yaml
   conda activate cdisc_r

   # Install pharmaverse packages
   Rscript -e "install.packages(c('admiral', 'xportr', 'pharmaRTF', 'Tplyr', 'diffdf', 'emmeans'))"
   ```

### Running the Pipeline

```bash
# Full pipeline
snakemake --cores 4

# ADaM datasets only
snakemake adam_only --cores 4

# TLFs only (requires ADaM)
snakemake tlf_only --cores 4

# QC benchmarks only
snakemake benchmark --cores 4

# Visualize pipeline DAG
snakemake --dag | dot -Tpng > pipeline_dag.png

# Clean generated files
snakemake clean
```

## Project Structure

```
cdisc-pilot-pipeline/
├── Snakefile                 # Main workflow definition
├── config/
│   └── config.yaml           # Study configuration
├── rules/
│   ├── 00_document_parsing.smk
│   ├── 01_sdtm.smk
│   ├── 02_adam.smk
│   ├── 03_tlf.smk
│   └── 04_qc.smk
├── scripts/
│   ├── adam/                 # ADaM creation scripts (R)
│   │   ├── create_adsl.R
│   │   ├── create_adae.R
│   │   ├── create_advs.R
│   │   ├── create_adlbc.R
│   │   ├── create_adlbh.R
│   │   ├── create_adqsadas.R # Primary endpoint
│   │   └── create_adtte.R
│   ├── tlf/                  # TLF generation scripts (R)
│   │   ├── create_t_14_1_01.R  # Demographics
│   │   ├── create_t_14_2_01.R  # AE Overview
│   │   ├── create_t_14_3_01.R  # Primary Efficacy (ANCOVA)
│   │   └── create_t_14_6_01.R  # Vital Signs
│   └── qc/                   # Quality control scripts
│       ├── compare_datasets.R
│       └── generate_validation_summary.py
├── data/
│   ├── sdtm/                 # Source SDTM data (*.xpt)
│   ├── adam/                 # Generated ADaM datasets
│   └── tlf/                  # Generated TLF outputs (*.rtf)
├── specs/
│   ├── sdtm/                 # SDTM specifications
│   ├── adam/                 # ADaM specifications
│   └── metadata/             # Extracted metadata
├── tests/
│   ├── ground_truth/         # Reference datasets for QC
│   │   └── adam/             # PHUSE ADaM ground truth
│   └── benchmarks/           # Comparison reports
├── reports/
│   ├── qc/                   # Validation summaries
│   └── exceptions/           # Error reports
├── logs/                     # Execution logs
├── envs/
│   └── r_env.yaml            # Conda environment
├── skills/                   # Document parsing skills
│   ├── protocol/
│   └── sap/
└── requirements.txt          # Python dependencies
```

## ADaM Datasets

| Dataset | Description | Key Variables |
|---------|-------------|---------------|
| ADSL | Subject Level | TRT01P, SAFFL, ITTFL, EFFFL |
| ADAE | Adverse Events | TRTEMFL, ASEV, AREL |
| ADVS | Vital Signs | BASE, CHG, AVISIT |
| ADLBC | Lab Chemistry | ANRIND, SHIFT1 |
| ADLBH | Lab Hematology | ANRIND, SHIFT1 |
| ADQSADAS | ADAS-Cog Efficacy | **PRIMARY** - CHG, LOCF |
| ADTTE | Time to Event | AVAL, CNSR |

## Tables, Listings, Figures

| TLF ID | Title | Population |
|--------|-------|------------|
| 14-1.01 | Summary of Demographic and Baseline Characteristics | ITT |
| 14-2.01 | Overall Summary of Adverse Events | Safety |
| **14-3.01** | **ADAS-Cog(11) - Change from Baseline to Week 24** | **Efficacy** |
| 14-6.01 | Summary of Vital Signs | Safety |

## Primary Efficacy Analysis

Table 14-3.01 presents the primary efficacy analysis:

- **Endpoint:** ADAS-Cog(11) change from baseline to Week 24
- **Method:** ANCOVA with LOCF
- **Model:** `CHG = TRT01P + BASE + SITEGR1`
- **Contrasts:** Xanomeline Low vs Placebo, Xanomeline High vs Placebo

## Quality Control

The pipeline compares generated datasets against PHUSE ground truth:

```bash
# Run QC comparisons
snakemake benchmark --cores 4

# View validation summary
open reports/qc/validation_summary.html
```

### Success Criteria
- ADaM variable match rate: >95%
- TLF cell accuracy: >99%
- Population counts: 100% match

## Configuration

Edit `config/config.yaml` to customize:
- Treatment arms
- SDTM domains to process
- ADaM datasets to generate
- TLF outputs
- Visit windows
- Population definitions

## Exception Handling

Pipeline failures are automatically captured:
- Error reports saved to `reports/exceptions/`
- Logs available in `logs/` directory
- `onerror` handler triggers notifications

## Future Enhancements

- [ ] Vision model integration for PDF parsing
- [ ] Protocol amendment impact analysis
- [ ] Define.xml generation
- [ ] Pinnacle 21 validation integration
- [ ] CSR assembly automation

## References

- [Admiral Documentation](https://pharmaverse.github.io/admiral/)
- [xportr Documentation](https://atorus-research.github.io/xportr/)
- [Tplyr Documentation](https://atorus-research.github.io/Tplyr/)
- [CDISC Pilot Project](https://www.cdisc.org/sdtmadam-pilot-project)
- [Snakemake Documentation](https://snakemake.readthedocs.io/)

## License

This project uses publicly available CDISC pilot data for educational and demonstration purposes.
