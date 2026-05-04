# ADR-002: Schema SSOT 单 Alembic head

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
当前 schema 来自两条线：① `migrations/0xx*.sql`（004 个原始 SQL，Tracker 期写入）；② `backend/alembic/versions/`（2 个版本，FastAPI 后期加）。两条线没有 cross-check，新表落到哪个有决策歧义；ORM 定义在 `geo_tracker/db/models.py` 与 `backend/app/models/analyzer.py` 重复。

**Decision**:
所有 schema 由 backend Alembic 唯一管理（单 head）。`migrations/0xx*.sql` 转 alembic 版本，使用 `op.execute("CREATE TABLE IF NOT EXISTS …")` + `op.add_column …` 守卫保证现有数据库升级幂等（不重建 / 不丢数据）。`migrations/` 改名 `migrations.legacy/`，加 README 标注"已转入 backend/alembic/versions/，不再追加"。CI 跑 `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` 验证可逆。

**Consequences**:
- ✅ 一处 schema 真相；新表只能从 backend 落 migration。
- ✅ ORM drift CI 检查可写：从 alembic head 反射 schema → 与 `genpano_models/` 比对。
- ✅ Tracker / admin 都从 `genpano_models/` import ORM，不重写。
- ⚠️ 历史 SQL 转 alembic 需仔细测试幂等：现网 DB 升级**必须**无变更（IF NOT EXISTS 守卫到位）。
- ⚠️ 一次性迁移工作 2 工程日（Phase R.2）。

**Alternatives**:
- **保留 SQL + Alembic 双源**：无 cross-check，drift 不可控；否决。
- **dbml/PlantUML 生成 schema**：先写 dbml → 生成 SQL，更纯。但项目已经有大量 alembic 工具链（`backend/Makefile`），引入 dbml 增加切换成本，Phase 2 评估。
