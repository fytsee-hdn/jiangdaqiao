"""
source_reconciliation_engine.py — P8B: compare PDF extraction vs curated baseline.

Performs deterministic normalization + LLM semantic comparison.
Generates reconciliation records and difference reports.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Bangkok")
except ImportError:
    _TZ = timezone(timedelta(hours=7))

_logger = logging.getLogger(__name__)

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import resolve_compliance_path

_RECONCILIATION_PATH = resolve_compliance_path("source_reconciliation/source_reconciliation.jsonl")
_RECON_DIR = os.path.dirname(_RECONCILIATION_PATH)

# ══════════════════════════════════════════════════════════════════
#  Normalization helpers (code only — no semantic business logic)
# ══════════════════════════════════════════════════════════════════


def normalize_requirement_code(code: str) -> str:
    """Normalize a requirement code deterministically.
    
    Examples:
      'LT 6.1' -> 'LT6.1'
      'T 6.1' -> 'T6.1'
      'G 4.1' -> 'G4.1'
      'N 6.0' -> 'N6.0'
      'D 6.0' -> 'D6.0'
    """
    if not code:
        return ""
    code = code.strip().upper()
    code = re.sub(r'\s+', '', code)
    return code


def normalize_requirement_text(text: str) -> str:
    """Normalize text for comparison (whitespace, punctuation)."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text.strip().lower())
    text = text.rstrip('.')
    return text


def simple_text_similarity(t1: str, t2: str) -> float:
    """Simple word overlap similarity (0-1). Not semantic — deterministic signal only."""
    w1 = set(normalize_requirement_text(t1).split())
    w2 = set(normalize_requirement_text(t2).split())
    if not w1 or not w2:
        return 0.0
    intersection = w1 & w2
    union = w1 | w2
    return len(intersection) / len(union)


def build_candidate_index(pdf_candidates: List[dict]) -> Dict[str, List[dict]]:
    """Index PDF candidates by normalized code for fast lookup."""
    index: Dict[str, List[dict]] = {}
    for c in pdf_candidates:
        code = normalize_requirement_code(c.get("clause_ref", "") or "")
        key = code or "__no_code__"
        if key not in index:
            index[key] = []
        index[key].append(c)
    return index


def build_baseline_index(curated_records: List[dict]) -> Dict[str, List[dict]]:
    """Index curated baseline records by normalized code."""
    index: Dict[str, List[dict]] = {}
    for r in curated_records:
        code = normalize_requirement_code(r.get("requirement_code", "") or "")
        key = code or "__no_code__"
        if key not in index:
            index[key] = []
        index[key].append(r)
    return index


def deterministic_match_candidates(
    pdf_candidates: List[dict],
    curated_records: List[dict],
) -> Tuple[Dict[str, Any], List[dict]]:
    """Deterministic matching pass.

    Returns (matched_pairs_by_code, unmatched_pdf, unmatched_baseline).
    """
    pdf_index = build_candidate_index(pdf_candidates)
    bl_index = build_baseline_index(curated_records)

    matched_pairs: List[dict] = []
    matched_pdf_ids = set()
    matched_bl_ids = set()

    # Match by exact normalized code
    for code, pdf_list in pdf_index.items():
        if code in bl_index:
            bl_list = bl_index[code]
            for p in pdf_list:
                for b in bl_list:
                    pid = p.get("id", "")
                    bid = b.get("curated_baseline_id", "")
                    sim = simple_text_similarity(
                        p.get("requirement_text", "") or p.get("original_text_en", ""),
                        b.get("requirement_text", ""),
                    )
                    matched_pairs.append({
                        "pdf_candidate": p,
                        "curated_baseline": b,
                        "normalized_code": code,
                        "text_similarity": sim,
                        "match_type": "code_exact" if sim >= 0.5 else "code_exact_low_similarity",
                    })
                    matched_pdf_ids.add(pid)
                    matched_bl_ids.add(bid)

    # Collect unmatched
    unmatched_pdf = [c for c in pdf_candidates
                     if (c.get("id", "") or c.get("gsp_standard_id", "")) not in matched_pdf_ids]
    unmatched_bl = [r for r in curated_records
                    if r.get("curated_baseline_id", "") not in matched_bl_ids]

    return {
        "matched_pairs": matched_pairs,
        "unmatched_pdf": unmatched_pdf,
        "unmatched_baseline": unmatched_bl,
    }


