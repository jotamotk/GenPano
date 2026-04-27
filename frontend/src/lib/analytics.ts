/**
 * GENPANO Analytics · Mixpanel Unified Wrapper (骨架)
 *
 * Status: Session 0-rev 仅落空骨架；业务事件由 Session 4a 填充 (PRD §4.11 事件清单为唯一真相源)。
 *
 * 硬约束 (Harness D3 `mixpanel-pii-redline`):
 *   - 事件 properties 禁放 PII: email / phone / token / password / company_name / ip_address
 *   - `email_domain` (仅 @ 之后部分) 是唯一例外
 *   - 业务代码必须经过此模块, 禁止直接 `import 'mixpanel-browser'`
 *
 * 登出 6 步契约 (Harness D2 `logout-6-step-order`):
 *   track('user_logged_out') -> 必须晚于任何依赖 distinct_id 的埋点, 但早于 reset()
 *   顺序: ... -> track -> mixpanel.reset() -> clearSession -> navigate
 */

// Lazy import so non-UI bundles (SSR / tests) 不会无脑加载 SDK
type MixpanelLike = {
  init: (token: string, opts?: Record<string, unknown>) => void;
  track: (event: string, properties?: Record<string, unknown>) => void;
  identify: (userId: string) => void;
  people: {
    set: (properties: Record<string, unknown>) => void;
  };
  reset: () => void;
  register: (properties: Record<string, unknown>) => void;
};

let mp: MixpanelLike | null = null;
let initialized = false;

async function getMixpanel(): Promise<MixpanelLike | null> {
  if (mp) return mp;
  if (typeof window === 'undefined') return null;
  try {
    const mod = await import('mixpanel-browser');
    mp = (mod.default ?? mod) as unknown as MixpanelLike;
    return mp;
  } catch {
    return null;
  }
}

export async function initAnalytics(token?: string): Promise<void> {
  if (initialized) return;
  const client = await getMixpanel();
  if (!client) return;
  const effectiveToken = token ?? import.meta.env.VITE_MIXPANEL_TOKEN;
  if (!effectiveToken) return;
  client.init(effectiveToken, {
    api_host: 'https://api.mixpanel.com',
    persistence: 'localStorage',
    ignore_dnt: false,
  });
  initialized = true;
}

export async function track(event: string, properties: Record<string, unknown> = {}): Promise<void> {
  const client = await getMixpanel();
  if (!client || !initialized) return;
  client.track(event, properties);
}

export async function identify(userId: string): Promise<void> {
  const client = await getMixpanel();
  if (!client || !initialized) return;
  client.identify(userId);
}

export async function setUserProperties(properties: Record<string, unknown>): Promise<void> {
  const client = await getMixpanel();
  if (!client || !initialized) return;
  client.people.set(properties);
}

export async function reset(): Promise<void> {
  const client = await getMixpanel();
  if (!client || !initialized) return;
  client.reset();
}

export async function registerSuperProperties(properties: Record<string, unknown>): Promise<void> {
  const client = await getMixpanel();
  if (!client || !initialized) return;
  client.register(properties);
}

export const analytics = {
  init: initAnalytics,
  track,
  identify,
  setUserProperties,
  reset,
  registerSuperProperties,
};

export default analytics;
