# Prompt Scope 生成实现计划

> **执行提示：** 使用 `superpowers:executing-plans`。执行本计划时逐项推进，先写/更新失败测试，再实现对应代码，最后运行验证命令。

**目标**

把 Prompt Matrix 生成从“隐含品牌/竞品倾向”升级为显式 Prompt 类型编排：

- Prompt 类型统一为 `non_branded`、`branded`、`competitive`。
- 旧值 `competitor` 仅作为兼容输入，内部和新输出统一归一化为 `competitive`。
- `competitive` 必须带 `competitive_type`，枚举为：
  - `direct_comparison`
  - `brand_alternative`
  - `product_alternative`
  - `switching`
  - `shortlist`
- 生成数量仍由用户手动数量和预计 Prompt 决定；新增类型不能把数量乘开。
- Query Pool 必须继承 Prompt Matrix 的类型语义，不能在 Query 生成时把 branded/non-branded/competitive 关系改掉。
- LLM 部分失败时保留已生成结果，并把真实错误细节写入 run，避免只显示泛泛的 `LLM call failed`。

**边界**

- Admin UI 只修改 FastAPI 返回的 `backend/static/admin.html`。
- 不创建第二个 Admin 前端。
- App 端本轮不作为阻塞项；如果 App 后续展示真实 Prompt/Query 类型，再追加轻量展示改动。

## 任务 1：类型常量与归一化测试

**文件**

- `backend/app/admin/prompt_matrix/lib.py`
- `backend/tests/test_phase_4_admin_prompt_matrix.py`

**测试先行**

新增或更新测试覆盖：

```python
def test_normalize_prompt_scope_accepts_legacy_competitor_alias():
    assert normalize_prompt_scope("competitor") == "competitive"
    assert normalize_prompt_scope("competitive") == "competitive"

def test_normalize_competitive_type_requires_type_for_competitive():
    assert normalize_competitive_type("competitive", "switching") == "switching"
    with pytest.raises(ValueError):
        normalize_competitive_type("competitive", "")

def test_normalize_competitive_type_rejects_type_for_non_competitive():
    with pytest.raises(ValueError):
        normalize_competitive_type("branded", "switching")
```

**实现**

在 Prompt Matrix shared helper 中增加：

- `ALLOWED_PROMPT_SCOPES = ("non_branded", "branded", "competitive")`
- `LEGACY_PROMPT_SCOPE_ALIASES = {"competitor": "competitive"}`
- `ALLOWED_COMPETITIVE_TYPES = (...)`
- `normalize_prompt_scope(value)`
- `normalize_competitive_type(scope, value)`

验收点：

- 空 `prompt_scope` 仍默认 `non_branded`。
- `competitor` 不再进入新数据输出，只在读取旧输入时归一化。
- 非 competitive 的 Prompt 不允许携带 `competitive_type`。

## 任务 2：生成槽位规划，不让类型放大数量

**文件**

- `backend/app/admin/prompt_matrix/lib.py`
- `backend/tests/test_phase_4_admin_prompt_matrix.py`

**测试先行**

新增测试表达核心规则：

```python
def test_prompt_scope_slots_do_not_multiply_generation_count():
    slots = build_prompt_generation_slots(
        topic=brand_topic,
        combinations=[
            {"intent": "compare", "language": "en"},
            {"intent": "buy", "language": "en"},
            {"intent": "review", "language": "zh"},
        ],
        max_per_topic=2,
    )
    assert len(slots) == 2
```

补充断言：

- 品牌/产品 topic 的 slots 至少覆盖 `branded` 与 `competitive`。
- category/通用 topic 可以生成 `non_branded` 与可比较的 `competitive`，但 branded 需要有明确品牌锚点才出现。
- 每个 slot 包含 `intent`、`language`、`prompt_scope`，competitive slot 额外包含 `competitive_type`。

**实现**

增加纯函数：

- `build_prompt_generation_slots(topic, combinations, max_per_topic)`

推荐策略：

