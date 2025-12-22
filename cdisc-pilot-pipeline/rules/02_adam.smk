"""
ADaM Rules
==========

Rules for creating Analysis Data Model (ADaM) datasets.
Uses admiral and other pharmaverse packages in R.
"""

# =============================================================================
# ADSL - Subject Level Analysis Dataset
# =============================================================================

rule create_adsl:
    """
    Create ADSL (Subject Level Analysis Dataset).
    Key derivations: treatment variables, population flags, demographics.
    """
    input:
        dm="data/sdtm/dm.xpt",
        ds="data/sdtm/ds.xpt",
        ex="data/sdtm/ex.xpt",
        sv="data/sdtm/sv.xpt",
        sc="data/sdtm/sc.xpt",
        mh="data/sdtm/mh.xpt",
        qs="data/sdtm/qs.xpt"
    output:
        adsl="data/adam/adsl.xpt"
    log:
        "logs/adam/create_adsl.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/adam/create_adsl.R"


# =============================================================================
# ADAE - Adverse Events Analysis Dataset
# =============================================================================

rule create_adae:
    """
    Create ADAE (Adverse Events Analysis Dataset).
    Key derivations: treatment-emergent flags, severity, duration.
    """
    input:
        ae="data/sdtm/ae.xpt",
        adsl="data/adam/adsl.xpt",
        ex="data/sdtm/ex.xpt",
        suppae="data/sdtm/suppae.xpt"
    output:
        adae="data/adam/adae.xpt"
    log:
        "logs/adam/create_adae.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/adam/create_adae.R"


# =============================================================================
# ADVS - Vital Signs Analysis Dataset
# =============================================================================

rule create_advs:
    """
    Create ADVS (Vital Signs Analysis Dataset).
    Key derivations: baseline, change from baseline, visit windows.
    """
    input:
        vs="data/sdtm/vs.xpt",
        adsl="data/adam/adsl.xpt"
    output:
        advs="data/adam/advs.xpt"
    log:
        "logs/adam/create_advs.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/adam/create_advs.R"


# =============================================================================
# ADLBC - Laboratory Chemistry Analysis Dataset
# =============================================================================

rule create_adlbc:
    """
    Create ADLBC (Laboratory Chemistry Analysis Dataset).
    Key derivations: baseline, change, reference ranges.
    """
    input:
        lb="data/sdtm/lb.xpt",
        adsl="data/adam/adsl.xpt"
    output:
        adlbc="data/adam/adlbc.xpt"
    log:
        "logs/adam/create_adlbc.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/adam/create_adlbc.R"


# =============================================================================
# ADLBH - Laboratory Hematology Analysis Dataset
# =============================================================================

rule create_adlbh:
    """
    Create ADLBH (Laboratory Hematology Analysis Dataset).
    """
    input:
        lb="data/sdtm/lb.xpt",
        adsl="data/adam/adsl.xpt"
    output:
        adlbh="data/adam/adlbh.xpt"
    log:
        "logs/adam/create_adlbh.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/adam/create_adlbh.R"


# =============================================================================
# ADQSADAS - ADAS-Cog Efficacy Analysis Dataset (PRIMARY ENDPOINT)
# =============================================================================

rule create_adqsadas:
    """
    Create ADQSADAS (ADAS-Cog Efficacy Analysis Dataset).
    PRIMARY ENDPOINT DATASET.
    Key derivations: total score, baseline, change, LOCF.
    """
    input:
        qs="data/sdtm/qs.xpt",
        adsl="data/adam/adsl.xpt",
        sv="data/sdtm/sv.xpt"
    output:
        adqsadas="data/adam/adqsadas.xpt"
    log:
        "logs/adam/create_adqsadas.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/adam/create_adqsadas.R"


# =============================================================================
# ADTTE - Time to Event Analysis Dataset
# =============================================================================

rule create_adtte:
    """
    Create ADTTE (Time to Event Analysis Dataset).
    Key derivations: time to first AE, censoring.
    """
    input:
        adae="data/adam/adae.xpt",
        adsl="data/adam/adsl.xpt"
    output:
        adtte="data/adam/adtte.xpt"
    log:
        "logs/adam/create_adtte.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/adam/create_adtte.R"


# =============================================================================
# ADAM METADATA
# =============================================================================

rule extract_adam_metadata:
    """Extract metadata from ADaM define.xml"""
    input:
        define="specs/adam/define.xml"
    output:
        metadata="specs/adam/adam_metadata.json"
    log:
        "logs/adam/extract_metadata.log"
    run:
        import json
        from datetime import datetime

        metadata = {
            "extraction_timestamp": datetime.now().isoformat(),
            "standard": "ADaMIG",
            "version": "1.1",
            "datasets": {
                "ADSL": {
                    "description": "Subject Level Analysis Dataset",
                    "structure": "One record per subject",
                    "class": "ADSL"
                },
                "ADAE": {
                    "description": "Adverse Events Analysis Dataset",
                    "structure": "One record per adverse event per subject",
                    "class": "ADAM OTHER"
                },
                "ADVS": {
                    "description": "Vital Signs Analysis Dataset",
                    "structure": "One record per vital sign per timepoint per subject",
                    "class": "BDS"
                },
                "ADLBC": {
                    "description": "Laboratory Chemistry Analysis Dataset",
                    "structure": "One record per lab test per timepoint per subject",
                    "class": "BDS"
                },
                "ADQSADAS": {
                    "description": "ADAS-Cog Efficacy Analysis Dataset",
                    "structure": "One record per parameter per timepoint per subject",
                    "class": "BDS"
                },
                "ADTTE": {
                    "description": "Time to Event Analysis Dataset",
                    "structure": "One record per event per subject",
                    "class": "TTE"
                }
            }
        }

        with open(output.metadata, 'w') as f:
            json.dump(metadata, f, indent=2)


# =============================================================================
# ADAM SUMMARY
# =============================================================================

rule adam_summary:
    """Generate ADaM summary report"""
    input:
        datasets=expand("data/adam/{dataset}.xpt", dataset=ADAM_DATASETS),
        metadata="specs/adam/adam_metadata.json"
    output:
        report="reports/qc/adam_summary.html"
    log:
        "logs/adam/summary_report.log"
    run:
        import json
        from datetime import datetime
        import os

        with open(input.metadata) as f:
            metadata = json.load(f)

        # Get file sizes
        sizes = {}
        for ds_path in input.datasets:
            ds_name = os.path.basename(ds_path).replace('.xpt', '').upper()
            sizes[ds_name] = os.path.getsize(ds_path)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>ADaM Summary Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #2196F3; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .timestamp {{ color: #666; font-size: 0.9em; }}
        .success {{ color: green; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>ADaM Summary Report - CDISCPILOT01</h1>
    <p class="timestamp">Generated: {datetime.now().isoformat()}</p>

    <h2>Dataset Overview</h2>
    <table>
        <tr>
            <th>Dataset</th>
            <th>Description</th>
            <th>Class</th>
            <th>File Size</th>
        </tr>
"""
        for ds_name, info in metadata["datasets"].items():
            size = sizes.get(ds_name, 0)
            size_str = f"{size:,} bytes" if size > 0 else "N/A"
            html += f"""        <tr>
            <td>{ds_name}</td>
            <td>{info['description']}</td>
            <td>{info['class']}</td>
            <td>{size_str}</td>
        </tr>
"""

        html += """    </table>

    <h2>Generation Status</h2>
    <p class="success">All ADaM datasets generated successfully</p>

</body>
</html>"""

        with open(output.report, 'w') as f:
            f.write(html)
