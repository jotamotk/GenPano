import React from 'react';
import AdminPlaceholderPage from '../../components/AdminPlaceholderPage';

export default function RetryCenterPage() {
  return (
    <AdminPlaceholderPage
      module="B"
      title="失败重试中心"
      description="按错误码 (CAPTCHA_REQUIRED / COOKIE_EXPIRED / CF_BLOCKED / TIMEOUT / PARSER_FAIL) 聚合的失败 query 列表 + 一键重放 (admin_har_replay 标签 · 决策 #28.G C3)."
      prdSection="ADMIN_PRD §4.2.6"
      pendingSession="Session 1.2' 落地 9 错误码后 wire"
    />
  );
}
