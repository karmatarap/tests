# Protocol Parsing Skill

## Purpose
Extract structured metadata from clinical trial protocol documents (PDF format).

## Input
- Protocol PDF document
- Study identifier (if known)

## Output Schema
```json
{
  "study_id": "string",
  "study_title": "string",
  "sponsor": "string",
  "phase": "string (I, II, III, IV)",
  "indication": "string",
  "objectives": {
    "primary": "string",
    "secondary": ["string"]
  },
  "treatment_arms": [
    {
      "name": "string",
      "description": "string",
      "dose": "string (optional)"
    }
  ],
  "key_inclusion_criteria": ["string"],
  "key_exclusion_criteria": ["string"],
  "planned_enrollment": "number",
  "study_duration": "string"
}
```

## Extraction Instructions

### Study Identification
1. Look for "Protocol Number" or "Study ID" in header/title page
2. Extract sponsor name from cover page
3. Identify phase from title or objectives section

### Objectives
1. Locate "Objectives" or "Study Objectives" section
2. Primary objective is typically first, marked explicitly
3. Secondary objectives follow, may be numbered

### Treatment Arms
1. Find "Study Design" or "Treatment" section
2. Look for tables showing arm descriptions
3. Extract dose, route, frequency information

### Inclusion/Exclusion Criteria
1. Locate "Eligibility Criteria" section
2. Key criteria often marked with asterisks or bold
3. Prioritize age, diagnosis, disease stage criteria

### Schedule of Activities
1. Identify table format in "Study Procedures" section
2. Extract visit names, timing, and procedures
3. Note visit windows if specified

## Example Prompts

### For Cover Page Analysis
```
Extract the study ID, sponsor name, phase, and study title from this protocol cover page.
```

### For Objectives Section
```
Identify the primary and secondary objectives from this section.
The primary objective typically mentions the main efficacy endpoint.
```

### For Treatment Arms
```
List all treatment arms including placebo. For each arm, extract:
- Arm name
- Drug/intervention
- Dose and frequency
- Route of administration
```

## Validation Rules
- Study ID should match expected format (sponsor prefix + number)
- Phase should be I, II, III, or IV
- At least one treatment arm required
- Primary objective must be present
