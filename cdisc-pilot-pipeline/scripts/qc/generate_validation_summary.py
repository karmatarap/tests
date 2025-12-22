#!/usr/bin/env python3
"""
============================================================================
Validation Summary Generator
============================================================================

Aggregates all comparison reports into a single validation summary.
Provides overall pipeline quality metrics.
============================================================================
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

def extract_metrics_from_html(html_path):
    """Extract key metrics from a comparison HTML report."""
    try:
        with open(html_path, 'r') as f:
            content = f.read()

        # Extract match rates using regex
        var_match = re.search(r'(\d+\.?\d*)%</div>\s*<div class="metric-label">Variable Match Rate', content)
        record_match = re.search(r'(\d+\.?\d*)%</div>\s*<div class="metric-label">Record Match Rate', content)
        status = re.search(r'(PASS|DIFFERENCES)</div>\s*<div class="metric-label">Overall Status', content)

        return {
            'var_match_rate': float(var_match.group(1)) if var_match else 0.0,
            'record_match_rate': float(record_match.group(1)) if record_match else 0.0,
            'status': status.group(1) if status else 'UNKNOWN'
        }
    except Exception as e:
        return {
            'var_match_rate': 0.0,
            'record_match_rate': 0.0,
            'status': 'ERROR',
            'error': str(e)
        }


def main():
    # Get file paths from Snakemake
    input_files = {
        'adsl': snakemake.input.adsl_cmp,
        'adae': snakemake.input.adae_cmp,
        'advs': snakemake.input.advs_cmp,
        'adqsadas': snakemake.input.adqsadas_cmp,
        'adtte': snakemake.input.adtte_cmp,
        'sdtm_summary': snakemake.input.sdtm_summary,
        'adam_summary': snakemake.input.adam_summary,
        'tlf_summary': snakemake.input.tlf_summary
    }
    output_report = snakemake.output.report
    log_file = snakemake.log[0]

    # Start logging
    with open(log_file, 'w') as log:
        log.write("Validation Summary Generation Log\n")
        log.write("==================================\n")
        log.write(f"Start time: {datetime.now().isoformat()}\n\n")

        # Extract metrics from each comparison report
        comparison_files = ['adsl', 'adae', 'advs', 'adqsadas', 'adtte']
        metrics = {}

        log.write("Extracting metrics from comparison reports...\n")
        for ds in comparison_files:
            if ds in input_files:
                metrics[ds.upper()] = extract_metrics_from_html(input_files[ds])
                log.write(f"  {ds.upper()}: {metrics[ds.upper()]}\n")

        # Calculate overall statistics
        total_datasets = len(metrics)
        passed_datasets = sum(1 for m in metrics.values() if m.get('status') == 'PASS')
        avg_var_match = sum(m.get('var_match_rate', 0) for m in metrics.values()) / max(total_datasets, 1)
        avg_record_match = sum(m.get('record_match_rate', 0) for m in metrics.values()) / max(total_datasets, 1)

        overall_status = 'PASS' if passed_datasets == total_datasets else 'FAIL'

        log.write(f"\nOverall Statistics:\n")
        log.write(f"  Total datasets: {total_datasets}\n")
        log.write(f"  Passed: {passed_datasets}\n")
        log.write(f"  Avg variable match: {avg_var_match:.1f}%\n")
        log.write(f"  Avg record match: {avg_record_match:.1f}%\n")
        log.write(f"  Overall status: {overall_status}\n")

        # Generate HTML report
        html_content = f'''<!DOCTYPE html>
<html>
<head>
    <title>CDISC Pilot Pipeline - Validation Summary</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f9f9f9; }}
        h1 {{ color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
        h2 {{ color: #666; margin-top: 30px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .summary-box {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin: 20px 0;
        }}
        .pass {{ color: #28a745; }}
        .fail {{ color: #dc3545; }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .metric {{ font-size: 36px; font-weight: bold; }}
        .metric-label {{ font-size: 14px; color: #666; margin-top: 10px; }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{ background: #4CAF50; color: white; font-weight: 600; }}
        tr:hover {{ background: #f5f5f5; }}
        .status-badge {{
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 12px;
        }}
        .status-pass {{ background: #d4edda; color: #155724; }}
        .status-fail {{ background: #f8d7da; color: #721c24; }}
        .study-header {{
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
        }}
        .study-header h1 {{ color: white; border: none; margin: 0; }}
        .study-header p {{ margin: 10px 0 0; opacity: 0.9; }}
        .pipeline-stage {{
            display: inline-block;
            padding: 8px 16px;
            margin: 5px;
            background: #e9ecef;
            border-radius: 20px;
            font-size: 14px;
        }}
        .pipeline-stage.complete {{ background: #d4edda; color: #155724; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="study-header">
            <h1>CDISC Pilot Pipeline - Validation Summary</h1>
            <p>Study: CDISCPILOT01 | Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>

        <div class="summary-box">
            <h2>Overall Pipeline Status</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric {'pass' if overall_status == 'PASS' else 'fail'}">{overall_status}</div>
                    <div class="metric-label">Overall Status</div>
                </div>
                <div class="metric-card">
                    <div class="metric">{passed_datasets}/{total_datasets}</div>
                    <div class="metric-label">Datasets Passed</div>
                </div>
                <div class="metric-card">
                    <div class="metric">{avg_var_match:.1f}%</div>
                    <div class="metric-label">Avg Variable Match</div>
                </div>
                <div class="metric-card">
                    <div class="metric">{avg_record_match:.1f}%</div>
                    <div class="metric-label">Avg Record Match</div>
                </div>
            </div>
        </div>

        <div class="summary-box">
            <h2>Pipeline Stages</h2>
            <p>
                <span class="pipeline-stage complete">SDTM Validation</span>
                <span class="pipeline-stage complete">ADaM Generation</span>
                <span class="pipeline-stage complete">TLF Production</span>
                <span class="pipeline-stage complete">QC Comparison</span>
            </p>
        </div>

        <div class="summary-box">
            <h2>Dataset Comparison Results</h2>
            <table>
                <tr>
                    <th>Dataset</th>
                    <th>Variable Match</th>
                    <th>Record Match</th>
                    <th>Status</th>
                </tr>
'''

        for ds_name, ds_metrics in metrics.items():
            status_class = 'status-pass' if ds_metrics.get('status') == 'PASS' else 'status-fail'
            html_content += f'''                <tr>
                    <td><strong>{ds_name}</strong></td>
                    <td>{ds_metrics.get('var_match_rate', 0):.1f}%</td>
                    <td>{ds_metrics.get('record_match_rate', 0):.1f}%</td>
                    <td><span class="status-badge {status_class}">{ds_metrics.get('status', 'UNKNOWN')}</span></td>
                </tr>
'''

        html_content += '''            </table>
        </div>

        <div class="summary-box">
            <h2>Key Tables Generated</h2>
            <table>
                <tr>
                    <th>Table ID</th>
                    <th>Title</th>
                    <th>Population</th>
                </tr>
                <tr>
                    <td>14-1.01</td>
                    <td>Summary of Demographic and Baseline Characteristics</td>
                    <td>ITT</td>
                </tr>
                <tr>
                    <td>14-2.01</td>
                    <td>Overall Summary of Adverse Events</td>
                    <td>Safety</td>
                </tr>
                <tr>
                    <td><strong>14-3.01</strong></td>
                    <td><strong>ADAS-Cog(11) - Change from Baseline to Week 24 (PRIMARY)</strong></td>
                    <td><strong>Efficacy</strong></td>
                </tr>
                <tr>
                    <td>14-6.01</td>
                    <td>Summary of Vital Signs at Baseline and End of Treatment</td>
                    <td>Safety</td>
                </tr>
            </table>
        </div>

        <div class="summary-box">
            <h2>Detailed Reports</h2>
            <ul>
'''

        for ds in comparison_files:
            html_content += f'''                <li><a href="../tests/benchmarks/{ds}_comparison.html">{ds.upper()} Comparison Report</a></li>
'''

        html_content += f'''            </ul>
        </div>

        <div class="summary-box">
            <h2>Pipeline Information</h2>
            <table>
                <tr><td><strong>Study ID</strong></td><td>CDISCPILOT01</td></tr>
                <tr><td><strong>Pipeline Version</strong></td><td>1.0.0</td></tr>
                <tr><td><strong>Validation Date</strong></td><td>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
                <tr><td><strong>Primary Endpoint</strong></td><td>ADAS-Cog(11) Change from Baseline to Week 24</td></tr>
            </table>
        </div>
    </div>
</body>
</html>'''

        # Write HTML file
        with open(output_report, 'w') as f:
            f.write(html_content)

        log.write(f"\nOutput: {output_report}\n")
        log.write(f"End time: {datetime.now().isoformat()}\n")


if __name__ == "__main__":
    main()
