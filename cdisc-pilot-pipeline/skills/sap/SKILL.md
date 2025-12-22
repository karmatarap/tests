# Statistical Analysis Plan (SAP) Parsing Skill

## Purpose
Extract analysis specifications from SAP documents for automated TLF generation.

## Input
- SAP PDF document
- Protocol metadata (optional, for cross-validation)

## Output Schema
```json
{
  "study_id": "string",
  "sap_version": "string",
  "primary_analysis": {
    "endpoint": "string",
    "method": "string (ANCOVA, MMRM, etc.)",
    "model": "string (model specification)",
    "missing_data": "string (LOCF, MMRM, MI, etc.)",
    "alpha": "number",
    "hypothesis": "string (one-sided, two-sided)"
  },
  "populations": {
    "ITT": "string (definition)",
    "Safety": "string (definition)",
    "Per_Protocol": "string (definition)",
    "Efficacy": "string (definition)"
  },
  "analysis_visits": [
    {
      "visit": "string",
      "window_low": "number (days)",
      "window_high": "number (days)"
    }
  ],
  "subgroups": ["string"],
  "multiplicity_adjustment": "string",
  "sensitivity_analyses": ["string"]
}
```

## Extraction Instructions

### Primary Analysis
1. Find "Primary Efficacy Analysis" or "Primary Endpoint Analysis"
2. Extract statistical method (ANCOVA, MMRM, mixed model)
3. Identify covariates and stratification factors
4. Note missing data handling approach

### Analysis Populations
1. Locate "Analysis Populations" or "Study Populations" section
2. Extract exact definitions for each population
3. Note flag variable names if mentioned (ITTFL, SAFFL, etc.)

### Visit Windows
1. Find "Analysis Windows" or "Visit Windowing" table
2. Extract target day and window bounds
3. Note rules for multiple observations within window

### Multiplicity
1. Identify section on "Multiple Comparisons" or "Multiplicity"
2. Extract adjustment method (Hochberg, Bonferroni, etc.)
3. Note which comparisons are adjusted

## Example Prompts

### For Primary Analysis
```
Extract the primary analysis specifications including:
- Statistical method
- Full model specification
- Missing data approach
- Significance level
```

### For Population Definitions
```
List all analysis populations with their exact definitions.
Include the variable/flag name used to identify each population.
```

### For Visit Windows
```
Extract the visit windowing rules as a table:
| Visit | Target Day | Window (days) |
```

## Validation Rules
- Primary endpoint must match protocol
- Population definitions should be unambiguous
- Alpha level typically 0.05 (two-sided) or 0.025 (one-sided)
- Visit windows should not overlap
