/*
 * LeadFormModal — PRD §4.9.3 / §4.7.4a 线索收集弹窗
 * ──────────────────────────────────────────────────
 * 触发: 任意诊断 / 线索报告四层 (Quick Wins / Strategic Bets / Branding Risks / Consulting Accelerators)
 * 提交后: 自动发送 PDF 至用户邮箱 + 通知 BD 团队
 * 携带上下文: diagnosticId (可选) → 预填咨询重点
 */
import { Badge, Button } from '../ui';

export default function LeadFormModal({ open, onClose, diagnostic, defaultBrand = '雅诗兰黛', defaultEmail = '' }) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(3,2,41,0.4)' }}
      onClick={onClose}
    >
      <div
        className="bg-themed-card rounded-xl shadow-2xl p-6 w-[480px] max-w-[90vw]"
        style={{ boxShadow: '0 25px 50px rgba(50,50,93,0.25)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-themed-primary">预约 GEO 诊断咨询</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-themed-muted hover:text-themed-primary text-lg leading-none"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        {diagnostic && (
          <div className="rounded-lg p-3 mb-4 border border-themed-card bg-themed-badge">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <Badge
                variant={
                  { P0: 'red', P1: 'orange', P2: 'accent', P3: 'default' }[diagnostic.severity] || 'default'
                }
                size="sm"
              >
                {diagnostic.severity}
              </Badge>
              <span className="text-xs font-medium text-themed-primary">{diagnostic.title}</span>
            </div>
            <p className="text-[11px] text-themed-faint">该诊断将作为咨询重点自动附带</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-themed-secondary block mb-1.5">品牌名称</label>
            <input
              type="text"
              defaultValue={defaultBrand}
              className="t-input w-full text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-themed-secondary block mb-1.5">联系人姓名</label>
              <input
                type="text"
                placeholder="输入姓名"
                className="t-input w-full text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-themed-secondary block mb-1.5">联系邮箱</label>
              <input
                type="email"
                defaultValue={defaultEmail}
                className="t-input w-full text-sm"
              />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-themed-secondary block mb-1.5">最关心的问题 (可选)</label>
            <textarea
              rows={3}
              placeholder="描述最关心的 GEO 优化问题..."
              className="t-input w-full text-sm resize-none"
            />
          </div>
        </div>

        <div className="flex gap-3 mt-5">
          <Button variant="accent" size="md" className="flex-1" onClick={onClose}>
            提交咨询请求
          </Button>
          <Button variant="outline" size="md" onClick={onClose}>
            取消
          </Button>
        </div>
        <p className="text-[11px] text-themed-faint mt-3 text-center">
          提交后将自动生成品牌 PANO Score 诊断报告 (PDF), 发送至联系邮箱及 BD 团队
        </p>
      </div>
    </div>
  );
}
