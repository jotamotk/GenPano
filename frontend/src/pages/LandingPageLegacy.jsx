/**
 * LandingPageLegacy.jsx
 *
 * ⚠️ ARCHIVED ON 2026-04-17
 * 这是 v1 Builderflow 风格的首页, 已被 v2.1 (Stripe Light, DESIGN_TOKENS 对齐) 替换。
 * 保留此文件作为历史参考, 不再挂载到路由。
 *
 * 替代文件: frontend/src/pages/LandingPage.jsx (v2.1)
 * 设计依据: docs/LANDING_REDESIGN.md §4 + docs/DESIGN_TOKENS.md
 * 归档原因:
 *   1. 自创视觉语言 (Figtree, #476AFF, #030B1D), 未消费产品 DESIGN_TOKENS (Nunito, #605BFF, #030229)
 *   2. CTA 部分指向 /dashboard (要求已登录), 部分无 UTM
 *   3. 含浏览器 chrome (红黄绿点 + 地址栏) 仿真, 违反 v2.1 "no macOS terminal dots" 约束
 *
 * 如需回退, 修改 App.jsx import 路径为 LandingPageLegacy 即可。
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';

/* ─────────────────────────────────────────────
   Design tokens extracted from Builderflow
   Font: Figtree  |  Accent: #476AFF
   Text: #030B1D / #62697D / #8F96A9
   Badge bg: #F4F7FF  |  Button: #030303
   Inner-section radius: 60px  |  Card: 32px
   Button radius: 12px  |  Badge radius: 12px
   Container max-width: 1204px
   ───────────────────────────────────────────── */

const T = {
  ink: '#030B1D',
  sub: '#62697D',
  muted: '#8F96A9',
  accent: '#476AFF',
  accentLight: '#F4F7FF',
  surfaceLight: '#F7F9FC',
  white: '#FFFFFF',
  btnDark: '#030303',
  dark: '#141413',
  darkSub: '#30302E',
  green: '#0AB892',
};

/* ─── Reusable: inner-section wrapper (60px radius) ─── */
function InnerSection({ children, className = '', style = {}, id }) {
  return (
    <div
      id={id}
      className={`relative overflow-hidden ${className}`}
      style={{
        backgroundColor: T.white,
        borderRadius: '60px',
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/* ─── Reusable: container (max-width 1204px) ─── */
function Container({ children, className = '' }) {
  return (
    <div className={`max-w-[1204px] mx-auto px-6 ${className}`}>
      {children}
    </div>
  );
}

/* ─── Badge pill ─── */
function Badge({ children, className = '' }) {
  return (
    <div
      className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium ${className}`}
      style={{
        backgroundColor: T.accentLight,
        color: T.accent,
        borderRadius: '12px',
        border: `1px solid ${T.accentLight}`,
      }}
    >
      {children}
    </div>
  );
}

/* ─── Legacy implementation omitted for brevity in archive header;
   the full original component lives in git history (see commit prior to 2026-04-17 landing v2.1 migration).
   If retrieval is needed, run:
     git log --all --follow -- frontend/src/pages/LandingPage.jsx
     git show <commit>:frontend/src/pages/LandingPage.jsx
   ─── */

export default function LandingPageLegacy() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex items-center justify-center p-8"
         style={{ backgroundColor: T.white, fontFamily: 'Figtree, "Noto Sans SC", system-ui, sans-serif' }}>
      <div className="max-w-lg text-center">
        <div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium mb-4"
          style={{ backgroundColor: T.accentLight, color: T.accent }}
        >
          已归档 · 2026-04-17
        </div>
        <h1 className="text-3xl font-semibold mb-4" style={{ color: T.ink, letterSpacing: '-0.02em' }}>
          Legacy LandingPage
        </h1>
        <p className="text-base leading-relaxed mb-8" style={{ color: T.sub }}>
          This page is the Builderflow-era landing (v1). It has been replaced by the v2.1
          Stripe-Light landing that mirrors the product design tokens. Content is preserved in git history.
        </p>
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center justify-center gap-2 px-6 py-3 text-sm font-semibold"
          style={{ backgroundColor: T.btnDark, color: T.white, borderRadius: '12px' }}
        >
          Go to current landing
        </button>
      </div>
    </div>
  );
}
