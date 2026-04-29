import React from 'react';
import AdminPlaceholderPage from '../../components/AdminPlaceholderPage';

export default function KGProductsPage() {
  return (
    <AdminPlaceholderPage
      module="C"
      title="产品库"
      description="kg_products 主表, 关联 kg_brands. 支持按品牌过滤 / 替代关系 / 升级关系一览."
      prdSection="ADMIN_PRD §4.3.3 · DATA_MODEL §1.3"
      pendingSession="Session 1.5' Product discovery 接入"
    />
  );
}
