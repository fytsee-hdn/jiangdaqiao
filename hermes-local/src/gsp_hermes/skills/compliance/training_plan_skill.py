"""training_plan_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class TrainingPlanSkill(ComplianceDraftSkill):
    name = "training_plan_skill"
    description = "Draft training plan candidates from reviewed compliance requirements."
    required_inputs = ("requirements",)
