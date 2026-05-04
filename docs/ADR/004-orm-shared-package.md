# ADR-004: ORM 共享包 `genpano_models/`

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
ORM 模型当前散在 ① `geo_tracker/db/models.py`（Tracker 域，写权限）、② `backend/app/models/analyzer.py`（FastAPI 端只读 mirror，与 ① 重复）、③ admin_console 直接用 raw SQL（无 ORM）。新增 36 张表 + 16 列 ALTER 后，三处再各定义一份是不可持续的。

**Decision**:
新建顶级包 `genpano_models/`（与 `backend/`、`geo_tracker/`、`admin_console/` 同级），集中所有 ORM 模型：
- `genpano_models/{base.py, user.py, analyzer.py, brand.py, industry.py, topic.py, prompt.py, query.py, llm_response.py, profile.py, segment.py, llm_account.py, proxy.py, browser_profile.py, scheduler.py, product.py, project.py, project_competitor.py, project_topic_pin.py, commercial_lead.py, report_job.py, crawl_request.py, ...}`
- `pyproject.toml` 把 `genpano_models` 作为本地路径依赖（`uv` workspace member）。
- `backend/app/models/__init__.py` 与 `geo_tracker/db/models.py` 改为 `from genpano_models import *`。
- admin（迁 FastAPI 后）也 import `genpano_models`。

**Consequences**:
- ✅ 单源 schema → ORM 定义；无 drift。
- ✅ CI 加 `models_drift_check.py`：从 alembic head 反射 → diff `genpano_models/` 字段集，不一致 fail。
- ✅ 三个进程共享 type / relationship / relationship loading 策略。
- ⚠️ 一次性抽包工作量 2 工程日（Phase R.3）；需小心移动时不破坏现有 import。
- ⚠️ 项目根目录多一个包，需更新 `Dockerfile` / `pyproject.toml` / CI workflow。

**Alternatives**:
- **保持各定义各的**：drift 风险高，否决。
- **代码生成（sqlacodegen）每次从 DB 反射**：可避免重复，但生成代码不稳定 + 失去手写 docstring / business method 能力，否决。
