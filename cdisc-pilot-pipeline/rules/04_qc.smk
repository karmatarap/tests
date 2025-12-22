"""
QC Rules
========

Rules for quality control and validation.
Compares generated datasets against ground truth.
"""

# =============================================================================
# DATASET COMPARISON
# =============================================================================

rule compare_adsl:
    """Compare generated ADSL to ground truth"""
    input:
        generated="data/adam/adsl.xpt",
        expected="tests/ground_truth/adam/adsl.xpt"
    output:
        report="tests/benchmarks/adsl_comparison.html"
    log:
        "logs/qc/compare_adsl.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/qc/compare_datasets.R"


rule compare_adae:
    """Compare generated ADAE to ground truth"""
    input:
        generated="data/adam/adae.xpt",
        expected="tests/ground_truth/adam/adae.xpt"
    output:
        report="tests/benchmarks/adae_comparison.html"
    log:
        "logs/qc/compare_adae.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/qc/compare_datasets.R"


rule compare_advs:
    """Compare generated ADVS to ground truth"""
    input:
        generated="data/adam/advs.xpt",
        expected="tests/ground_truth/adam/advs.xpt"
    output:
        report="tests/benchmarks/advs_comparison.html"
    log:
        "logs/qc/compare_advs.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/qc/compare_datasets.R"


rule compare_adqsadas:
    """Compare generated ADQSADAS to ground truth"""
    input:
        generated="data/adam/adqsadas.xpt",
        expected="tests/ground_truth/adam/adqsadas.xpt"
    output:
        report="tests/benchmarks/adqsadas_comparison.html"
    log:
        "logs/qc/compare_adqsadas.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/qc/compare_datasets.R"


rule compare_adtte:
    """Compare generated ADTTE to ground truth"""
    input:
        generated="data/adam/adtte.xpt",
        expected="tests/ground_truth/adam/adtte.xpt"
    output:
        report="tests/benchmarks/adtte_comparison.html"
    log:
        "logs/qc/compare_adtte.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/qc/compare_datasets.R"


# =============================================================================
# VALIDATION SUMMARY
# =============================================================================

rule validation_summary:
    """Generate overall validation summary report"""
    input:
        adsl_cmp="tests/benchmarks/adsl_comparison.html",
        adae_cmp="tests/benchmarks/adae_comparison.html",
        advs_cmp="tests/benchmarks/advs_comparison.html",
        adqsadas_cmp="tests/benchmarks/adqsadas_comparison.html",
        adtte_cmp="tests/benchmarks/adtte_comparison.html",
        sdtm_summary="reports/qc/sdtm_summary.html",
        adam_summary="reports/qc/adam_summary.html",
        tlf_summary="reports/qc/tlf_summary.html"
    output:
        report="reports/qc/validation_summary.html"
    log:
        "logs/qc/validation_summary.log"
    script:
        "../scripts/qc/generate_validation_summary.py"


# =============================================================================
# PINNACLE 21 VALIDATION (FUTURE)
# =============================================================================

rule run_p21_validation:
    """
    Run Pinnacle 21 validation on SDTM/ADaM.
    STUB: For future integration with P21 CLI.
    """
    input:
        adam=expand("data/adam/{dataset}.xpt", dataset=ADAM_DATASETS)
    output:
        report="reports/qc/p21_validation.html"
    log:
        "logs/qc/p21_validation.log"
    run:
        from datetime import datetime

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Pinnacle 21 Validation Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .stub {{ color: #999; font-style: italic; }}
    </style>
</head>
<body>
    <h1>Pinnacle 21 Validation Report</h1>
    <p class="stub">STUB: Pinnacle 21 integration pending</p>
    <p>Generated: {datetime.now().isoformat()}</p>
    <p>This report will show P21 Community validation results when integrated.</p>
</body>
</html>"""

        with open(output.report, 'w') as f:
            f.write(html)


# =============================================================================
# DEFINE.XML GENERATION (FUTURE)
# =============================================================================

rule generate_define_xml:
    """
    Generate define.xml for submission package.
    STUB: For future implementation.
    """
    input:
        adam=expand("data/adam/{dataset}.xpt", dataset=ADAM_DATASETS),
        metadata="specs/adam/adam_metadata.json"
    output:
        define="reports/submission/define.xml"
    log:
        "logs/qc/generate_define.log"
    run:
        from datetime import datetime
        from pathlib import Path

        Path(output.define).parent.mkdir(parents=True, exist_ok=True)

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- STUB: Define.xml generation pending -->
<!-- Generated: {datetime.now().isoformat()} -->
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3">
    <Study OID="CDISCPILOT01">
        <GlobalVariables>
            <StudyName>CDISC Pilot Study</StudyName>
        </GlobalVariables>
    </Study>
</ODM>"""

        with open(output.define, 'w') as f:
            f.write(xml)
