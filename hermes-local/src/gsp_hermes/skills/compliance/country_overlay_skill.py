"""country_overlay_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class CountryOverlaySkill(ComplianceDraftSkill):
    name = "country_overlay_skill"
    description = "Draft country overlay candidates with legal-source traceability."
    required_inputs = ("source_refs",)
