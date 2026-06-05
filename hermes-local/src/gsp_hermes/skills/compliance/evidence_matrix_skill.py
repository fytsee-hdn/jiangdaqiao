"""evidence_matrix_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class EvidenceMatrixSkill(ComplianceDraftSkill):
    name = "evidence_matrix_skill"
    description = "Draft evidence matrix rows and identify missing evidence."
    required_inputs = ("source_refs",)
