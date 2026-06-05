"""Skill manifest enforcement for Hermes profile boundaries."""

from __future__ import annotations

from typing import Any, Dict

from gsp_hermes.admin.admin_audit_logger import log_admin_action

ALLOWED_STATUSES = {"draft", "candidate", "pending_review", "accepted", "obsolete"}
LOADABLE_STATUS = "accepted"
REQUIRED_FIELDS = {
    "scope",
    "status",
    "allowed_profiles",
    "source_agent",
    "contains_sensitive_data",
}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_skill_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    missing = sorted(field for field in REQUIRED_FIELDS if field not in manifest)
    status = _norm(manifest.get("status"))
    allowed_profiles = manifest.get("allowed_profiles", [])
    if missing:
        return {"valid": False, "reason": "manifest_missing_fields", "missing": missing}
    if status not in ALLOWED_STATUSES:
        return {"valid": False, "reason": "invalid_status"}
    if not isinstance(allowed_profiles, list) or not allowed_profiles:
        return {"valid": False, "reason": "allowed_profiles_required"}
    return {"valid": True, "reason": ""}


def can_load_skill(manifest: Dict[str, Any], active_profile: str) -> Dict[str, Any]:
    validation = validate_skill_manifest(manifest)
    if not validation.get("valid"):
        return {"allowed": False, "reason": validation.get("reason"), "details": validation}
    status = _norm(manifest.get("status"))
    if status != LOADABLE_STATUS:
        return {"allowed": False, "reason": "skill_not_accepted"}
    active = _norm(active_profile)
    allowed = [_norm(profile) for profile in manifest.get("allowed_profiles", [])]
    if active not in allowed:
        return {"allowed": False, "reason": "profile_scope_mismatch"}
    if manifest.get("contains_sensitive_data") is True:
        return {"allowed": False, "reason": "sensitive_skill_not_loadable"}
    return {"allowed": True, "reason": ""}


def can_promote_skill(manifest: Dict[str, Any], target_status: str, approved_by: str = "") -> Dict[str, Any]:
    target = _norm(target_status)
    if target != LOADABLE_STATUS:
        return {"allowed": True, "reason": ""}
    if manifest.get("contains_sensitive_data") is True:
        return {"allowed": False, "reason": "sensitive_skill_cannot_be_promoted"}
    if _norm(approved_by) not in {"human_owner", "owner"}:
        return {"allowed": False, "reason": "human_approval_required"}
    return {"allowed": True, "reason": ""}


def log_skill_event(event: str, manifest: Dict[str, Any], active_profile: str, allowed: bool, reason: str) -> None:
    log_admin_action({
        "actor": "skill_policy",
        "entrypoint": "runtime",
        "user_id": "",
        "intent": event,
        "risk_level": "medium" if allowed else "high",
        "requires_confirmation": False,
        "allowed": allowed,
        "summary": event,
        "data": {
            "profile": active_profile,
            "skill_scope": manifest.get("scope"),
            "skill_status": manifest.get("status"),
            "source_agent": manifest.get("source_agent"),
            "reason": reason,
        },
    })
