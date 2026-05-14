/**
 * LandingPage — v2.1 (Stripe Light, 2026-04-17)
 *
 * 设计依据:
 *   - docs/DESIGN_TOKENS.md  (唯一样式真相源, 本页只能引用已存在的 CSS 变量)
 *   - docs/LANDING_REDESIGN.md §4 v2.1
 *
 * ⚠️ 强制约束 (见 memory: feedback_genpano_landing_v21):
 *   1. 颜色 / 圆角 / 阴影 / 字体 100% 消费 docs/DESIGN_TOKENS.md 的 CSS 变量, 不新增 token
 *   2. 所有 CTA 指向真实路由 (/register /login /industry), 禁用 #cta / #register 锚点占位
 *   3. 所有 CTA 带 ?from=landing_<位置> UTM (PRD §4.11)
 *   4. 品牌渐变只有一条: linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%)
 *   5. 主字体 Nunito (已在 frontend/src/index.css 全局挂载到 body), 不引入 JetBrains Mono / Geist
 *   6. 不渲染 macOS 终端红/黄/绿点 mock
 *   7. 禁止开发者约束文字泄漏到用户 UI
 *
 * Structure: this file is intentionally a thin shell. Each section lives in
 * ./sections/<Name>.tsx and shared bits live in ./components and ./hooks.
 */
import { COPY } from './copy';
import { useLocale } from './hooks/useLocale';
import { FinalCTA } from './sections/FinalCTA';
import { Footer } from './sections/Footer';
import { ForAgents } from './sections/ForAgents';
import { Hero } from './sections/Hero';
import { Industries } from './sections/Industries';
import { Masthead } from './sections/Masthead';
import { Method } from './sections/Method';
import { Problem } from './sections/Problem';
import { ProductBento } from './sections/ProductBento';
import { Voices } from './sections/Voices';

export default function LandingPage() {
  const [locale, setLocale] = useLocale();
  const t = COPY[locale];

  return (
    <div style={{ backgroundColor: 'var(--color-bg-page)', minHeight: '100vh' }}>
      <Masthead locale={locale} setLocale={setLocale} t={t} />
      <main>
        <Hero t={t} />
        <Problem t={t} />
        <Method t={t} />
        <ProductBento t={t} />
        <Industries t={t} />
        <Voices t={t} />
        <ForAgents t={t} />
        <FinalCTA t={t} />
      </main>
      <Footer t={t} />
    </div>
  );
}
