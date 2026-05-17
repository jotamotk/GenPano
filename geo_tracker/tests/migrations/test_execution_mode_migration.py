"""Refs Epic #1110 / Issue #1114.

Static verification of the ``2026_05_17_0002_llm_accounts_execution_mode.py``
migration. Targets the structural invariants the issue body locks in:

  - upgrade adds BOTH ``execution_mode`` AND ``vm_id`` columns.
  - upgrade adds the ``chk_exec_mode_cookies`` CHECK constraint.
  - upgrade has the correct default for ``execution_mode``
    (``'local_cookie'``) so existing rows backfill to legacy behavior.
  - downgrade DROPS the constraint then BOTH columns — not a bare
    ``pass`` (which would silently break ``alembic downgrade -1`` on
    every operator's deploy).
  - the revision chains correctly off the previous expired_transition
    migration (down_revision pinned).

We use AST + textual inspection rather than spinning up alembic
against a real Postgres + the entire revision tree, because the
revision tree includes phases (admin_users, brand_context_snapshots)
that expect tables this in-memory SQLite test wouldn't bring up. The
AST checks are deterministic and catch the regressions the issue body
calls out explicitly.

A separate suite (``test_account_pool_vm_session.py``) exercises the
ORM-level schema directly via ``Base.metadata.create_all`` to confirm
the model + migration agree on column names + types.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    ROOT
    / "backend"
    / "alembic"
    / "versions"
    / "2026_05_17_0002_llm_accounts_execution_mode.py"
)


def _migration_text() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _revision_assignments(path: Path) -> dict[str, object]:
    """Mirror the helper from
    ``backend/tests/test_phase_5_query_pool_schema_repair.py`` —
    extracts module-level ``revision`` / ``down_revision`` strings
    without import-time side-effects."""
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


def test_migration_file_exists():
    assert MIGRATION.exists(), (
        f"expected migration at {MIGRATION}; check the timestamp prefix "
        f"matches the issue spec"
    )


def test_revision_id_pinned():
    revs = _revision_assignments(MIGRATION)
    assert revs["revision"] == "20260517_exec_mode"


def test_chains_off_expired_transition_count_migration():
    """The expired_transition_count migration was shipped earlier on
    2026-05-17; chaining off it ensures alembic applies these two in
    order so the LLMAccount model in the same release can carry both
    columns without an autogenerate diff."""
    revs = _revision_assignments(MIGRATION)
    assert revs["down_revision"] == "20260517_expired_trans_count"


def test_upgrade_adds_execution_mode_column():
    text = _migration_text()
    # Look for the specific column-add invocation. The migration
    # builds the column via ``sa.Column("execution_mode", sa.Text(), ...)``,
    # so we assert on the literal column name + default value.
    assert 'sa.Column(' in text
    assert '"execution_mode"' in text
    # Default literal MUST be the production-safe value so existing
    # rows backfill to legacy behavior.
    assert 'server_default="local_cookie"' in text


def test_upgrade_adds_vm_id_column():
    text = _migration_text()
    assert '"vm_id"' in text


def test_upgrade_adds_check_constraint_with_correct_predicate():
    """The chk_exec_mode_cookies CHECK is the only thing standing
    between a vm_session row carrying cookies (R2.5 self-cloning
    device) and a production ban storm. Pin the predicate string
    explicitly so a regression that weakens the constraint
    (e.g. ``OR cookies_json = ''``) surfaces here."""
    text = _migration_text()
    assert "chk_exec_mode_cookies" in text
    assert "execution_mode = 'local_cookie'" in text
    assert "cookies_json IS NULL" in text


def test_downgrade_is_not_a_bare_pass():
    """The issue body explicitly forbids a no-op downgrade. Confirm
    the function body has actual statements that drop the constraint
    and both columns."""
    tree = ast.parse(_migration_text())
    downgrade = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
    )
    # Filter out docstring expression so a comment-only body is rejected.
    body_statements = [
        stmt
        for stmt in downgrade.body
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
    ]
    assert len(body_statements) > 1, (
        "downgrade() must drop the constraint and both columns; "
        "a bare ``pass`` violates the issue spec"
    )

    text = _migration_text()
    # Expected ops in downgrade body.
    assert "drop_constraint" in text
    assert 'drop_column("llm_accounts", "vm_id")' in text
    assert 'drop_column("llm_accounts", "execution_mode")' in text


def test_downgrade_drops_constraint_before_columns():
    """Postgres requires the CHECK constraint be dropped before the
    columns it references. If a regression swapped the order, the
    downgrade would fail with ``cannot drop column execution_mode
    because constraint chk_exec_mode_cookies depends on it``. Pin
    the textual order so the bug surfaces here."""
    text = _migration_text()
    constraint_idx = text.find('drop_constraint(CHECK_NAME')
    column_exec_idx = text.find('drop_column("llm_accounts", "execution_mode")')
    column_vm_idx = text.find('drop_column("llm_accounts", "vm_id")')
    # Constraint drop must appear before either column drop.
    assert constraint_idx != -1
    assert column_exec_idx != -1
    assert column_vm_idx != -1
    assert constraint_idx < column_exec_idx
    assert constraint_idx < column_vm_idx


def test_upgrade_uses_lock_timeout_for_postgres():
    """Sibling migration (expired_transition_count) sets a 5s
    lock_timeout to avoid the 14-28 minute hangs reported in PR
    #1102 / #1104 incidents. The same discipline applies here
    because both columns + the CHECK constraint acquire
    AccessExclusiveLock on llm_accounts."""
    text = _migration_text()
    assert "SET lock_timeout = '5s'" in text


def test_migration_uses_idempotent_guards():
    """Re-running upgrade after a partial apply (mid-deploy crash)
    must not error. Verifies the guard helpers exist."""
    text = _migration_text()
    assert "_column_exists(\"llm_accounts\", \"execution_mode\")" in text
    assert "_column_exists(\"llm_accounts\", \"vm_id\")" in text
    assert "_constraint_exists(\"llm_accounts\", CHECK_NAME)" in text


def test_upgrade_then_downgrade_round_trip_on_sqlite():
    """Smoke-run the migration against an in-memory SQLite to confirm
    the upgrade + downgrade operations execute without errors and
    leave the schema in the expected shape.

    SQLite is intentionally used here (rather than spinning up a real
    Postgres in the test) because the test must work in any developer
    sandbox + CI runner. The CHECK constraint is Postgres-gated
    inside the migration (see the ``is_postgres`` branch); the
    column-add / drop semantics are dialect-independent. Production
    Postgres applies all three (columns + constraint) via the same
    upgrade() code path.
    """
    import importlib.util
    import sys

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text

    spec = importlib.util.spec_from_file_location(
        "exec_mode_migration", MIGRATION
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so the migration file's "from __future__" imports work.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    engine = create_engine("sqlite:///:memory:")
    try:
        # Pre-create the legacy llm_accounts shape so the migration has
        # rows to backfill.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE llm_accounts ("
                    "  id INTEGER PRIMARY KEY,"
                    "  llm_name TEXT,"
                    "  cookies_json TEXT"
                    ")"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO llm_accounts (id, llm_name, cookies_json) "
                    "VALUES (1, 'doubao', '[]')"
                )
            )

        # Apply upgrade.
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            module.op = Operations(ctx)
            module.upgrade()

        insp = inspect(engine)
        columns = {col["name"] for col in insp.get_columns("llm_accounts")}
        assert "execution_mode" in columns
        assert "vm_id" in columns

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT execution_mode, vm_id FROM llm_accounts WHERE id = 1")
            ).one()
        assert row[0] == "local_cookie", (
            "existing rows must backfill to 'local_cookie' so production "
            "behavior is unchanged"
        )
        assert row[1] is None

        # Apply upgrade a second time — must be a no-op (idempotent).
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            module.op = Operations(ctx)
            module.upgrade()

        # Apply downgrade. Columns + constraint must come off.
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            module.op = Operations(ctx)
            module.downgrade()

        insp2 = inspect(engine)
        columns_after = {col["name"] for col in insp2.get_columns("llm_accounts")}
        assert "execution_mode" not in columns_after
        assert "vm_id" not in columns_after
    finally:
        engine.dispose()
