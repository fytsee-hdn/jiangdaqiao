"""Shared helpers for accepted GSP compliance draft skills."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


CONTROLLED_STATUS = "draft_requires_human_review"


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class ComplianceDraftSkill:
    """Base class for deterministic draft-only compliance skills.

    Accepted compliance skills may organise supplied evidence and identify gaps,
    but they must not approve, publish, certify legal compliance, or fabricate
    missing source details.
    """

    name = "compliance_draft_skill"
    description = "Draft-only compliance skill."
    required_inputs: Iterable[str] = ()

    def run(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        data = dict(kwargs)
        if args:
            data["positional_inputs"] = list(args)
        missing = [field for field in self.required_inputs if not data.get(field)]
        source_refs = _as_list(data.get("source_refs") or data.get("evidence_refs"))
        return {
            "ok": not missing,
            "status": CONTROLLED_STATUS,
            "skill": self.name,
            "draft_only": True,
            "requires_human_review": True,
            "missing_required_inputs": missing,
            "source_refs": source_refs,
            "candidate": {
                "objective": data.get("objective", ""),
                "items": _as_list(data.get("items") or data.get("requirements") or data.get("clauses")),
                "notes": data.get("notes", ""),
            },
            "blocked_actions": [
                "approve_official_policy",
                "publish_standard",
                "certify_legal_compliance",
                "fabricate_missing_sources",
            ],
            "message": "Draft candidate prepared from supplied inputs; human review is required before official use.",
        }
