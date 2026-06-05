"""checklist_planning_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class ChecklistPlanningSkill(ComplianceDraftSkill):
    name = "checklist_planning_skill"
    description = "Draft implementation checklist candidates for compliance review."
    required_inputs = ("requirements",)
