import type { DslStyle } from './types';
import type { CSSProperties } from 'react';

/** Style DSL v2 渲染白名单（31 字段）— 前端渲染侧的唯一字段清单。
 *  与后端 contracts.dsl.Style / contracts/dsl/v0.1/schema.json 的一致性
 *  由 src/test/contract-consistency.test.ts 双向守护（运行时 + 编译期）。 */
export const STYLE_WHITELIST = [
  'margin', 'marginTop', 'marginRight', 'marginBottom', 'marginLeft',
  'padding', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'gap', 'rowGap', 'columnGap',
  'width', 'height', 'maxWidth', 'minWidth',
  'color', 'backgroundColor',
  'fontSize', 'fontWeight', 'textAlign', 'lineHeight',
  'display', 'flexDirection', 'justifyContent', 'alignItems',
  'borderWidth', 'borderStyle', 'borderColor', 'borderRadius',
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
