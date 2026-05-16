"""[#1044 B2-5 partial] cta + anchor_actions sections (PRD §4.7.6 + §4.8.4).

Closes the smallest two of the six missing sections from the audit:
  - cta — fixed-copy "consult us" block (PRD §4.7.6 business boundary)
  - anchor_actions — per-reader "what to ask" surface aggregated from
    open-diagnostic anchor_questions (PRD §4.8.4)

Acceptance:
  - weekly report payload now contains both cta + anchor_actions sections
  - lead_diagnostic uses cta variant 'strengthened' with longer copy
  - anchor_actions filters by period and severity per variant
  - anchor_actions dedupes verbatim questions across diagnostics
  - cta exposes a CTA URL + label in metrics so renderers can link out
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import Diagnostic, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    u = User(
        id=_new_id(),
        email=f"sect-{uuid.uuid4().hex[:6]}@example.com",
        name="sect",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    p = Project(
        id=_new_id(),
        user_id=u.id,
        name="P-sect",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


def _ctx(db_session, project, locale="zh-CN", from_date=None, to_date=None):
    from app.reports.sections.base import ReportContext

    today = date.today()
    return ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42],
        from_date=from_date or today - timedelta(days=6),
        to_date=to_date or today,
        locale=locale,
    )


# ── cta section ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cta_full_variant_renders_zh(db_session, project):
    from app.reports.sections.cta import CtaSection

    out = await CtaSection().render(_ctx(db_session, project), variant="full")
    assert out.section_type == "cta"
    assert "咨询" in out.title
    assert out.summary  # non-empty
    assert (
        "playbook" not in out.summary.lower() or "playbook" in out.summary
    )  # zh body talks about 剧本 not playbook
    assert out.metrics["cta_url"]
    assert out.metrics["cta_label"]
    assert out.metrics["strengthened"] is False


@pytest.mark.asyncio
async def test_cta_strengthened_variant_uses_longer_copy(db_session, project):
    from app.reports.sections.cta import CtaSection

    out_full = await CtaSection().render(_ctx(db_session, project), variant="full")
    out_strong = await CtaSection().render(_ctx(db_session, project), variant="strengthened")
    assert out_strong.metrics["strengthened"] is True
    assert len(out_strong.summary) > len(out_full.summary)


@pytest.mark.asyncio
async def test_cta_url_override_via_env(db_session, project, monkeypatch):
    monkeypatch.setenv("GENPANO_CONSULTING_CTA_URL", "https://example.com/consult")
    from app.reports.sections.cta import CtaSection

    out = await CtaSection().render(_ctx(db_session, project), variant="full")
    assert out.metrics["cta_url"] == "https://example.com/consult"


# ── anchor_actions section ──────────────────────────────────────


async def _mk_diag(
    db_session,
    project,
    *,
    severity: str,
    anchor: dict | None,
    detected_at: datetime | None = None,
    rule_id: str = "visibility_decline_v1",
) -> Diagnostic:
    d = Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=42,
        category="visibility_decline",
        severity=severity,
        type="brand",
        title=f"diag-{severity}",
        evidence={},
        reader_hints=["operator", "manager"],
        anchor_questions=anchor,
        rule_id=rule_id,
        status="open",
        detected_at=detected_at,
    )
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    return d


@pytest.mark.asyncio
async def test_anchor_actions_groups_by_reader(db_session, project):
    from app.reports.sections.anchor_actions import AnchorActionsSection

    today = date.today()
    in_window = datetime.combine(today - timedelta(days=2), datetime.min.time())
    await _mk_diag(
        db_session,
        project,
        severity="P0",
        detected_at=in_window,
        anchor={
            "operator": ["重启 engine adapter 还是切换代理池?"],
            "manager": ["是否触发紧急公关?"],
        },
    )
    out = await AnchorActionsSection().render(_ctx(db_session, project), variant="p01_only")
    by_reader = {t["name"]: t["rows"] for t in out.tables}
    assert "anchor_questions_operator" in by_reader
    assert "anchor_questions_manager" in by_reader
    assert len(by_reader["anchor_questions_operator"]) == 1
    assert "engine" in by_reader["anchor_questions_operator"][0]["question"]
    assert out.metrics["total_questions"] == 2
    assert out.metrics["diagnostic_count"] == 1


@pytest.mark.asyncio
async def test_anchor_actions_filters_period(db_session, project):
    """A diagnostic detected before from_date must NOT contribute."""
    from app.reports.sections.anchor_actions import AnchorActionsSection

    today = date.today()
    old = datetime.combine(today - timedelta(days=60), datetime.min.time())
    await _mk_diag(
        db_session,
        project,
        severity="P0",
        detected_at=old,
        anchor={"operator": ["ancient question — must not appear"]},
    )
    out = await AnchorActionsSection().render(_ctx(db_session, project), variant="p01_only")
    assert out.metrics["total_questions"] == 0
    assert out.metrics["diagnostic_count"] == 0


@pytest.mark.asyncio
async def test_anchor_actions_p01_only_excludes_p2(db_session, project):
    from app.reports.sections.anchor_actions import AnchorActionsSection

    today = date.today()
    in_window = datetime.combine(today - timedelta(days=2), datetime.min.time())
    await _mk_diag(
        db_session,
        project,
        severity="P2",
        detected_at=in_window,
        anchor={"operator": ["should NOT appear when variant is p01_only"]},
    )
    out = await AnchorActionsSection().render(_ctx(db_session, project), variant="p01_only")
    assert out.metrics["total_questions"] == 0

    out_all = await AnchorActionsSection().render(_ctx(db_session, project), variant="all")
    assert out_all.metrics["total_questions"] == 1


@pytest.mark.asyncio
async def test_anchor_actions_dedupes_verbatim_questions(db_session, project):
    """Two P0 diagnostics with the same anchor question text should
    produce ONE row, not two."""
    from app.reports.sections.anchor_actions import AnchorActionsSection

    today = date.today()
    in_window = datetime.combine(today - timedelta(days=2), datetime.min.time())
    repeat = "代理池被封了吗?"
    await _mk_diag(
        db_session,
        project,
        severity="P0",
        detected_at=in_window,
        anchor={"operator": [repeat]},
        rule_id="rule_a",
    )
    await _mk_diag(
        db_session,
        project,
        severity="P1",
        detected_at=in_window,
        anchor={"operator": [repeat, "切换备用 adapter?"]},
        rule_id="rule_b",
    )
    out = await AnchorActionsSection().render(_ctx(db_session, project), variant="p01_only")
    operator_rows = next(t["rows"] for t in out.tables if t["name"] == "anchor_questions_operator")
    questions = [r["question"] for r in operator_rows]
    assert questions.count(repeat) == 1
    assert "切换备用 adapter?" in questions


@pytest.mark.asyncio
async def test_anchor_actions_empty_state_explicit(db_session, project):
    from app.reports.sections.anchor_actions import AnchorActionsSection

    out = await AnchorActionsSection().render(_ctx(db_session, project), variant="p01_only")
    assert out.metrics["total_questions"] == 0
    assert "无开放诊断" in out.summary or "no open" in out.summary.lower()


# ── builder wiring ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_weekly_report_includes_cta_and_anchor_actions(db_session, project):
    """End-to-end: build_report('weekly') should now contain both new
    sections at the expected positions in SECTION_ORDER."""
    from app.reports import build_report

    payload = await build_report(db_session, project=project, report_type="weekly")
    section_types = [s["section_type"] for s in payload["sections"]]
    assert "anchor_actions" in section_types
    assert "cta" in section_types
    # cta is last in SECTION_ORDER
    assert section_types[-1] == "cta"


@pytest.mark.asyncio
async def test_lead_diagnostic_report_uses_strengthened_cta(db_session, project):
    from app.reports import build_report

    payload = await build_report(db_session, project=project, report_type="lead_diagnostic")
    cta_section = next(s for s in payload["sections"] if s["section_type"] == "cta")
    assert cta_section["variant"] == "strengthened"
    assert cta_section["metrics"]["strengthened"] is True


@pytest.mark.asyncio
async def test_on_demand_skips_optional_cta(db_session, project):
    """on_demand reports mark cta as 'optional' — builder skips
    'optional' variants, so on_demand has no cta section."""
    from app.reports import build_report

    payload = await build_report(db_session, project=project, report_type="on_demand")
    section_types = [s["section_type"] for s in payload["sections"]]
    assert "cta" not in section_types
    # anchor_actions IS present (variant='all', not optional)
    assert "anchor_actions" in section_types
