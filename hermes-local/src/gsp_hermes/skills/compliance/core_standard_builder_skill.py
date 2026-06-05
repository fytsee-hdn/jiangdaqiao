"""core_standard_builder_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class CoreStandardBuilderSkill(ComplianceDraftSkill):
    name = "core_standard_builder_skill"
    description = "Draft GSP core standard candidates from accepted requirement inputs."
    required_inputs = ("source_refs",)
