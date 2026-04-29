import React from 'react';
import AdminPlaceholderPage from '../../components/AdminPlaceholderPage';

export default function KGBrandsPage() {
  return (
    <AdminPlaceholderPage
      module="C"
      title="品牌库"
      description="跨行业品牌主表 (kg_brands), 含 nameZh / nameEn / aliases[] / 集团 / panoScore. 支持搜索 / 编辑 / 合并."
      prdSection="ADMIN_PRD §4.3.2 · DATA_MODEL §1.2"
      pendingSession="Session 1.5' KG Platform Layer · Admin 只读 API"
    />
  );
}
