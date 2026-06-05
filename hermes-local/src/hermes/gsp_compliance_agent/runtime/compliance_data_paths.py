"""
compliance_data_paths.py — GSP Compliance Agent: shared data path resolution.

Provides a single source of truth for compliance data paths.
Resolves paths in this priority order:
1. GSP_COMPLIANCE_DATA_ROOT environment variable (for profile-specific data roots)
2. Project-local data/knowledge/compliance/ fallback

All C5/C6 runtime modules should import from here instead of hard-coding paths.
"""

from __future__ import annotations

import os
from typing import List

# ══════════════════════════════════════════════════════════════════
#  Compliance data root resolution
# ══════════════════════════════════════════════════════════════════


def get_compliance_data_root() -> str:
    """Return the compliance data root directory.

    Priority:
    1. GSP_COMPLIANCE_DATA_ROOT env var (for profile-specific data)
    2. Project-local data/knowledge/compliance/ fallback

    The env var approach allows each Hermes profile (default, compliance)
    to have its own isolated compliance data directory.
    """
    env_root = os.environ.get("GSP_COMPLIANCE_DATA_ROOT")
    if env_root:
        return env_root

    # Fallback: project root relative to this file
    _project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    return os.path.join(_project_root, "data", "knowledge", "compliance")


def resolve_compliance_path(relative_path: str) -> str:
    """Resolve a relative path under the compliance data root.

    Example:
        resolve_compliance_path("gsp_standards/gsp_core_standard.jsonl")
        -> ~/.hermes/profiles/compliance/workspace/data/knowledge/compliance/gsp_standards/gsp_core_standard.jsonl
        (or project-local fallback)
    """
    return os.path.join(get_compliance_data_root(), relative_path)


def get_project_root() -> str:
    """Return the GSP compliance agent project root."""
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )


# ══════════════════════════════════════════════════════════════════
#  Standard compliance paths (for direct import)
# ══════════════════════════════════════════════════════════════════


def gsp_standards_path() -> str:
    return resolve_compliance_path("gsp_standards/gsp_core_standard.jsonl")


def evidence_matrix_path() -> str:
    return resolve_compliance_path("evidence_matrix/evidence_matrix.jsonl")


def checklists_path() -> str:
    return resolve_compliance_path("checklists/department_checklist.jsonl")


def crm_path() -> str:
    return resolve_compliance_path("customer_requirements/customer_requirement_master.jsonl")


def controlled_terms_path() -> str:
    return resolve_compliance_path("controlled_terms/controlled_terms.jsonl")


def review_decisions_path() -> str:
    """Path for review decision records."""
    return resolve_compliance_path("review_decisions/review_decisions.jsonl")


def review_audit_path() -> str:
    """Path for audit log records."""
    return resolve_compliance_path("review_decisions/review_audit.jsonl")


def review_packets_dir() -> str:
    return resolve_compliance_path("review_packets")


def source_text_archive_path() -> str:
    return resolve_compliance_path("source_text_archive/source_text_archive.jsonl")


def source_register_path() -> str:
    return resolve_compliance_path("source_register/source_register.jsonl")


# ══════════════════════════════════════════════════════════════════
#  Legal module paths
# ══════════════════════════════════════════════════════════════════


def legal_country_profiles_dir() -> str:
    return resolve_compliance_path("legal/country_profiles")


def legal_source_register_dir() -> str:
    return resolve_compliance_path("legal/legal_source_register")


def legal_text_archive_dir() -> str:
    return resolve_compliance_path("legal/legal_text_archive")


def legal_curated_index_dir() -> str:
    return resolve_compliance_path("legal/legal_curated_index")


def applicable_legal_requirements_dir() -> str:
    return resolve_compliance_path("legal/applicable_legal_requirements")


def legal_interpretations_dir() -> str:
    return resolve_compliance_path("legal/legal_interpretations")


def legal_conflict_cases_dir() -> str:
    return resolve_compliance_path("legal/legal_conflict_cases")


def legal_gsp_mappings_dir() -> str:
    return resolve_compliance_path("legal/legal_gsp_mappings")


def legal_review_decisions_dir() -> str:
    return resolve_compliance_path("legal/legal_review_decisions")


def legal_reports_dir() -> str:
    return resolve_compliance_path("legal/reports")


# ══════════════════════════════════════════════════════════════════
#  Directory structure
# ══════════════════════════════════════════════════════════════════


def get_required_directories() -> List[str]:
    """Return list of directories that should exist under compliance data root."""
    base = get_compliance_data_root()
    return [
        os.path.join(base, "customer_requirements"),
        os.path.join(base, "controlled_terms"),
        os.path.join(base, "gsp_standards"),
        os.path.join(base, "evidence_matrix"),
        os.path.join(base, "checklists"),
        os.path.join(base, "review_decisions"),
        os.path.join(base, "review_packets"),
        os.path.join(base, "source_text_archive"),
        os.path.join(base, "source_register"),
        os.path.join(base, "gateway_observability"),
        os.path.join(base, "reports"),
        # P9A: Legal module directories
        os.path.join(base, "legal", "country_profiles"),
        os.path.join(base, "legal", "legal_source_register"),
        os.path.join(base, "legal", "legal_text_archive"),
        os.path.join(base, "legal", "legal_curated_index"),
        os.path.join(base, "legal", "applicable_legal_requirements"),
        os.path.join(base, "legal", "legal_interpretations"),
        os.path.join(base, "legal", "legal_conflict_cases"),
        os.path.join(base, "legal", "legal_gsp_mappings"),
        os.path.join(base, "legal", "legal_review_decisions"),
        os.path.join(base, "legal", "reports"),
        # P9C: Legal original text acquisition and article directories
        os.path.join(base, "legal", "legal_original_acquisitions"),
        os.path.join(base, "legal", "legal_article_candidates"),
        os.path.join(base, "legal", "original_files"),
    ]


def ensure_compliance_dirs() -> List[str]:
    """Create all required compliance data directories if they don't exist.

    Returns list of created/confirmed directory paths.
    """
    created = []
    for d in get_required_directories():
        os.makedirs(d, exist_ok=True)
        created.append(d)
    return created


def ensure_empty_jsonl(path: str):
    """Ensure an empty JSONL file exists at the given path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("")


def ensure_all_empty_jsonl():
    """Ensure all standard JSONL targets exist as empty files."""
    targets = [
        gsp_standards_path(),
        evidence_matrix_path(),
        checklists_path(),
        crm_path(),
        controlled_terms_path(),
        review_decisions_path(),
        review_audit_path(),
        source_text_archive_path(),
        source_register_path(),
    ]
    for path in targets:
        ensure_empty_jsonl(path)
