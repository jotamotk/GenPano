"""Query Pool schema drift regression coverage.

Admin consolidation moved Query Pool reads/writes into FastAPI, but existing
operator databases can already have legacy query_generation_* tables. The
consolidation migration must repair those tables with ALTER COLUMN guards,
not only CREATE TABLE IF NOT EXISTS, or the Admin Query Pool loads fail with
UndefinedColumn at runtime.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"
CONSOLIDATION = VERSIONS / "2026_05_06_0002_admin_console_consolidation.py"
REPAIR = VERSIONS / "2026_05_07_0001_query_pool_schema_repair.py"


def _revision_assignments(path: Path) -> dict[str, object]:
    values: dict[str, object] = {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            value = node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            only_target = node.targets[0]
            if isinstance(only_target, ast.Name):
                target = only_target.id
                value = node.value
        if target not in {"revision", "down_revision"}:
            continue
        values[target] = ast.literal_eval(value) if value is not None else None
    return values


def _assert_add_column(text: str, table: str, column_fragment: str) -> None:
    assert f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS " in text
    assert column_fragment in text


def test_admin_consolidation_repairs_existing_query_pool_tables_before_indexes():
    text = CONSOLIDATION.read_text(encoding="utf-8")
    compact = " ".join(text.split())
    _assert_add_column(text, "query_generation_runs", "llm_model VARCHAR(128)")
    _assert_add_column(text, "query_generation_runs", "llm_usage_json JSONB NOT NULL DEFAULT")
    _assert_add_column(text, "query_generation_runs", "llm_error TEXT")
    _assert_add_column(
        text,
        "query_generation_candidates",
        "generation_method VARCHAR(32) NOT NULL DEFAULT",
    )
    _assert_add_column(text, "query_generation_candidates", "llm_model VARCHAR(128)")
    _assert_add_column(text, "query_generation_candidates", "llm_usage_json JSONB NOT NULL DEFAULT")

    generation_method_alter = compact.index(
        "ALTER TABLE query_generation_candidates ADD COLUMN IF NOT EXISTS"
    )
    generation_method_index = compact.index("idx_query_candidates_generation_method")
    assert generation_method_alter < generation_method_index


def test_query_pool_schema_repair_migration_patches_already_stamped_databases():
    text = REPAIR.read_text(encoding="utf-8")
    compact = " ".join(text.split())
    assert 'revision: str = "20260507_qpool_repair"' in compact
    assert (
        'down_revision: str | Sequence[str] | None = "20260506_drop_audit_operator_fk"' in compact
    )
    _assert_add_column(text, "query_generation_runs", "llm_model VARCHAR(128)")
    _assert_add_column(text, "query_generation_runs", "llm_usage_json JSONB NOT NULL DEFAULT")
    _assert_add_column(text, "query_generation_runs", "llm_error TEXT")
    _assert_add_column(
        text,
        "query_generation_candidates",
        "generation_method VARCHAR(32) NOT NULL DEFAULT",
    )
    _assert_add_column(text, "query_generation_candidates", "llm_model VARCHAR(128)")
    _assert_add_column(text, "query_generation_candidates", "llm_usage_json JSONB NOT NULL DEFAULT")
    assert "CREATE INDEX IF NOT EXISTS idx_query_candidates_generation_method" in compact


def test_query_pool_repair_revision_fits_alembic_version_column():
    text = REPAIR.read_text(encoding="utf-8")
    revision_line = next(line for line in text.splitlines() if line.startswith("revision:"))
    revision = revision_line.split("=", 1)[1].strip().strip('"')
    assert len(revision) <= 32


def test_alembic_revision_ids_fit_version_column_and_down_revisions_resolve():
    revisions: dict[str, Path] = {}
    down_revisions: dict[Path, object] = {}
    for path in VERSIONS.glob("*.py"):
        values = _revision_assignments(path)
        revision = values.get("revision")
        assert isinstance(revision, str) and revision, f"{path.name} is missing revision"
        assert len(revision) <= 32, f"{path.name} revision too long for alembic_version"
        revisions[revision] = path
        down_revisions[path] = values.get("down_revision")

    for path, down_revision in down_revisions.items():
        if down_revision is None:
            continue
        if isinstance(down_revision, str):
            references = (down_revision,)
        else:
            assert isinstance(down_revision, tuple), (
                f"{path.name} down_revision must be str/tuple/None"
            )
            references = down_revision
        for reference in references:
            assert isinstance(reference, str), f"{path.name} has non-string down_revision"
            assert reference in revisions, f"{path.name} references missing {reference}"
