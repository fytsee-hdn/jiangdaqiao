"""document_priority_matrix_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class DocumentPriorityMatrixSkill(ComplianceDraftSkill):
    name = "document_priority_matrix_skill"
    description = "Draft document priority matrix rows with evidence and review status."
    required_inputs = ("source_refs",)
