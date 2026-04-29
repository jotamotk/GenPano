import React from 'react';
import AdminPlaceholderPage from '../../components/AdminPlaceholderPage';

export default function PipelineOverviewPage() {
  return (
    <AdminPlaceholderPage
      module="B"
      title="采集管线 · 总览"
      description="今日采集吞吐 / 失败率 / 引擎健康分布 / 队列水位 KPI 卡片合面板。"
      prdSection="ADMIN_PRD §4.2.1 · ADMIN_PRD_B_PIPELINE.md"
      pendingSession="Session 1.2' (Adapter live 化) + Step 4 数据写入"
    />
  );
}
