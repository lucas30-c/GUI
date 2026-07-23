import type { DslStyle } from './types';
import type { CSSProperties } from 'react';

const STYLE_WHITELIST = [
  'color', 'backgroundColor', 'fontSize', 'fontWeight', 'textAlign',
  'width', 'height', 'padding', 'margin', 'borderRadius', 'gap',
] as const;

export function mapDslStyle(style: DslStyle | undefined): CSSProperties {
  if (!style) return {};
  const result: CSSProperties = {};
  for (const key of STYLE_WHITELIST) {
    const value = style[key];
    if (value !== undefined && value !== null) {
      (result as Record<string, string>)[key] = value;
    }
  }
  return result;
}
