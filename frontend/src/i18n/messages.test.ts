/**
 * Issue #1031 follow-up: the `brand_products.sentiment_label` key was
 * missing from `messages.js`, so `BrandProductsPage.tsx:310` rendered
 * the raw literal `brand_products.sentiment_label` in every sparkline
 * card (the `t` function returns the key as-is when not found; the
 * 2nd arg is parsed as message-format params, NOT a fallback string).
 *
 * This test guards the lookup so a future namespace move doesn't
 * silently regress the UI.
 */

import { describe, expect, it } from 'vitest'
// @ts-expect-error – messages.js is a plain JS module without a .d.ts.
import { MESSAGES, resolveKey } from './messages'

describe('brand_products.sentiment_label i18n key', () => {
  it('resolves to "情感" in zh-CN', () => {
    const zh = MESSAGES['zh-CN']
    expect(resolveKey(zh, 'brand_products.sentiment_label')).toBe('情感')
  })

  it('resolves to "Sentiment" in en-US', () => {
    const en = MESSAGES['en-US']
    expect(resolveKey(en, 'brand_products.sentiment_label')).toBe('Sentiment')
  })

  it('does not return the raw key (regression for issue #1031)', () => {
    for (const locale of ['zh-CN', 'en-US'] as const) {
      const value = resolveKey(MESSAGES[locale], 'brand_products.sentiment_label')
      expect(value).toBeDefined()
      expect(value).not.toBe('brand_products.sentiment_label')
    }
  })
})