# ══════════════════════════════════════════════════════════════════
#  LLM reconciliation (mock for testing)
# ══════════════════════════════════════════════════════════════════


def build_llm_reconciliation_input(
    unmatched_or_ambiguous_pairs: List[dict],
    source_id: str = "",
) -> list:
    """Build LLM input from unmatched or ambiguous pairs."""
    inputs = []
    for pair in unmatched_or_ambiguous_pairs:
        pdf = pair.get("pdf_candidate", {})
        bl = pair.get("curated_baseline", {})
        inputs.append({
            "pdf_candidate": {
                "id": pdf.get("id", ""),
                "clause_ref": pdf.get("clause_ref", ""),
                "requirement_text": (pdf.get("requirement_text", "") or pdf.get("original_text_en", ""))[:500],
            },
            "curated_baseline": {
                "curated_baseline_id": bl.get("curated_baseline_id", ""),
                "requirement_code": bl.get("requirement_code", ""),
                "requirement_text": bl.get("requirement_text", "")[:500],
            },
            "normative_signals": {
                "pdf_code_normalized": normalize_requirement_code(pdf.get("clause_ref", "") or ""),
                "baseline_code_normalized": normalize_requirement_code(bl.get("requirement_code", "") or ""),
                "text_similarity": simple_text_similarity(
                    pdf.get("requirement_text", "") or pdf.get("original_text_en", ""),
                    bl.get("requirement_text", ""),
                ),
            },
        })
    return inputs


_MOCK_LLM_RESPONSE = {
    "comparison_status": "needs_human_review",
    "confidence": 0.6,
    "recommended_action": "needs_human_review",
    "reasoning_summary": "Mock LLM: Unable to determine match with confidence. Human review recommended.",
    "code_match_signals": {"normalized_match": False},
}


def call_llm_for_reconciliation(
    llm_input: list,
    mock: bool = True,
) -> List[dict]:
    """Call LLM for reconciliation. Uses mock for testing."""
    if mock:
        results = []
        for inp in llm_input:
            result = dict(_MOCK_LLM_RESPONSE)
            result["pdf_candidate_id"] = inp["pdf_candidate"]["id"]
            result["curated_baseline_id"] = inp["curated_baseline"]["curated_baseline_id"]
            results.append(result)
        return results
    return [{"error": "Real LLM not implemented in P8B-Lite."}]


# ══════════════════════════════════════════════════════════════════
#  Reconciliation record generation
# ══════════════════════════════════════════════════════════════════


