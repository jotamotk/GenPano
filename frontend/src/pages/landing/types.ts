/**
 * Shared types for the landing page sections.
 *
 * Section components take `t` — one localized COPY entry. We derive the type
 * from the COPY object so every key stays in sync without manual interfaces.
 */
import type { COPY } from './copy';
import type { Locale } from './hooks/useLocale';

export type CopyBag = (typeof COPY)[Locale];

export interface SectionProps {
  t: CopyBag;
}
