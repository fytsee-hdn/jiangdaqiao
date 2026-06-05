"""department_work_package_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class DepartmentWorkPackageSkill(ComplianceDraftSkill):
    name = "department_work_package_skill"
    description = "Draft department work package candidates and owner-facing actions."
    required_inputs = ("source_refs",)
