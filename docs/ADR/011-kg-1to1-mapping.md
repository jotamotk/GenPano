# ADR-011: KG `kg_brands`/`kg_products` 1:1 映射现有 brands/products

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
Phase K 引入 5 张 `kg_*` 表。`kg_brands` 与现有 `brands` 表的关系可选：① `kg_brands` 全字段独立（包括 name / industry_id / aliases 等）；② `kg_brands` 通过 `brand_id FK→brands(id) UNIQUE` 1:1 映射，仅承担"图谱属性"（aliases / official_domains / group_id / status）；③ 干脆把 KG 字段加到 `brands` 表，不开 `kg_brands`。

**Decision**:
方案 ②：`kg_brands(brand_id UNIQUE FK→brands)` 1:1 映射，仅承担**图谱专属属性**（如 KG 审核 status / 别名 JSONB / 集团 group_id / official_domains JSONB 镜像）。`brands` 表的 name / industry_id / 业务字段不重复存。`kg_products` 同理 1:1 映射 `products`。

**Consequences**:
- ✅ admin 现有 `brands` CRUD 路径不变（不需要重新接 `kg_brands`）。
- ✅ KG 表只装"图谱视角看到的额外信息"，业务表保持简洁。
- ✅ Phase K K2 种子 ETL 简单：每 brand 直接建对应 kg_brand 行，status='approved'。
- ⚠️ 查询 KG full graph 需要 LEFT JOIN brands + kg_brands（有索引性能可控）。
- ⚠️ 双表同步（brand 删除时 kg_brand 级联 ON DELETE CASCADE）。

**Alternatives**:
- **方案 ① 独立全字段 kg_brands**：与 brands 表内容大量重复，更新不同步风险高，否决。
- **方案 ③ 加列到 brands**：业务表臃肿，KG 概念污染业务概念边界，否决。
