# Prompt Scope 生成设计

## 摘要

Prompt Matrix 需要把“品牌关系”作为一条独立的生成维度来管理，但不能把它和用户意图混在一起。系统现在已有：

- `intent`: `informational` / `commercial` / `transactional` / `navigational`
- `language`: `zh-CN` / `en-US`

本设计在这两条维度之上增加更明确的 Prompt 类型模型：

- `non_branded`
- `branded`
- `competitive`

其中 `competitive` 还必须带 `competitive_type`，用来区分直接对比、替代、平替、切换和多品牌候选等不同竞争关系。

## 类型模型

`prompt_scope` 描述 Prompt 文案和品牌之间的关系。它独立于 `intent`。

`non_branded` 表示品牌中性的 Prompt。文案里不能出现当前品牌、竞品品牌、品牌别名、具体品牌产品名。它可以出现品类、功效、场景、人群痛点、价格区间和决策标准。数据上它仍然归属当前 `brand_id`，用于覆盖率和生成归属。

`branded` 表示文案明确提到当前品牌、当前品牌别名，或当前品牌产品。它不能引入竞品，也不能出现对比、替代、平替、换用、哪个更好等竞争关系。用户是在了解、评估、购买或使用当前品牌。

`competitive` 表示文案把当前品牌放进比较、替代、切换、平替或多品牌选择关系里。它可以出现竞品，但点名竞品必须来自已知品牌数据或明确的生成上下文。生成器不能凭空发明具体竞品品牌。

为了兼容旧数据，现有的 `competitor` 值可以作为 `competitive` 的别名被接受；但新的产品文案、接口文档和 UI 文案应统一使用 `competitive`。

## Competitive 子类型

`competitive` Prompt 必须设置以下 `competitive_type` 之一：

- `direct_comparison`: 当前品牌和一个明确竞品直接比较。
- `brand_alternative`: 在品牌层面寻找当前品牌的替代选择。
- `product_alternative`: 为当前品牌的某个产品寻找替代、平替或相似产品。
- `switching`: 从一个品牌或产品切换到另一个品牌或产品。
- `shortlist`: 在三个或更多品牌组成的候选清单里做选择。

只有 `competitive` Prompt 可以设置 `competitive_type`。`non_branded` 和 `branded` 必须把 `competitive_type` 设为 `null`。

## 生成规划

Prompt Matrix 应该先规划生成槽位，再调用 LLM。LLM 的职责是填充槽位，而不是自由决定类型分布。

当前生成逻辑可理解为：

```text
Topic x intent x language
```

新的规划模型是：

```text
Topic x intent x language x prompt_scope_plan
```

但 `prompt_scope_plan` 必须受 `max_per_topic` 约束。新增 Prompt 类型不能让数量直接乘以 3。例如 `max_per_topic = 8` 时，一个 Topic 最多生成 8 条 Prompt，可以是：

```text
3 条 non_branded
3 条 branded
2 条 competitive
```

而不是：

```text
8 条 non_branded + 8 条 branded + 8 条 competitive
```

默认 scope 配比应按 Topic 维度调整：

- Category Topic: 优先 `non_branded`，其次 `branded`，最后 `competitive`。
- Brand Topic: 优先 `branded`，其次 `competitive`，少量 `non_branded`。
- Product Topic: 优先 `branded`，其次使用 `product_alternative`、`direct_comparison` 或 `switching` 的 `competitive` 槽位，必要时保留少量 `non_branded`。

有效预计数量仍应保持为：

```text
selected_topic_count x min(planned_slots_per_topic, max_per_topic)
```

`max_prompts` 继续作为整次 run 的全局上限。它不能变成每个 scope 的上限。

## LLM 合同

每个请求给 LLM 的槽位都应明确带上目标 scope；如果是竞争类，还要带上 `competitive_type`：

```json
{
  "topic_id": 1,
  "intent": "commercial",
  "language": "zh-CN",
  "prompt_scope": "competitive",
  "competitive_type": "direct_comparison"
}
```

每条生成结果应返回：

```json
{
  "topic_id": 1,
  "intent": "commercial",
  "language": "zh-CN",
  "text": "Nike 和 Adidas 新手跑鞋哪个更适合日常慢跑？",
  "prompt_scope": "competitive",
  "competitive_type": "direct_comparison",
  "primary_brand_id": 123,
  "competitor_brand_ids": [456],
  "tags": {
    "prompt_scope": "competitive",
    "competitive_type": "direct_comparison"
  }
}
```

