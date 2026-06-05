"""requirement_breakdown_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class RequirementBreakdownSkill(ComplianceDraftSkill):
    name = "requirement_breakdown_skill"
    description = "Break source clauses into draft requirement candidates."
    required_inputs = ("source_refs",)
