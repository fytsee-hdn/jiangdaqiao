"""
source_reconciliation_guard.py — P8B workflow guard: blocks C5A for PDF-only sources.

Ensures PDF-extracted requirements have curated baseline comparison
and reconciliation before they can be used for GSP Standard derivation.
"""
from __future__ import annotations

import json
import os
from typing import List

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import resolve_compliance_path

_SOURCE_REGISTER_PATH = resolve_compliance_path("source_register/source_register.jsonl")
_BASELINE_PATH = resolve_compliance_path("curated_baselines/curated_baseline.jsonl")
_RECONCILIATION_PATH = resolve_compliance_path("source_reconciliation/source_reconciliation.jsonl")
_CRM_PATH = resolve_compliance_path("customer_requirements/customer_requirement_master.jsonl")


def _load_jsonl(path: str) -> list:
    records = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return records


def is_pdf_source(source_record: dict) -> bool:
    filename = (source_record.get("source_file_path") or source_record.get("filename") or "").lower()
    return filename.endswith(".pdf") or source_record.get("source_type", "").lower() == "pdf"


def requires_curated_baseline(source_record: dict) -> bool:
    return is_pdf_source(source_record)


def has_curated_baseline(source_id: str) -> bool:
    baselines = _load_jsonl(_BASELINE_PATH)
    return any(b.get("source_id") == source_id for b in baselines)


def has_reconciliation_report(source_id: str) -> bool:
    reconciliations = _load_jsonl(_RECONCILIATION_PATH)
    return any(r.get("source_id") == source_id for r in reconciliations)


def has_unresolved_reconciliation_differences(source_id: str) -> bool:
    reconciliations = _load_jsonl(_RECONCILIATION_PATH)
    unresolved = [
        r for r in reconciliations
        if r.get("source_id") == source_id
        and r.get("human_decision_status", "pending_review") == "pending_review"
    ]
    return len(unresolved) > 0


def get_confirmed_requirement_ids(source_id: str) -> List[str]:
    """Return CRM IDs that have been confirmed after reconciliation."""
    reconciliations = _load_jsonl(_RECONCILIATION_PATH)
    accepted = [
        r for r in reconciliations
        if r.get("source_id") == source_id
        and r.get("human_decision_status") == "accepted"
    ]
    return list(set(r.get("pdf_candidate_id", "") for r in accepted if r.get("pdf_candidate_id")))


def can_confirm_requirements_for_source(source_id: str) -> dict:
    """Check if requirements from this source can be confirmed."""
    reasons = []
    if has_unresolved_reconciliation_differences(source_id):
        reasons.append("Unresolved reconciliation differences exist. Review and accept/reject each item first.")
    return {"allowed": len(reasons) == 0, "blocking_reasons": reasons}


def can_start_gsp_derivation_for_source(source_id: str) -> dict:
    """Check if GSP Standard derivation can proceed for this source.
    
    For PDF sources, requires: curated baseline + reconciliation report + no unresolved differences.
    """
    reasons = get_reconciliation_blocking_reasons(source_id)
    return {"allowed": len(reasons) == 0, "blocking_reasons": reasons}


def get_reconciliation_blocking_reasons(source_id: str) -> List[str]:
    """Return all blocking reasons for C5A derivation."""
    reasons = []
    
    # Find the source record
    sources = _load_jsonl(_SOURCE_REGISTER_PATH)
    source = next((s for s in sources if s.get("id") == source_id or s.get("source_id") == source_id), None)
    
    if source is None:
        reasons.append(f"Source '{source_id}' not found in source_register.")
        return reasons
    
    if not is_pdf_source(source):
        # Non-PDF sources (Excel/Word) may proceed without baseline comparison
        return reasons
    
    if not requires_curated_baseline(source):
        return reasons
    
    if not has_curated_baseline(source_id):
        reasons.append("PDF source requires curated baseline (Excel/Word/Text). No baseline found.")
        return reasons
    
    if not has_reconciliation_report(source_id):
        reasons.append("Reconciliation report not generated. Run reconciliation first.")
        return reasons
    
    if has_unresolved_reconciliation_differences(source_id):
        reasons.append("Unresolved reconciliation differences exist. Review and accept/reject each item first.")
    
    return reasons
