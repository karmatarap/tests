"""
TLF Rules
=========

Rules for creating Tables, Listings, and Figures.
Uses Tplyr, pharmaRTF, and other reporting packages in R.
"""

# =============================================================================
# TABLE 14-1.01 - Demographics
# =============================================================================

rule create_t_14_1_01:
    """
    Create Table 14-1.01: Summary of Demographic and Baseline Characteristics.
    Population: ITT (All randomized subjects)
    """
    input:
        adsl="data/adam/adsl.xpt"
    output:
        rtf="data/tlf/14-1.01.rtf"
    log:
        "logs/tlf/create_t_14_1_01.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/tlf/create_t_14_1_01.R"


# =============================================================================
# TABLE 14-2.01 - Adverse Events Overview
# =============================================================================

rule create_t_14_2_01:
    """
    Create Table 14-2.01: Overall Summary of Adverse Events.
    Population: Safety (Received at least one dose)
    """
    input:
        adae="data/adam/adae.xpt",
        adsl="data/adam/adsl.xpt"
    output:
        rtf="data/tlf/14-2.01.rtf"
    log:
        "logs/tlf/create_t_14_2_01.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/tlf/create_t_14_2_01.R"


# =============================================================================
# TABLE 14-3.01 - Primary Efficacy (ADAS-Cog)
# =============================================================================

rule create_t_14_3_01:
    """
    Create Table 14-3.01: ADAS-Cog(11) - Change from Baseline to Week 24 - LOCF.
    PRIMARY EFFICACY TABLE.
    Population: Efficacy (ITT with baseline and post-baseline)
    Analysis: ANCOVA with baseline and pooled site as covariates
    """
    input:
        adqsadas="data/adam/adqsadas.xpt",
        adsl="data/adam/adsl.xpt"
    output:
        rtf="data/tlf/14-3.01.rtf"
    log:
        "logs/tlf/create_t_14_3_01.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/tlf/create_t_14_3_01.R"


# =============================================================================
# TABLE 14-6.01 - Vital Signs
# =============================================================================

rule create_t_14_6_01:
    """
    Create Table 14-6.01: Summary of Vital Signs at Baseline and End of Treatment.
    Population: Safety
    """
    input:
        advs="data/adam/advs.xpt",
        adsl="data/adam/adsl.xpt"
    output:
        rtf="data/tlf/14-6.01.rtf"
    log:
        "logs/tlf/create_t_14_6_01.log"
    conda:
        "../envs/r_env.yaml"
    script:
        "../scripts/tlf/create_t_14_6_01.R"


# =============================================================================
# TLF SUMMARY
# =============================================================================

rule tlf_summary:
    """Generate TLF summary report"""
    input:
        tlfs=expand("data/tlf/{tlf}.rtf", tlf=TLFS)
    output:
        report="reports/qc/tlf_summary.html"
    log:
        "logs/tlf/summary_report.log"
    run:
        import os
        from datetime import datetime

        tlf_info = {
            "14-1.01": {
                "title": "Summary of Demographic and Baseline Characteristics",
                "population": "ITT",
                "type": "Table"
            },
            "14-2.01": {
                "title": "Overall Summary of Adverse Events",
                "population": "Safety",
                "type": "Table"
            },
            "14-3.01": {
                "title": "ADAS-Cog(11) - Change from Baseline to Week 24 - LOCF",
                "population": "Efficacy",
                "type": "Table"
            },
            "14-6.01": {
                "title": "Summary of Vital Signs at Baseline and End of Treatment",
                "population": "Safety",
                "type": "Table"
            }
        }

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>TLF Summary Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #9C27B0; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .timestamp {{ color: #666; font-size: 0.9em; }}
        .success {{ color: green; font-weight: bold; }}
        .primary {{ background-color: #FFF3E0 !important; }}
    </style>
</head>
<body>
    <h1>TLF Summary Report - CDISCPILOT01</h1>
    <p class="timestamp">Generated: {datetime.now().isoformat()}</p>

    <h2>Tables, Listings, and Figures</h2>
    <table>
        <tr>
            <th>TLF ID</th>
            <th>Title</th>
            <th>Type</th>
            <th>Population</th>
            <th>File Size</th>
        </tr>
"""
        for tlf_path in input.tlfs:
            tlf_id = os.path.basename(tlf_path).replace('.rtf', '')
            info = tlf_info.get(tlf_id, {"title": "Unknown", "population": "Unknown", "type": "Unknown"})
            size = os.path.getsize(tlf_path) if os.path.exists(tlf_path) else 0
            row_class = "primary" if tlf_id == "14-3.01" else ""
            html += f"""        <tr class="{row_class}">
            <td>{tlf_id}</td>
            <td>{info['title']}</td>
            <td>{info['type']}</td>
            <td>{info['population']}</td>
            <td>{size:,} bytes</td>
        </tr>
"""

        html += """    </table>

    <h2>Notes</h2>
    <ul>
        <li>Highlighted row indicates primary efficacy table</li>
        <li>All tables generated in RTF format</li>
    </ul>

    <h2>Generation Status</h2>
    <p class="success">All TLFs generated successfully</p>

</body>
</html>"""

        with open(output.report, 'w') as f:
            f.write(html)
