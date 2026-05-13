import { test } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

import { ensureAdminSession } from './admin-auth';

type AdminApiResult = {
  ok: boolean;
  status: number;
  body: unknown;
  text: string;
};

type SanitizedResult = {
  taskIdPresent: boolean;
  terminalState: string;
  resultStatus: string;
  resultPlatform: string;
  reasonCategory: string;
  originalGotoLoadTimeoutRecurred: boolean;
  smsReservationPurchaseAttempted: 'yes' | 'no' | 'unknown';
  persistenceProofRequired: true;
};

const outputPath = path.join(
  process.cwd(),
  'test-results',
  'chatgpt-sms-full-live-result.json',
);

const readPollSeconds = (): number => {
  const raw = Number.parseInt(process.env.ADMIN_E2E_CHATGPT_SMS_POLL_SECONDS || '1800', 10);
  if (!Number.isFinite(raw)) return 1800;
  return Math.min(Math.max(raw, 120), 2400);
};

const categoryFromReason = (reason: string, terminalState: string): string => {
  const lower = `${reason} ${terminalState}`.toLowerCase();
  if (lower.includes('cooldown')) return 'cooldown_lock';
  if (lower.includes('manual') || lower.includes('captcha') || lower.includes('challenge')) {
    return 'requires_manual_challenge';
  }
  if (lower.includes('risk') || lower.includes('blocked') || lower.includes('suspicious')) {
    return 'risk_block';
  }
  if (
    lower.includes('no_physical_inventory') ||
    lower.includes('price_above_guard') ||
    lower.includes('target_offer_missing') ||
    lower.includes('provider_exhausted') ||
    lower.includes('no compliant')
  ) {
    return 'no_compliant_herosms_offer';
  }
  if (lower.includes('herosms') || lower.includes('sms') || lower.includes('provider')) {
    return 'herosms_error';
  }
  if (lower.includes('timeout') || lower.includes('page.goto')) return 'browser_timeout';
  if (lower.includes('cookies')) return 'no_cookies_persisted';
  return reason ? 'registration_failed' : 'unknown_terminal_failure';
};

const sanitizeResult = (
  terminalState: string,
  result: Record<string, unknown> | null,
  fallbackText: string,
  originalGotoLoadTimeoutRecurred: boolean,
): SanitizedResult => {
  const resultStatus = String(result?.status || '');
  const resultPlatform = String(result?.platform || 'chatgpt');
  const reason = String(result?.reason || result?.error || fallbackText || '');
  const reasonCategory =
    resultStatus === 'success' ? 'task_success_pending_persistence' : categoryFromReason(reason, terminalState);
  const smsReservationPurchaseAttempted =
    resultStatus === 'success' ? 'yes' : reasonCategory === 'cooldown_lock' ? 'no' : 'unknown';
  return {
    taskIdPresent: true,
    terminalState,
    resultStatus,
    resultPlatform,
    reasonCategory,
    originalGotoLoadTimeoutRecurred,
    smsReservationPurchaseAttempted,
    persistenceProofRequired: true,
  };
};

const writeSanitizedResult = (result: SanitizedResult) => {
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.log(`[ChatGPT SMS full live verify] ${JSON.stringify(result)}`);
};

const adminApi = async (
  page: Parameters<typeof ensureAdminSession>[0],
  pathName: string,
  options: { method?: string; body?: unknown } = {},
): Promise<AdminApiResult> => {
  return await page.evaluate(
    async ({ pathName: requestPath, options: requestOptions }) => {
      const response = await fetch(requestPath, {
        method: requestOptions.method || 'GET',
        credentials: 'same-origin',
        headers: requestOptions.body ? { 'content-type': 'application/json' } : undefined,
        body: requestOptions.body ? JSON.stringify(requestOptions.body) : undefined,
      });
      const text = await response.text();
      let body = null;
      try {
        body = text ? JSON.parse(text) : null;
      } catch {
        body = null;
      }
      return { ok: response.ok, status: response.status, body, text };
    },
    { pathName, options },
  );
};

