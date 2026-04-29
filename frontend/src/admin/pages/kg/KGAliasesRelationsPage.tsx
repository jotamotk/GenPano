import React from 'react';
import AdminPlaceholderPage from '../../components/AdminPlaceholderPage';

export default function KGAliasesRelationsPage() {
  return (
    <AdminPlaceholderPage
      module="C"
      title="别名 + 关系审核"
      description="kg_mined_relations 待审队列. confidence_score = min(1, 1 - 0.85^evidence_count) (CLAUDE.md #21.D `kg_mined_relations`); ≥0.70 ∧ ≥5 自动晋升 / [0.50, 0.70) 人工审核."
      prdSection="ADMIN_PRD §4.3.4 · DATA_MODEL §1.9"
      pendingSession="Session 1.5' relation extractor 数据写入 + Step 6 wire"
    />
  );
}