- 先按已有 `intent × language` 组合得到基础槽位。
- 每个 topic 最多取 `max_per_topic` 个槽位。
- 在槽位内部分配 scope，而不是为每个 scope 复制一遍组合。
- 对品牌/产品 topic，优先轮转：
  - `branded`
  - `competitive/direct_comparison`
  - `competitive/brand_alternative`
  - `non_branded`
  - `competitive/product_alternative`
  - `competitive/switching`
  - `competitive/shortlist`
- 对 category/topic 无明确品牌锚点时，优先：
  - `non_branded`
  - `competitive/shortlist`
  - `competitive/product_alternative`
  - `competitive/brand_alternative`

验收点：

- `estimatedPromptCount` 的语义不变：`selectedTopicCount × min(intentCount × languageCount, maxPerTopic)`。
- `max_per_topic` 仍是每 topic 总上限，不是每类型上限。

## 任务 3：Prompt Matrix LLM 合约与解析校验

**文件**

- `backend/app/admin/prompt_matrix/lib.py`
- `backend/app/admin/prompt_matrix/llm.py`
- `backend/tests/test_phase_4_admin_prompt_matrix.py`
- `backend/tests/test_phase_4_prompt_matrix_llm.py`

**测试先行**

更新现有 prompt 文案测试：

- schema 使用 `prompt_scope: non_branded|branded|competitive`。
- 文案仍提到 `competitor` 仅作为 legacy alias。
- user message 包含 `generation_slots`。
- competitive slot 带 `competitive_type`。

新增解析测试：

```python
def test_parse_llm_prompt_candidates_persists_competitive_type():
    candidates = parse_llm_prompt_candidates(
        payload_with_competitive_prompt,
        topics_by_id={"brand-topic": brand_topic},
        source_id="run-1",
    )
    assert candidates[0].prompt_scope == "competitive"
    assert candidates[0].competitive_type == "direct_comparison"
    assert candidates[0].tags["competitive_type"] == "direct_comparison"

def test_parse_llm_prompt_candidates_rejects_competitive_without_type():
    with pytest.raises(ValueError, match="competitive_type"):
        parse_llm_prompt_candidates(payload_missing_type, topics_by_id=..., source_id="run-1")

def test_parse_llm_prompt_candidates_rejects_branded_without_brand_anchor():
    with pytest.raises(ValueError, match="branded"):
        parse_llm_prompt_candidates(payload_branded_without_brand, topics_by_id=..., source_id="run-1")
```

**实现**

修改 LLM contract：

- system message 明确三类 prompt。
- JSON schema 允许：
  - `prompt_scope`
  - `competitive_type`
  - `tags`
- user payload 每个 topic 包含 `generation_slots`，LLM 必须逐 slot 返回。

解析规则：

- `prompt_scope` 从 top-level 优先，其次 tags，最后默认 `non_branded`。
- `competitor` 归一化为 `competitive`。
- `competitive_type` 从 top-level 或 tags 读取。
- competitive 缺 type 直接拒绝。
- branded 必须包含 topic 的品牌/产品锚点。
- non_branded 不允许品牌泄漏。
- competitive 必须包含比较/替代/迁移/榜单等竞争语义，不能只是普通品牌提问。

验收点：

- 新候选写入 tags 时包含 `prompt_scope` 和必要的 `competitive_type`。
- 旧数据 tags 里的 `competitor` 读出时表现为 `competitive`。

## 任务 4：生成入库与部分失败细节

**文件**

- `backend/app/admin/prompt_matrix/generation.py`
- `backend/app/api/admin/prompt_matrix/router.py`
- `backend/tests/test_phase_4_slice3_admin_prompt_matrix_generate.py`

**测试先行**

新增测试：

```python
def test_generate_prompt_candidates_keeps_partial_results_and_error_detail(session):
    # fake client 先返回一批有效 candidates，再抛 PromptMatrixError("llm_call_failed", "HTTP 429: quota")
    run = generate_prompt_candidates(...)
    assert run.generated_count > 0
    assert "HTTP 429" in run.llm_error
    assert run.metrics["partial_failure"] is True
```

更新现有测试：

- branded candidate 仍写入 `tags.prompt_scope == "branded"`。
- competitive candidate 写入 `tags.prompt_scope == "competitive"` 和 `tags.competitive_type`。

**实现**