test('P0 controlled live ChatGPT SMS registration succeeds before DB persistence proof', async ({ page }) => {
  const pollSeconds = readPollSeconds();
  test.setTimeout((pollSeconds + 180) * 1000);

  if (process.env.ADMIN_E2E_CHATGPT_SMS_FULL_VERIFY !== '1') {
    test.skip(true, 'Temporary #733 ChatGPT SMS full-cookie verification sentinel is disabled.');
  }

  console.log('[ChatGPT SMS full live verify] MUTATION ENABLED: exactly one Admin sms_register dispatch for platform=chatgpt.');
  await ensureAdminSession(page);

  const dispatch = await adminApi(page, '/api/sms_register', {
    method: 'POST',
    body: { platform: 'chatgpt' },
  });
  if (!dispatch.ok) {
    writeSanitizedResult({
      taskIdPresent: false,
      terminalState: `HTTP_${dispatch.status}`,
      resultStatus: 'dispatch_failed',
      resultPlatform: 'chatgpt',
      reasonCategory: 'admin_dispatch_failed',
      originalGotoLoadTimeoutRecurred: /Page\.goto: Timeout 60000ms exceeded|chatgpt\.com/i.test(dispatch.text),
      smsReservationPurchaseAttempted: 'unknown',
      persistenceProofRequired: true,
    });
    throw new Error(`ChatGPT SMS registration dispatch failed with HTTP ${dispatch.status}.`);
  }

  const taskId =
    dispatch.body && typeof dispatch.body === 'object'
      ? String((dispatch.body as Record<string, unknown>).task_id || '')
      : '';
  if (!taskId) {
    writeSanitizedResult({
      taskIdPresent: false,
      terminalState: 'NO_TASK_ID',
      resultStatus: 'dispatch_failed',
      resultPlatform: 'chatgpt',
      reasonCategory: 'task_id_missing',
      originalGotoLoadTimeoutRecurred: false,
      smsReservationPurchaseAttempted: 'unknown',
      persistenceProofRequired: true,
    });
    throw new Error('ChatGPT SMS registration dispatch did not return a task id.');
  }

  const deadline = Date.now() + pollSeconds * 1000;
  let lastState = 'PENDING';
  let lastResult: Record<string, unknown> | null = null;
  let lastText = '';
  while (Date.now() < deadline) {
    await page.waitForTimeout(5000);
    const status = await adminApi(page, `/api/task_status/${encodeURIComponent(taskId)}`);
    lastText = status.text;
    if (!status.ok) {
      lastState = `HTTP_${status.status}`;
      continue;
    }
    const body = status.body && typeof status.body === 'object'
      ? (status.body as Record<string, unknown>)
      : {};
    lastState = String(body.state || 'UNKNOWN');
    lastResult = body.result && typeof body.result === 'object'
      ? (body.result as Record<string, unknown>)
      : null;
    if (['SUCCESS', 'FAILURE', 'ERROR'].includes(lastState)) {
      break;
    }
  }

  const originalGotoLoadTimeoutRecurred = /Page\.goto: Timeout 60000ms exceeded[\s\S]*chatgpt\.com/i.test(lastText);
  const sanitized = sanitizeResult(lastState, lastResult, lastText, originalGotoLoadTimeoutRecurred);
  writeSanitizedResult(sanitized);

  if (lastState !== 'SUCCESS') {
    throw new Error(`ChatGPT SMS registration terminal state was ${lastState}; category=${sanitized.reasonCategory}.`);
  }
  if (sanitized.resultStatus !== 'success') {
    throw new Error(
      `ChatGPT SMS registration terminal non-success category=${sanitized.reasonCategory}; resultStatus=${sanitized.resultStatus || 'none'}.`,
    );
  }
});
