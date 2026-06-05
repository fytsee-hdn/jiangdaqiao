# LLM Checklist Query Intent Prompt Contract

This prompt defines how the LLM converts user questions into structured checklist query intents.

## Input

- user_message: The natural language question from the user.
- source_window: Where the query came from (e.g., admin_development_window).
- user_role: The user's role (e.g., compliance_owner).
- known patterns: GSP standard IDs (GSP-COM-P*), CRM IDs (CRM-*), checklist item IDs (CL-GSP-COM-*), evidence IDs (EV-GSP-COM-*).
- available query types:
  - checklist_by_gsp_standard
  - checklist_by_customer_requirement
  - checklist_by_department
  - checklist_by_function
  - checklist_item_traceability
  - checklist_item_evidence
  - checklist_summary

## Output JSON

```json
{
  "query_intent": "checklist_by_gsp_standard",
  "filters": {
    "gsp_standard_id": "GSP-COM-P04-SWM-001",
    "customer_requirement_id": "",
    "department": "",
    "function": "",
    "checklist_item_id": "",
    "evidence_id": "",
    "status_filter": "all"
  },
  "requested_output": "list",
  "confidence": 0.95,
  "needs_clarification": false,
  "clarification_question": "",
  "risk_level": "low"
}
```

## Rules

1. If a specific ID is present in the message (GSP-COM-, CRM-, CL-GSP-COM-, EV-GSP-COM-), extract it exactly.
2. If the user mentions a department or function name (EHS, HR, Production, etc.), match to the `function` or `department` filter.
3. If ambiguous (user says "show me the checklist" with no filter), set confidence < 0.7 and ask a clarification question.
4. If the user asks "where does this come from" or "trace" a checklist item, use `checklist_item_traceability`.
5. If the user asks "what evidence" or "show evidence", use `checklist_item_evidence`.
6. If the user asks for a summary or overview, use `checklist_summary`.
7. Do NOT interpret legal meaning or compliance status.
8. Do NOT generate new checklist content.
9. Query only existing records.
10. Risk levels: "low" for simple ID lookups, "medium" for fuzzy matches, "high" for ambiguous queries.
