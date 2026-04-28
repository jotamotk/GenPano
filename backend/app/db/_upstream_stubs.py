"""Upstream table stubs for Alembic autogenerate FK resolution.

These are NOT real models. They exist only so SQLAlchemy's
sort_tables_and_constraints stage can build the dependency graph
when 8 analyzer tables reference upstream tables via ForeignKey strings.

The include_object callback in alembic/env.py filters these names
out of the migration output, so versions/<ts>_baseline.py contains
ONLY the 8 analyzer tables + 4 ALTER statements.

DO NOT add columns beyond `id`. DO NOT import these in app code.
DO NOT create real models for these 4 tables in Step 6 -- they are
out of scope per Step 6 spec hard constraint #1.

NOTE: users was originally on the stub list but was promoted to a real
table in A1' Step 3 (Round 9 PR), see CLAUDE.md decision #30.H. The 4
stubs above (llm_responses / brands / competitors / prompts) remain stubs.
"""

from sqlalchemy import Column, Integer, Table

from app.db.base import Base

UPSTREAM_STUB_NAMES = frozenset({"llm_responses", "brands", "competitors", "prompts"})

llm_responses = Table("llm_responses", Base.metadata, Column("id", Integer, primary_key=True))
brands = Table("brands", Base.metadata, Column("id", Integer, primary_key=True))
competitors = Table("competitors", Base.metadata, Column("id", Integer, primary_key=True))
prompts = Table("prompts", Base.metadata, Column("id", Integer, primary_key=True))
