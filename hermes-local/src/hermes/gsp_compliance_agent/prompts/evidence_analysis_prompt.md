# LLM Evidence Analysis Prompt Contract

This prompt defines how the LLM (real or mock) analyzes GSP Standard candidates to propose evidence requirements.

## Input Format

```json
{
  "gsp_standard": {
    "gsp_standard_id": "GSP-COM-P04-SWM-001",
    "title": "GSP Standard GSP-COM-P04-SWM-001",
    "gsp_principle": "P04",
    "gsp_domain": "SWM",
    "requirement_statement": "GSP interprets the customer requirement as follows: Risk assessments shall be carried out...",
    "normative_force": "shall",
    "is_critical": true,
    "gsp_applicability": "all_facilities",
    "gsp_owner_function": "",
    "gsp_responsible_departments": [],
    "legal_dependency": "needs_legal_review",
    "notes": "..."
  },
  "linked_customer_requirements": [
    {
      "crm_id": "CRM-C5A-SAMPLE-001",
      "customer": "IKEA",
      "standard_family": "IWAY",
      "standard_version": "6.0",
      "clause_ref": "G 4.1",
      "original_text_excerpt": "Risk assessments shall be carried out for all routine and non-routine tasks..."
    }
  ],
  "principle_label": "P04 - Health and Safety",
  "domain_label": "SWM - Safe Working Methods"
}
```

## Task

You are an expert compliance analyst. Given a GSP Standard candidate and its linked customer requirement(s), analyze what evidence would reasonably demonstrate that the standard is implemented at a factory or facility.

### Rules (MANDATORY)

1. **Do NOT claim legal compliance.** State what evidence could demonstrate implementation, not that the facility is legally compliant.

2. **Do NOT generate SOP steps.** Describe WHAT evidence is needed, not HOW to produce it. Never write step-by-step instructions.

3. **Do NOT generate checklist items.** Evidence requirements are about proof of implementation, not verification checklists.

4. **Do NOT overstate certainty.** If the evidence requirement is ambiguous, say so and mark `needs_human_review: true`.

5. **Preserve traceability.** Every evidence proposal must reference the GSP standard ID and customer requirement.

6. **Return structured JSON only.** No prose before or after the JSON block.

7. **Be specific but not prescriptive.** "A documented risk assessment covering all routine and non-routine tasks, reviewed at least annually" is good. "Use Form RA-001 and file it in the EHS folder" is too prescriptive (that's SOP territory).

### Output JSON Schema

Return a JSON object with the following structure:

```json
{
  "gsp_standard_id": "GSP-COM-P04-SWM-001",
  "analysis_summary": "Brief interpretation of what the standard requires and what evidence would demonstrate compliance.",
  "proposed_evidence": [
    {
      "evidence_title": "Risk Assessment Register",
      "evidence_requirement_statement": "A documented risk assessment covering all routine and non-routine tasks that can pose a health or safety risk, reviewed at least annually and updated when processes change.",
      "evidence_type": "risk_assessment",
      "evidence_owner_function": "EHS",
      "evidence_responsible_department": "EHS Department",
      "evidence_frequency": "annually",
      "evidence_format": "document",
      "evidence_acceptance_criteria": "Risk assessment document that includes identified hazards, risk ratings, control measures, review dates, and authorised signatures. Must cover all identified tasks in the facility.",
      "evidence_retention_requirement": "Minimum 3 years or until next IWAY audit",
      "risk_level": "critical",
      "uncertainty_notes": "",
      "needs_human_review": false
    }
  ]
}
```

### Allowed Values

**evidence_type**: Must be one of:
- `policy_or_procedure`
- `work_instruction`
- `training_record`
- `attendance_or_system_export`
- `inspection_record`
- `maintenance_record`
- `risk_assessment`
- `permit_or_license`
- `monitoring_record`
- `incident_or_near_miss_record`
- `audit_record`
- `photo_or_visual_evidence`
- `supplier_or_subcontractor_record`
- `communication_record`
- `corrective_action_record`
- `other`
- `unknown`

**evidence_frequency**: Must be one of:
- `once`, `daily`, `weekly`, `monthly`, `quarterly`, `annually`, `per_shift`, `per_batch`, `as_needed`, `upon_request`, `ongoing`, `unknown`

**evidence_format**: Must be one of:
- `document`, `spreadsheet`, `photograph`, `video`, `system_export`, `signed_form`, `certificate`, `log_book`, `database_record`, `email`, `physical_sample`, `other`, `unknown`

**risk_level**: Must be one of:
- `critical`, `high`, `medium`, `low`, `unknown`

**evidence_owner_function**: Use standard function names like:
- `EHS`, `HR`, `Production`, `QA`, `Maintenance`, `Logistics`, `Training`, `Legal`, `Compliance`, `Administration`, `Management`

**normative_force interpretation**:
- `shall` = mandatory requirement → evidence is required
- `should` = recommended → evidence is advisable
- `may` = optional → evidence may be omitted

### Number of Evidence Proposals

Propose between **1 and 5** evidence requirements per GSP standard candidate.
- For simple, narrow requirements → 1 evidence item
- For complex, multi-part requirements → 2-5 items
- If the requirement is unclear → 1 item with `needs_human_review: true`

### Uncertainty Handling

- If the GSP statement could be interpreted multiple ways, note this in `uncertainty_notes`.
- If the requirement references legal standards that vary by jurisdiction, set `needs_human_review: true`.
- If you cannot determine an appropriate evidence type, use `unknown` and set `needs_human_review: true`.
