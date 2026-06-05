"""sop_planning_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class SopPlanningSkill(ComplianceDraftSkill):
    name = "sop_planning_skill"
    description = "Draft SOP planning candidates from reviewed compliance requirements."
    required_inputs = ("requirements",)
