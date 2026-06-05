"""source_register_skill.py - accepted draft-only GSP compliance skill."""

from __future__ import annotations

from .common import ComplianceDraftSkill


class SourceRegisterSkill(ComplianceDraftSkill):
    name = "source_register_skill"
    description = "Draft source register entries from provided source metadata."
    required_inputs = ("source_refs",)
