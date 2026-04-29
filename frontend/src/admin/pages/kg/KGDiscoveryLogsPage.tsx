import React from 'react';
import AdminPlaceholderPage from '../../components/AdminPlaceholderPage';

export default function KGDiscoveryLogsPage() {
  return (
    <AdminPlaceholderPage
      module="C"
      title="Discovery 日志"
      description="kg_discovery_logs LLM 调用追踪 — 输入 prompt / 输出 token / cost / 失败原因, 支持按行业 + 时间窗筛选."
      prdSection="ADMIN_PRD §4.3.6"
      pendingSession="Session 1.5' Discovery pipeline live 写入"
    />
  );
}