- `_insert_candidate_batch` 归一化 `prompt_scope`，并校验/写入 `competitive_type`。
- 捕获 `PromptMatrixError` 时，不只保存 code，要保存 `code: message`。
- 如果已经插入部分候选，run metrics 增加：
  - `partial_failure: true`
  - `batch_error_code`
  - `batch_error_message`
  - 已插入/跳过数量
- API 返回保留原 `llm_error` 字段，同时 metrics 可供 UI 展示部分成功。

验收点：

- 用户看到的不再只是 `LLM call failed`。
- 已经插入的 16 条不会被掩盖。

## 任务 5：Query Pool 继承 Prompt 类型

**文件**

- `backend/app/admin/query_pool/lib.py`
- `backend/app/admin/query_pool/llm.py`
- `backend/app/admin/query_pool/text_clean.py`
- `backend/tests/test_phase_5_slice3b_iii_query_pool_llm.py`

**测试先行**

更新/新增测试：

```python
def test_query_pool_context_inherits_competitive_scope_and_type():
    contexts = query_pool_candidate_contexts(...)
    assert contexts[0]["prompt_scope"] == "competitive"
    assert contexts[0]["competitive_type"] == "switching"
```

更新 LLM prompt 测试：

- 文案使用 `competitive`。
- 包含 `competitive_type`。
- 明确 Query 不得改变来源 Prompt 的 scope/type。

**实现**

- Query Pool scope 集合改为 `non_branded/branded/competitive`。
- 读取 `competitor` 旧值时归一化。
- candidate context 中增加 `competitive_type`。
- LLM prompt 要求：
  - non_branded query 不带品牌。
  - branded query 保留品牌/产品锚点。
  - competitive query 保留竞争意图和 `competitive_type`。

验收点：

- Query Pool 不会把 competitive Prompt 当 branded 或 non-branded 扩写。
- 后续 Query LLM 的 error body 继续保留，不回退到泛泛错误。

## 任务 6：Admin 展示与静态测试

**文件**

- `backend/app/api/admin/prompt_matrix/router.py`
- `backend/static/admin.html`
- `backend/tests/test_phase_x_admin_prompt_matrix_static.py`

**测试先行**

新增静态断言：

- Admin HTML 包含 `competitive_type` 或对应显示 helper。
- 候选 Prompt 区域展示 prompt scope badge。
- 不出现新文案把 `competitor` 作为主类型。

**实现**

- Prompt Matrix candidate row API 直接输出：
  - `prompt_scope`
  - `competitive_type`
- Admin 候选 Prompt/Prompt 列表中显示轻量 badge：
  - `Non-branded`
  - `Branded`
  - `Competitive`
  - competitive 时显示细分类型。

验收点：

- 操作员能看出生成出的 prompt 属于哪一类。
- UI 不需要改变生成数量算法。

## 任务 7：验证与收尾

运行：

```powershell
cd backend
..\ .venv\Scripts\python.exe -m pytest tests/test_phase_4_admin_prompt_matrix.py tests/test_phase_4_prompt_matrix_llm.py tests/test_phase_4_slice3_admin_prompt_matrix_generate.py tests/test_phase_5_slice3b_iii_query_pool_llm.py tests/test_phase_x_admin_prompt_matrix_static.py -q
..\ .venv\Scripts\python.exe -m ruff check app tests
```

如果路径中空格导致 PowerShell 解析问题，使用仓库实际 `.venv` Python：

```powershell
& "C:\Users\frank.wang\genpano\.venv\Scripts\python.exe" -m pytest ...
```

Admin smoke check：

- 启动 FastAPI/Vite 当前项目已有 dev server。
- 打开 `/admin`。
- 确认 Prompt Matrix 页面能加载。
- 确认生成数量/每 Topic 上限仍为数字输入。
- 确认候选 Prompt 区域可以按品牌筛选，并显示 scope/type。

## 回滚点

若 LLM contract 改动导致线上生成质量波动，保留如下低风险回滚方式：

- 后端仍接受旧 `competitor`。
- `competitive_type` 仅对 competitive 新输出强校验。
- Admin 展示是只读 badge，不影响已有审批/导出流程。
