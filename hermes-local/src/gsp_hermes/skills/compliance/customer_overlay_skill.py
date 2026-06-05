"""customer_overlay_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class CustomerOverlaySkill(ComplianceDraftSkill):
    name = "customer_overlay_skill"
    description = "Draft customer overlay candidates with source traceability."
    required_inputs = ("source_refs",)
