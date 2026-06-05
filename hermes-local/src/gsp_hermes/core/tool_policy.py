"""Shared tool policy helpers for profile-specific extraction rules."""

from __future__ import annotations

from typing import Any, Dict


def validate_ocr_policy_binding(shared_tool: Dict[str, Any], extraction_policy: Dict[str, Any], profile: str) -> Dict[str, Any]:
    if shared_tool.get("tool_type") != "ocr_engine":
        return {"valid": False, "reason": "shared_tool_must_be_ocr_engine"}
    expected_profile = str(profile or "").strip().lower()
    policy_profile = str(extraction_policy.get("profile", "")).strip().lower()
    if policy_profile != expected_profile:
        return {"valid": False, "reason": "profile_policy_mismatch"}
    if extraction_policy.get("policy_type") != "ocr_extraction":
        return {"valid": False, "reason": "policy_type_mismatch"}
    required = extraction_policy.get("required_fields", [])
    if not isinstance(required, list) or not required:
        return {"valid": False, "reason": "required_fields_missing"}
    return {"valid": True, "reason": ""}


def build_ocr_cache_key(profile: str, artifact_hash: str, engine_id: str, engine_version: str, policy_id: str) -> str:
    parts = [profile, artifact_hash, engine_id, engine_version, policy_id]
    if any(not str(part).strip() for part in parts):
        raise ValueError("profile, artifact_hash, engine_id, engine_version, and policy_id are required")
    return "::".join(str(part).strip() for part in parts)