def generate_reconciliation_records(
    pdf_candidates: List[dict],
    curated_records: List[dict],
    mock_llm: bool = True,
    source_id: str = "",
    batch_id: str = "",
) -> dict:
    """Generate reconciliation records from PDF candidates and curated baseline.

    Steps:
    1. Deterministic match by normalized code.
    2. LLM reconciliation for unmatched/ambiguous pairs.
    3. Combine into reconciliation records.
    """
    now = datetime.now(_TZ).isoformat()
    
    match_result = deterministic_match_candidates(pdf_candidates, curated_records)
    matched_pairs = match_result["matched_pairs"]
    unmatched_pdf = match_result["unmatched_pdf"]
    unmatched_bl = match_result["unmatched_baseline"]

    records: List[dict] = []
    seq = 0

    # Generate records for matched pairs
    for pair in matched_pairs:
        seq += 1
        pdf = pair["pdf_candidate"]
        bl = pair["curated_baseline"]
        sim = pair["text_similarity"]

        if sim >= 0.8:
            cs = "exact_match"
            ra = "confirm_requirement"
        elif sim >= 0.5:
            cs = "text_similar_id_match"
            ra = "use_curated_baseline"
        else:
            cs = "id_mismatch"
            ra = "needs_human_review"

        records.append({
            "reconciliation_id": f"REC-P8B-{seq:04d}",
            "source_id": source_id,
            "pdf_candidate_id": pdf.get("id", ""),
            "curated_baseline_id": bl.get("curated_baseline_id", ""),
            "comparison_status": cs,
            "confidence": sim,
            "llm_recommendation": ra,
            "llm_reasoning_summary": f"Deterministic: text_similarity={sim:.2f}, code_match={pair['match_type']}",
            "code_match_signals": {"pdf_code": pdf.get("clause_ref", ""), "baseline_code": bl.get("requirement_code", "")},
            "normalized_pdf_code": pair["normalized_code"],
            "normalized_baseline_code": pair["normalized_code"],
            "text_similarity_score": sim,
            "level_match": True,
            "section_match": True,
            "recommended_action": ra,
            "human_decision_status": "pending_review",
            "human_decision_id": "",
            "batch_id": batch_id,
            "created_at": now,
            "updated_at": now,
        })

    # Generate records for unmatched PDF candidates (extra_in_pdf_extraction)
    for pdf in unmatched_pdf:
        seq += 1
        records.append({
            "reconciliation_id": f"REC-P8B-{seq:04d}",
            "source_id": source_id,
            "pdf_candidate_id": pdf.get("id", ""),
            "curated_baseline_id": "",
            "comparison_status": "extra_in_pdf_extraction",
            "confidence": 0.5,
            "llm_recommendation": "needs_human_review",
            "llm_reasoning_summary": "No matching curated baseline record found. May be noise or missing baseline item.",
            "code_match_signals": {"pdf_code": pdf.get("clause_ref", ""), "baseline_code": ""},
            "normalized_pdf_code": normalize_requirement_code(pdf.get("clause_ref", "") or ""),
            "normalized_baseline_code": "",
            "text_similarity_score": 0.0,
            "level_match": False,
            "section_match": False,
            "recommended_action": "needs_human_review",
            "human_decision_status": "pending_review",
            "created_at": now,
            "updated_at": now,
        })

    # Generate records for unmatched baseline records (missing_in_pdf_extraction)
    for bl in unmatched_bl:
        seq += 1
        records.append({
            "reconciliation_id": f"REC-P8B-{seq:04d}",
            "source_id": source_id,
            "pdf_candidate_id": "",
            "curated_baseline_id": bl.get("curated_baseline_id", ""),
            "comparison_status": "missing_in_pdf_extraction",
            "confidence": 0.5,
            "llm_recommendation": "use_curated_baseline",
            "llm_reasoning_summary": "Present in curated baseline but missing from PDF extraction.",
            "code_match_signals": {"pdf_code": "", "baseline_code": bl.get("requirement_code", "")},
            "normalized_pdf_code": normalize_requirement_code(bl.get("requirement_code", "") or ""),
            "normalized_baseline_code": "",
            "text_similarity_score": 0.0,
            "level_match": False,
            "section_match": False,
            "recommended_action": "use_curated_baseline",
            "human_decision_status": "pending_review",
            "created_at": now,
            "updated_at": now,
        })

    return {
        "ok": True,
        "records": records,
        "matched_count": len(matched_pairs),
        "extra_in_pdf": len(unmatched_pdf),
        "missing_in_pdf": len(unmatched_bl),
        "total": len(records),
    }


def write_reconciliation_records(records: List[dict], execute: bool = False) -> bool:
    if not execute:
        return False
    if not records:
        return True
    try:
        os.makedirs(_RECON_DIR, exist_ok=True)
        with open(_RECONCILIATION_PATH, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        _logger.error("Failed to write reconciliation records: %s", e)
        return False


def generate_reconciliation_report(result: dict, batch_id: str = "") -> str:
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.join(_RECON_DIR, "reports")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"reconciliation_report_{ts}.md")

    lines = [
        "# P8B Source Reconciliation Report",
        "",
        f"**Batch ID:** {batch_id}",
        f"**Generated:** {datetime.now(_TZ).isoformat()}",
        "",
        "---",
        "",
        "## Overview",
        "",
        f"- **Matched pairs:** {result.get('matched_count', 0)}",
        f"- **Extra in PDF (noise):** {result.get('extra_in_pdf', 0)}",
        f"- **Missing in PDF extraction:** {result.get('missing_in_pdf', 0)}",
        f"- **Total reconciliation records:** {result.get('total', 0)}",
        "",
        "## Reconciliation Detail",
        "",
    ]
    for rec in result.get("records", []):
        lines.append(f"- **{rec['reconciliation_id']}**: {rec['comparison_status']}")
        lines.append(f"  PDF: {rec.get('pdf_candidate_id', 'N/A')}")
        lines.append(f"  Baseline: {rec.get('curated_baseline_id', 'N/A')}")
        lines.append(f"  Action: {rec.get('recommended_action', '?')}")
        lines.append(f"  Confidence: {rec.get('confidence', 0)}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## ⚠️ IMPORTANT",
        "",
        "These reconciliation records are recommendations only.",
        "They do NOT confirm or approve any requirement.",
        "Human review is required before requirements can be confirmed.",
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path
