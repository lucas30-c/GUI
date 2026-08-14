/**
 * 前端契约一致性测试 — Style 白名单的跨语言单一事实来源守护（RC2 修复）。
 *
 * 后端 contracts.dsl.Style 模型是唯一事实来源；本测试断言：
 * 1. 前端渲染白名单 STYLE_WHITELIST 与已提交的 contracts/dsl/v0.1/schema.json
 *    中 Style 的 properties 完全一致（双向）；
 * 2. patch schema 的 Style 与 dsl schema 的 Style 完全一致；
 * 3. 编译期：DslStyle 接口键集与 STYLE_WHITELIST 双向覆盖（类型级守卫）。
 */
import { describe, expect, it } from 'vitest'
import dslSchema from '../../../contracts/dsl/v0.1/schema.json'
import patchSchema from '../../../contracts/patch/v0.1/schema.json'
import { STYLE_WHITELIST, mapDslStyle } from '../dsl/style'
import type { DslStyle } from '../dsl/types'

interface SchemaWithDefs {
  $defs: Record<string, { properties: Record<string, unknown> }>;
}

function stylePropertyNames(schema: unknown): string[] {
  const defs = (schema as SchemaWithDefs).$defs
  expect(defs).toBeDefined()
  const styleDef = defs.Style
  if (!styleDef) throw new Error('schema 缺少 Style 定义')
  return Object.keys(styleDef.properties)
}

describe('Style 契约一致性（前端 ↔ JSON Schema 快照）', () => {
  it('渲染白名单与 DSL schema 的 Style 字段集完全一致（双向）', () => {
    const schemaFields = new Set(stylePropertyNames(dslSchema))
    const whitelist = new Set<string>(STYLE_WHITELIST)
    expect(whitelist).toEqual(schemaFields)
  })

  it('patch schema 的 Style 与 dsl schema 的 Style 字段集一致', () => {
    const dslFields = stylePropertyNames(dslSchema).sort()
    const patchFields = stylePropertyNames(patchSchema).sort()
    expect(patchFields).toEqual(dslFields)
  })

  it('白名单无重复字段', () => {
    expect(new Set(STYLE_WHITELIST).size).toBe(STYLE_WHITELIST.length)
  })

  it('Style v2 关键能力字段在场（margin auto / 单边 margin / padding / gap / flex）', () => {
    const whitelist = new Set<string>(STYLE_WHITELIST)
    for (const field of [
      'margin',
      'marginTop',
      'marginRight',
      'marginBottom',
      'marginLeft',
      'padding',
      'paddingTop',
      'gap',
      'rowGap',
      'columnGap',
      'maxWidth',
      'minWidth',
      'display',
      'flexDirection',
      'justifyContent',
      'alignItems',
      'lineHeight',
    ]) {
      expect(whitelist.has(field)).toBe(true)
    }
  })

  it('margin:"0 auto" 与 flex 布局值可无损进入 DOM style', () => {
    const style: DslStyle = {
      margin: '0 auto',
      marginTop: 'auto',
      padding: '1rem 2rem',
      display: 'flex',
      lineHeight: '1.5',
    }
    const result = mapDslStyle(style)
    expect(result.margin).toBe('0 auto')
    expect(result.marginTop).toBe('auto')
    expect(result.padding).toBe('1rem 2rem')
    expect(result.display).toBe('flex')
    expect(result.lineHeight).toBe('1.5')
  })
})

// ============================================================
// 编译期双向覆盖守卫（类型级）
// ============================================================

/** STYLE_WHITELIST 的每个条目都必须是 DslStyle 的键 —— 由 mapDslStyle 的
 *  `style[key]` 索引在编译期强制；此处再显式声明缺失方向的守卫：
 *  DslStyle 的每个键都必须出现在白名单联合类型中，否则 Assign 报错。 */
type WhitelistEntry = (typeof STYLE_WHITELIST)[number]
type MissingFromWhitelist = Exclude<keyof DslStyle, WhitelistEntry>
type ExtraInWhitelist = Exclude<WhitelistEntry, keyof DslStyle>

// 任一方向漂移都会让对应类型变为 never，元组实例化即编译失败。
// 导出该类型使其成为「被使用」的编译期守卫（避免 noUnusedLocals 误报）。
type AssertNone<T extends never> = T
export type StyleWhitelistCompileGuards = [
  AssertNone<MissingFromWhitelist>,
  AssertNone<ExtraInWhitelist>,
]
