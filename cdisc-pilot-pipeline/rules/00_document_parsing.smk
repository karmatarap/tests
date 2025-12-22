"""
Document Parsing Rules
======================

Rules for extracting metadata from protocol, SAP, and other study documents.
For MVP, these are stub rules that use pre-created JSON metadata files.
Future: Integration with vision models for automated extraction.
"""

# =============================================================================
# PROTOCOL PARSING
# =============================================================================

rule parse_protocol:
    """
    Parse protocol document to extract study metadata.
    STUB: Uses pre-created metadata file.
    FUTURE: Vision model integration for PDF parsing.
    """
    input:
        protocol="documents/protocol/protocol.pdf"
    output:
        metadata="specs/metadata/protocol_metadata.json"
    log:
        "logs/document_parsing/parse_protocol.log"
    run:
        import json
        from datetime import datetime

        # Stub metadata for CDISCPILOT01
        metadata = {
            "extraction_timestamp": datetime.now().isoformat(),
            "extraction_method": "manual_stub",
            "study_id": "CDISCPILOT01",
            "study_title": "Safety and Efficacy of the Xanomeline Transdermal Therapeutic System (TTS) in Patients with Mild to Moderate Alzheimer's Disease",
            "sponsor": "CDISC Pilot Project",
            "phase": "Phase III",
            "indication": "Alzheimer's Disease",
            "objectives": {
                "primary": "To determine if there is a statistically significant relationship between the treatment groups and the change from baseline in ADAS-Cog(11) score at Week 24",
                "secondary": [
                    "To evaluate safety and tolerability",
                    "To assess change in CIBIC+ score"
                ]
            },
            "treatment_arms": [
                {"name": "Placebo", "description": "Matching placebo TTS"},
                {"name": "Xanomeline Low Dose", "dose": "54 mg/day TTS"},
                {"name": "Xanomeline High Dose", "dose": "81 mg/day TTS"}
            ],
            "key_inclusion_criteria": [
                "Age 50-90 years",
                "Diagnosis of probable Alzheimer's Disease (NINCDS/ADRDA criteria)",
                "MMSE score 10-26",
                "Modified Hachinski score <= 4"
            ],
            "planned_enrollment": 300,
            "study_duration": "26 weeks treatment + 30 day follow-up"
        }

        with open(output.metadata, 'w') as f:
            json.dump(metadata, f, indent=2)

        with open(log[0], 'w') as logf:
            logf.write(f"Protocol metadata extracted at {datetime.now().isoformat()}\n")
            logf.write("Method: manual_stub\n")


rule parse_sap:
    """
    Parse Statistical Analysis Plan to extract analysis specifications.
    STUB: Uses pre-created metadata file.
    """
    input:
        sap="documents/sap/sap.pdf"
    output:
        metadata="specs/metadata/sap_metadata.json"
    log:
        "logs/document_parsing/parse_sap.log"
    run:
        import json
        from datetime import datetime

        metadata = {
            "extraction_timestamp": datetime.now().isoformat(),
            "extraction_method": "manual_stub",
            "primary_analysis": {
                "endpoint": "ADAS-Cog(11) change from baseline to Week 24",
                "method": "ANCOVA",
                "model": "CHG = TRT01P + BASE + SITEGR1",
                "missing_data": "LOCF",
                "alpha": 0.05,
                "hypothesis": "two-sided"
            },
            "populations": {
                "ITT": "All randomized subjects",
                "Safety": "All subjects who received at least one dose",
                "Efficacy": "ITT with baseline and post-baseline efficacy"
            },
            "multiplicity_adjustment": "None for primary; Hochberg for secondary",
            "subgroups": ["Age (<65, >=65)", "Sex", "Race", "Baseline severity"]
        }

        with open(output.metadata, 'w') as f:
            json.dump(metadata, f, indent=2)


rule extract_endpoints:
    """Extract endpoint definitions from protocol/SAP"""
    input:
        protocol_meta="specs/metadata/protocol_metadata.json",
        sap_meta="specs/metadata/sap_metadata.json"
    output:
        endpoints="specs/metadata/endpoints.json"
    run:
        import json

        endpoints = {
            "primary": {
                "name": "ADAS-Cog(11)",
                "paramcd": "ACTOT",
                "description": "Alzheimer's Disease Assessment Scale - Cognitive Subscale (11 items)",
                "analysis_variable": "CHG",
                "baseline_variable": "BASE",
                "timepoint": "Week 24",
                "method": "ANCOVA with LOCF"
            },
            "secondary": [
                {
                    "name": "CIBIC+",
                    "paramcd": "CIBIC",
                    "description": "Clinician's Interview-Based Impression of Change plus caregiver input"
                },
                {
                    "name": "NPI-X",
                    "paramcd": "NPIX",
                    "description": "Neuropsychiatric Inventory"
                }
            ]
        }

        with open(output.endpoints, 'w') as f:
            json.dump(endpoints, f, indent=2)


rule extract_visit_schedule:
    """Extract visit schedule from protocol"""
    input:
        protocol_meta="specs/metadata/protocol_metadata.json"
    output:
        visits="specs/metadata/visit_schedule.json"
    run:
        import json

        visits = config["visits"]  # Use visits from config.yaml

        with open(output.visits, 'w') as f:
            json.dump({"visits": visits}, f, indent=2)


rule extract_populations:
    """Extract population definitions"""
    input:
        sap_meta="specs/metadata/sap_metadata.json"
    output:
        populations="specs/metadata/populations.json"
    run:
        import json

        populations = config["populations"]  # Use populations from config.yaml

        with open(output.populations, 'w') as f:
            json.dump({"populations": populations}, f, indent=2)


# =============================================================================
# DOCUMENT CHANGE DETECTION (FUTURE)
# =============================================================================

rule detect_document_changes:
    """
    Detect changes between protocol versions.
    FUTURE: Compare PDFs/extracted metadata to identify amendments.
    """
    input:
        current="documents/protocol/protocol.pdf",
        previous="documents/protocol/protocol_previous.pdf"
    output:
        changes="specs/metadata/protocol_changes.json"
    log:
        "logs/document_parsing/detect_changes.log"
    run:
        import json
        from datetime import datetime

        # Stub: No changes detected
        changes = {
            "detection_timestamp": datetime.now().isoformat(),
            "current_version": "1.0",
            "previous_version": "N/A",
            "changes_detected": False,
            "changes": []
        }

        with open(output.changes, 'w') as f:
            json.dump(changes, f, indent=2)


rule analyze_impact:
    """
    Analyze impact of document changes on downstream analyses.
    FUTURE: Map changes to affected ADaM/TLF outputs.
    """
    input:
        changes="specs/metadata/protocol_changes.json"
    output:
        impact="reports/qc/change_impact_analysis.json"
    run:
        import json
        from datetime import datetime

        impact = {
            "analysis_timestamp": datetime.now().isoformat(),
            "changes_reviewed": 0,
            "affected_datasets": [],
            "affected_tlfs": [],
            "requires_rerun": False,
            "recommendations": []
        }

        with open(output.impact, 'w') as f:
            json.dump(impact, f, indent=2)
