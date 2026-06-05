# LLM Source Reconciliation Prompt Contract

This prompt defines how the LLM compares PDF-extracted requirement candidates against curated baseline records.

## Input

```json
{
  "pdf_candidate": {
    "id": "CRM-PDF-EXTRACT-001",
    "clause_ref": "G 4.1",
    "requirement_text": "Risk assessments shall be carried out for all routine and non-routine tasks...",
    "section": "G 4 Health and Safety"
  },
  "curated_baseline": {
    "curated_baseline_id": "BL-IWAY-001",
    "requirement_code": "G 4.1",
    "requirement_text": "Risk assessments shall be carried out for all routine and non-routine tasks...",
    "level": "shall",
    "section_name": "Health and Safety"
  },
  "normative_signals": {
    "pdf_code_normalized": "G4.1",
    "baseline_code_normalized": "G4.1",
    "text_similarity": 0.95
  }
}
```

## Task

Compare the PDF-extracted candidate and the curated baseline record. Determine whether they represent the same requirement semantically.

### Rules

1. Return structured JSON only.
2. Do NOT approve anything — recommendations only.
3. If uncertain, set `needs_human_review`.
4. Identify ID mismatches (LT vs T prefix, number transposition).
5. Identify noise (title, footer, glossary, definition, incomplete text).
6. Identify level mismatches (shall vs should).
7. Identify section mismatches.
8. Preserve traceability to both source records.

### Output JSON

```json
{
  "comparison_status": "exact_match",
  "confidence": 0.95,
  "recommended_action": "confirm_requirement",
  "reasoning_summary": "Both records refer to G 4.1 risk assessment. Text is semantically identical.",
  "code_match_signals": {
    "pdf_code": "G 4.1",
    "baseline_code": "G 4.1",
    "normalized_match": true
  }
}
```

### Comparison Status Values

- `exact_match` — Text and code are semantically equivalent.
- `text_similar_id_match` — Text matches but code format differs (e.g., LT vs T).
- `id_mismatch` — Code differs, text may or may not match.
- `missing_in_pdf_extraction` — Present in baseline but not in PDF extraction.
- `extra_in_pdf_extraction` — Present in PDF extraction but not in baseline (likely noise).
- `level_mismatch` — Text similar but requirement level differs (shall vs should).
- `section_mismatch` — Text similar but section/chapter differs.
- `text_incomplete` — PDF text is truncated or incomplete compared to baseline.
- `duplicate_candidate` — Same requirement appears multiple times in PDF extraction.
- `needs_human_review` — Cannot determine with confidence.

### Recommended Action Values

- `confirm_requirement` — Match is reliable, can be confirmed.
- `correct_pdf_candidate` — Baseline is correct; use baseline text.
- `use_curated_baseline` — Baseline is authoritative; use baseline version.
- `reject_pdf_candidate` — PDF item is noise or incorrect.
- `split_required` — Single PDF item covers multiple baseline items.
- `merge_required` — Multiple PDF items map to one baseline item.
- `level_review_required` — Level mismatch needs human review.
- `needs_human_review` — Cannot determine.