`tags.prompt_scope` 继续作为兼容镜像保留；顶层字段才是新的标准合同。也就是说，后续代码应优先读顶层字段，但仍能兼容旧的 `tags.prompt_scope`。

## 校验规则

LLM 输出解析后应进行 Prompt 类型校验：

- `non_branded`: 如果文案包含当前品牌、已知竞品、品牌别名或具体品牌产品名，则拒收。
- `branded`: 如果文案没有包含当前品牌、当前品牌别名或当前品牌产品，则拒收；如果包含竞品或竞争关系语言，也拒收。
- `competitive`: 如果文案缺少竞争关系信号，则拒收。竞争关系信号包括对比、替代、平替、切换、多品牌候选、`vs`、`which is better`、`similar to`，以及等价中文表达。
- `competitive_type`: `competitive` 必填；其他 scope 禁止填写。
- 点名竞品：如果竞品无法从已知品牌、竞品数据或明确上下文中解析出来，应拒收或降级处理，不能让虚构竞品进入正式候选。

单条 Prompt 校验失败应进入 rejected sample 或候选审核失败原因。除非所有生成结果都不可用，或 JSON 根结构完全无效，否则不应该让整个 run 失败。

## Query Pool 合同

Query Pool 必须继承 Prompt 的 `prompt_scope` 和 `competitive_type`。它可以加入 Segment/Profile 语境，但不能改变品牌关系。

- `non_branded` Prompt 生成的 Query 必须继续保持品牌中性。
- `branded` Prompt 生成的 Query 必须保留当前品牌关系，不能新增竞品。
- `competitive` Prompt 生成的 Query 必须保留对比、替代、切换或多品牌选择关系，不能发明新竞品。

这样可以保持职责清晰：Prompt Matrix 负责品牌关系规划，Query Pool 只负责把 Prompt 改写成带消费者语境的 Query。

## App 端影响

第一阶段可以先在 Admin 和后端落地生成合同，不阻塞用户侧 app。前提是 app 端只消费聚合指标、Response 和现有 Prompt/Query 文案。当前 `frontend/src` 没有直接调用 Prompt Matrix Admin API。

当 app 端的 Prompt 或 Query 下钻开始展示真实生成行时，需要跟进：

- 在 Topic -> Prompt -> Query 下钻中，把 `prompt_scope` 和 `intent`、`language` 一起展示。
- 对 `competitive` Prompt 和 Query 展示 `competitive_type`。
- 在可浏览 Prompt/Query 列表的地方增加可选过滤：`non_branded` / `branded` / `competitive`。
- 品牌可见度、missed prompts、竞品对比、query coverage 等页面后续应按 `prompt_scope` 分层解释指标。
- app 端只读展示 scope，不负责修改 scope；Admin 生成和审核仍然是事实来源。

现有 app 端竞品管理页面可以保持不变。它已经在品牌层面管理项目竞品。新的 Prompt Scope 模型只需要把这些竞品数据作为生成上下文使用；除非后续需要让客户维护更精细的竞品池，否则不需要新增用户侧竞品设置流程。

## 错误处理边界

LLM HTTP 失败、请求超时、完全无效的 JSON 属于 LLM call failure。单条 Prompt 不符合类型规则属于质量失败。

如果一次 run 已经生成了部分有效 Prompt，后续某些 Prompt 因类型、重复或自然度校验失败，应保留有效结果、记录 rejected sample，并在 UI 中展示部分成功摘要，而不是直接塌缩成泛泛的 `LLM call failed`。

只有以下情况才应该让整个 run 进入失败状态：

- LLM 请求本身失败，且没有可用 batch。
- LLM 返回内容完全无法解析。
- 所有输出都被质量规则拒收。
- run 超时或被取消。

如果 run 已插入部分有效候选，但后续 batch 出现 LLM HTTP 错误，应在 run 上保留已生成数量和错误详情，让操作者能看到“已生成多少、失败在哪个 batch、上游错误是什么”。

## 实现备注

第一阶段实现应保持范围收敛：

- 在解析边界把 `competitor` 归一化为 `competitive`。
- 增加 `competitive_type` 的解析、校验和持久化；如果当前 schema 暂时不适合新增字段，可先放在 candidate tags 中，同时在 API 层输出 typed 字段。
- 在调用 LLM 之前生成明确的 slots，让 LLM 按 slot 输出。
- 更新 Prompt Matrix 和 Query Pool 的 prompt 文案，使其遵循新的合同。
- 增加测试覆盖：scope planning、类型校验、旧值兼容、Query 继承、partial failure 处理、app 展示字段兼容。
