// frontend/src/test/style-refinement.test.tsx
// 受控样式精修的前端信任边界（Spec 010 §14、AC-26 ~ AC-30）：
// A 部分 —— 运行时守卫按 op 判别式逐条校验 update_style，畸形变体一律 invalid_response；
// B 部分 —— derivePatchStyle 的净化规则、turn 构造三形态、请求体形状、失败隔离与面板展示。

import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import App, { MAX_TURN_STYLE_KEYS, derivePatchProps, derivePatchStyle } from '../App'
import { LOCAL_ERROR_MESSAGES, isPatchDocumentShape, refineNode } from '../api/refine'
import type { Fetcher } from '../api/refine'
import type { DslDocument } from '../dsl/types'
import type { PatchDocument, RefineRequest } from '../api/types'
import goldCaseRaw from '../../../examples/dsl/coffee-shop-landing.json'

// --- 见证节点（与目标无关，用于非目标零变更断言）---

const TARGET = 'hero.title'
const WITNESS = 'hero.subtitle'
const GOLD_SUBTITLE = '每一杯都是匠心之作，从产地到杯中的精品咖啡体验'

// --- 畸形 update_style 用例表（AC-27：8 种变体）---

interface MalformedCase {
  name: string
  operations: unknown[]
}

const MALFORMED_STYLE_CASES: MalformedCase[] = [
  {
    name: '缺 style',
    operations: [{ op: 'update_style', targetNodeId: TARGET }],
  },
  {
    name: 'style: null',
    operations: [{ op: 'update_style', targetNodeId: TARGET, style: null }],
  },
  {
    name: 'style: []',
    operations: [{ op: 'update_style', targetNodeId: TARGET, style: [] }],
  },
  {
    name: 'style: "x"',
    operations: [{ op: 'update_style', targetNodeId: TARGET, style: 'x' }],
  },
  {
    name: '缺 targetNodeId',
    operations: [{ op: 'update_style', style: { color: '#fff' } }],
  },
  {
    name: "targetNodeId: ''",
    operations: [{ op: 'update_style', targetNodeId: '', style: { color: '#fff' } }],
  },
  {
    name: "op: 'update_styles'（未知 op）",
    operations: [{ op: 'update_styles', targetNodeId: TARGET, style: { color: '#fff' } }],
  },
  {
    name: 'op 缺失',
    operations: [{ targetNodeId: TARGET, style: { color: '#fff' } }],
  },
]

// --- JSON 文档工具（只读夹具，深拷贝后使用）---

interface JsonNode {
  id: string
  type: string
  props?: Record<string, unknown>
  style?: Record<string, unknown>
  children?: JsonNode[]
}

interface JsonDoc {
  version: string
  root: JsonNode
  metadata?: unknown
}

function cloneGold(): JsonDoc {
  const parsed: JsonDoc = JSON.parse(JSON.stringify(goldCaseRaw))
  return parsed
}

function findJsonNode(node: JsonNode, id: string): JsonNode | null {
  if (node.id === id) return node
  for (const child of node.children ?? []) {
    const found = findJsonNode(child, id)
    if (found !== null) return found
  }
  return null
}

function requireNode(doc: JsonDoc, nodeId: string): JsonNode {
  const node = findJsonNode(doc.root, nodeId)
  if (node === null) throw new Error(`夹具构造失败：找不到节点 ${nodeId}`)
  return node
}

/** 目标节点写入 style（模拟后端浅合并后的返回文档） */
function docWithStyle(
  nodeId: string,
  style: Record<string, unknown>,
  base: JsonDoc = cloneGold(),
): JsonDoc {
  const node = requireNode(base, nodeId)
  node.style = { ...(node.style ?? {}), ...style }
  return base
}

/** 目标节点写入 props.text */
function docWithText(
  nodeId: string,
  text: string,
  base: JsonDoc = cloneGold(),
): JsonDoc {
  const node = requireNode(base, nodeId)
  node.props = { ...(node.props ?? {}), text }
  return base
}

// --- 响应 envelope 工具 ---

function stylePatchBody(
  nodeId: string,
  style: Record<string, unknown>,
): Record<string, unknown> {
  return {
    success: true,
    patch: {
      version: '0.1',
      operations: [{ op: 'update_style', targetNodeId: nodeId, style }],
    },
    document: docWithStyle(nodeId, style),
    integrity: { selectedNodeId: nodeId, nonTargetNodesUnchanged: true },
  }
}

function propsPatchBody(nodeId: string, text: string): Record<string, unknown> {
  return {
    success: true,
    patch: {
      version: '0.1',
      operations: [{ op: 'update_props', targetNodeId: nodeId, props: { text } }],
    },
    document: docWithText(nodeId, text),
    integrity: { selectedNodeId: nodeId, nonTargetNodesUnchanged: true },
  }
}

function mixedPatchBody(
  nodeId: string,
  text: string,
  style: Record<string, unknown>,
): Record<string, unknown> {
  return {
    success: true,
    patch: {
      version: '0.1',
      operations: [
        { op: 'update_props', targetNodeId: nodeId, props: { text } },
        { op: 'update_style', targetNodeId: nodeId, style },
      ],
    },
    document: docWithStyle(nodeId, style, docWithText(nodeId, text)),
    integrity: { selectedNodeId: nodeId, nonTargetNodesUnchanged: true },
  }
}

/** 以指定 patch 覆盖的成功 envelope（document / integrity 仍合法） */
function bodyWithPatch(nodeId: string, patch: unknown): Record<string, unknown> {
  return {
    success: true,
    patch,
    document: docWithStyle(nodeId, { color: '#c0392b' }),
    integrity: { selectedNodeId: nodeId, nonTargetNodesUnchanged: true },
  }
}

function serverFailureBody(): Record<string, unknown> {
  return {
    success: false,
    error: {
      code: 'invalid_candidate_structure',
      message: '候选 Patch 结构非法',
      issues: [
        { path: 'operations[0].style', code: 'unknown_style_key', message: '未知样式键' },
      ],
    },
  }
}

// --- fetcher 注入工具（不 mock 全局 fetch）---

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

interface ScriptedResponse {
  status: number
  body: Record<string, unknown>
}

function ok(body: Record<string, unknown>): ScriptedResponse {
  return { status: 200, body }
}

function scriptedFetcher(responses: ScriptedResponse[]): Fetcher {
  let index = 0
  return vi.fn(async () => {
    const response = responses[Math.min(index, responses.length - 1)]
    if (response === undefined) throw new Error('scriptedFetcher 未配置任何响应')
    index += 1
    return jsonResponse(response.status, response.body)
  })
}

// --- 请求体读取工具 ---

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('期望普通对象')
  }
  const record: Record<string, unknown> = {}
  for (const [key, entry] of Object.entries(value)) record[key] = entry
  return record
}

function requestBodyAt(fetcher: Fetcher, callIndex: number): Record<string, unknown> {
  const call = vi.mocked(fetcher).mock.calls[callIndex]
  if (call === undefined) throw new Error(`fetcher 未发生第 ${callIndex + 1} 次调用`)
  const parsed: unknown = JSON.parse(String(call[1]?.body))
  return asRecord(parsed)
}

function historyTurnsAt(
  fetcher: Fetcher,
  callIndex: number,
): Array<Record<string, unknown>> {
  const history = requestBodyAt(fetcher, callIndex).history
  if (!Array.isArray(history)) throw new Error('请求体缺少 history 数组')
  const turns: Array<Record<string, unknown>> = []
  for (const turn of history) turns.push(asRecord(turn))
  return turns
}

function turnAt(fetcher: Fetcher, callIndex: number, turnIndex: number): Record<string, unknown> {
  const turn = historyTurnsAt(fetcher, callIndex)[turnIndex]
  if (turn === undefined) throw new Error(`第 ${callIndex + 1} 次请求缺少第 ${turnIndex + 1} 轮`)
  return turn
}

// --- API Client 直调夹具 ---

const clientDocument: DslDocument = {
  version: '0.1',
  root: {
    id: 'page',
    type: 'Page',
    props: { title: 'Base' },
    children: [{ id: TARGET, type: 'Heading', props: { text: '原始标题', level: 1 } }],
  },
}

function clientRequest(): RefineRequest {
  return {
    document: clientDocument,
    selectedNodeId: TARGET,
    instruction: 'set_style:color=#c0392b',
  }
}

// --- 交互工具 ---

function selectNode(container: HTMLElement, nodeId: string): void {
  const node = container.querySelector(`[data-node-id="${nodeId}"]`)
  if (node === null) throw new Error(`找不到节点 ${nodeId}`)
  fireEvent.click(node)
}

function nodeText(container: HTMLElement, nodeId: string): string {
  const node = container.querySelector(`[data-node-id="${nodeId}"]`)
  if (node === null) throw new Error(`找不到节点 ${nodeId}`)
  return node.textContent ?? ''
}

async function runRound(
  container: HTMLElement,
  nodeId: string,
  instruction: string,
): Promise<void> {
  selectNode(container, nodeId)
  fireEvent.change(screen.getByTestId('refine-instruction'), {
    target: { value: instruction },
  })
  await act(async () => {
    fireEvent.click(screen.getByTestId('refine-submit'))
  })
  await waitFor(() => expect(screen.queryByTestId('refine-loading')).toBeNull())
}

function historyItems(): string[] {
  return screen.queryAllByTestId('refine-history-item').map((el) => el.textContent ?? '')
}

function patch(operations: PatchDocument['operations']): PatchDocument {
  return { version: '0.1', operations }
}

// --- 未捕获异常探针 ---

let consoleErrorSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

afterEach(() => {
  consoleErrorSpy.mockRestore()
})

// ============================================================
// A. 守卫层：按 op 判别式逐条校验（AC-26 / AC-27）
// ============================================================

describe('A. isPatchDocumentShape 对 update_style 的逐条校验', () => {
  it('接受合法 update_style（AC-26）', () => {
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [{ op: 'update_style', targetNodeId: TARGET, style: { color: '#fff' } }],
      }),
    ).toBe(true)
  })

  it('接受空 style 对象（值域判定属后端 hard gate，本层只校验结构）', () => {
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [{ op: 'update_style', targetNodeId: TARGET, style: {} }],
      }),
    ).toBe(true)
  })

  it('接受混合 operations（update_props + update_style）', () => {
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [
          { op: 'update_props', targetNodeId: TARGET, props: { text: 'x' } },
          { op: 'update_style', targetNodeId: TARGET, style: { fontSize: '2rem' } },
        ],
      }),
    ).toBe(true)
  })

  it('纯 update_props 回归：形状与 M4-03 一致仍被接受', () => {
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [{ op: 'update_props', targetNodeId: TARGET, props: { text: 'x' } }],
      }),
    ).toBe(true)
  })

  for (const malformed of MALFORMED_STYLE_CASES) {
    it(`拒绝 update_style：${malformed.name}`, () => {
      expect(
        isPatchDocumentShape({ version: '0.1', operations: malformed.operations }),
      ).toBe(false)
    })
  }

  it('混合 operations 中任一条 style op 非法 → 整体拒绝', () => {
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [
          { op: 'update_props', targetNodeId: TARGET, props: { text: 'x' } },
          { op: 'update_style', targetNodeId: TARGET, style: null },
        ],
      }),
    ).toBe(false)
  })

  it('update_style 携带 props 而缺 style → 拒绝（不按 props 分支放行）', () => {
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [{ op: 'update_style', targetNodeId: TARGET, props: { text: 'x' } }],
      }),
    ).toBe(false)
  })
})

describe('B. refineNode 对 update_style 响应的处理', () => {
  it('合法 update_style 响应 → success（AC-26）', async () => {
    const body = stylePatchBody(TARGET, { color: '#c0392b' })
    const result = await refineNode(clientRequest(), async () => jsonResponse(200, body))

    if (result.kind !== 'success') throw new Error(`期望 success，实际 ${result.kind}`)
    expect(result.patch.operations).toHaveLength(1)
    const operation = result.patch.operations[0]
    if (operation === undefined) throw new Error('缺少 operation')
    expect(operation.op).toBe('update_style')
  })

  for (const malformed of MALFORMED_STYLE_CASES) {
    it(`${malformed.name} → invalid_response（Promise 正常 resolve，不抛异常）`, async () => {
      const body = bodyWithPatch(TARGET, {
        version: '0.1',
        operations: malformed.operations,
      })
      const result = await refineNode(clientRequest(), async () => jsonResponse(200, body))

      if (result.kind !== 'local') throw new Error(`期望 local，实际 ${result.kind}`)
      expect(result.code).toBe('invalid_response')
      expect(result.message).toBe(LOCAL_ERROR_MESSAGES.invalid_response)
    })
  }
})

describe('C. 畸形 update_style 响应不污染任何状态（AC-27）', () => {
  for (const malformed of MALFORMED_STYLE_CASES) {
    it(`${malformed.name}：document / history 零变更且无未捕获异常`, async () => {
      const fetcher = scriptedFetcher([
        ok(propsPatchBody(TARGET, '第一版')),
        ok(bodyWithPatch(TARGET, { version: '0.1', operations: malformed.operations })),
      ])
      const { container } = render(<App fetcher={fetcher} />)

      await runRound(container, TARGET, 'set_text:第一版')
      expect(nodeText(container, TARGET)).toBe('第一版')
      const historyBefore = historyItems()
      expect(historyBefore).toHaveLength(1)

      await runRound(container, TARGET, 'set_style:color=#c0392b')

      expect(screen.getByTestId('refine-error-code').textContent).toBe('invalid_response')
      expect(nodeText(container, TARGET)).toBe('第一版')
      expect(historyItems()).toEqual(historyBefore)
      expect(screen.getByTestId('refine-history-count').textContent).toContain('1 / 20')
      expect(consoleErrorSpy).not.toHaveBeenCalled()
    })
  }
})

// ============================================================
// D. derivePatchStyle 的净化规则（AC-28）
// ============================================================

describe('D. derivePatchStyle', () => {
  it('只取 update_style 操作，忽略 update_props', () => {
    const result = derivePatchStyle(
      patch([
        { op: 'update_props', targetNodeId: TARGET, props: { text: 'x' } },
        { op: 'update_style', targetNodeId: TARGET, style: { color: '#fff' } },
      ]),
      TARGET,
    )
    expect(result).toEqual({ color: '#fff' })
  })

  it('只取 targetNodeId 等于本次提交节点的操作', () => {
    const result = derivePatchStyle(
      patch([
        { op: 'update_style', targetNodeId: WITNESS, style: { color: '#000' } },
        { op: 'update_style', targetNodeId: TARGET, style: { fontSize: '2rem' } },
      ]),
      TARGET,
    )
    expect(result).toEqual({ fontSize: '2rem' })
  })

  it('多条匹配操作按数组顺序浅合并，后来者覆盖', () => {
    const result = derivePatchStyle(
      patch([
        { op: 'update_style', targetNodeId: TARGET, style: { color: '#111', gap: '1rem' } },
        { op: 'update_style', targetNodeId: TARGET, style: { color: '#222' } },
      ]),
      TARGET,
    )
    expect(result).toEqual({ color: '#222', gap: '1rem' })
  })

  it('保留 string 与 null（null 表示该轮删除了此样式键）', () => {
    const result = derivePatchStyle(
      patch([
        {
          op: 'update_style',
          targetNodeId: TARGET,
          style: { color: '#fff', backgroundColor: null },
        },
      ]),
      TARGET,
    )
    expect(result).toEqual({ color: '#fff', backgroundColor: null })
  })

  it('丢弃 number / boolean / object / array / undefined 值', () => {
    const result = derivePatchStyle(
      patch([
        {
          op: 'update_style',
          targetNodeId: TARGET,
          style: {
            color: '#fff',
            fontSize: 16,
            bold: true,
            nested: { a: 1 },
            list: ['1rem'],
            missing: undefined,
          },
        },
      ]),
      TARGET,
    )
    expect(result).toEqual({ color: '#fff' })
  })

  it(`键数超过 ${MAX_TURN_STYLE_KEYS} 时按插入顺序保留前 ${MAX_TURN_STYLE_KEYS} 个`, () => {
    const style: Record<string, unknown> = {}
    for (let index = 0; index < 14; index += 1) style[`k${index}`] = `v${index}`
    const result = derivePatchStyle(
      patch([{ op: 'update_style', targetNodeId: TARGET, style }]),
      TARGET,
    )
    expect(Object.keys(result)).toHaveLength(MAX_TURN_STYLE_KEYS)
    expect(Object.keys(result)).toEqual(
      Array.from({ length: MAX_TURN_STYLE_KEYS }, (_unused, index) => `k${index}`),
    )
  })

  it('无匹配操作时返回空对象（含空 operations 与纯 props patch）', () => {
    expect(derivePatchStyle(patch([]), TARGET)).toEqual({})
    expect(
      derivePatchStyle(
        patch([{ op: 'update_props', targetNodeId: TARGET, props: { text: 'x' } }]),
        TARGET,
      ),
    ).toEqual({})
  })

  it('确定性：同一输入重复调用结果逐键相同', () => {
    const document = patch([
      { op: 'update_style', targetNodeId: TARGET, style: { color: '#fff', gap: '1rem' } },
    ])
    expect(derivePatchStyle(document, TARGET)).toEqual(derivePatchStyle(document, TARGET))
  })

  it('derivePatchProps 与 derivePatchStyle 互不串扰（各只认自己的 op）', () => {
    const document = patch([
      { op: 'update_props', targetNodeId: TARGET, props: { text: '标题' } },
      { op: 'update_style', targetNodeId: TARGET, style: { color: '#fff' } },
    ])
    expect(derivePatchProps(document, TARGET)).toEqual({ text: '标题' })
    expect(derivePatchStyle(document, TARGET)).toEqual({ color: '#fff' })
  })
})

// ============================================================
// E. turn 构造与请求体形状（AC-29 / DD-19）
// ============================================================

describe('E. turn 构造与请求体', () => {
  it('style 轮：下一次请求的 turn 携带 patchStyle', async () => {
    const fetcher = scriptedFetcher([
      ok(stylePatchBody(TARGET, { color: '#c0392b' })),
      ok(stylePatchBody(TARGET, { fontSize: '2rem' })),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_style:color=#c0392b')
    await runRound(container, TARGET, 'set_style:fontSize=2rem')

    const turn = turnAt(fetcher, 1, 0)
    expect(turn.patchStyle).toEqual({ color: '#c0392b' })
    expect(turn.patchProps).toEqual({})
    expect(turn.selectedNodeId).toBe(TARGET)
    expect(turn.nodeType).toBe('Heading')
  })

  it('props-only 轮：下一次请求的 turn 不含 patchStyle 键（与 M4-03 形状一致）', async () => {
    const fetcher = scriptedFetcher([
      ok(propsPatchBody(TARGET, '第一版')),
      ok(propsPatchBody(TARGET, '第二版')),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_text:第一版')
    await runRound(container, TARGET, 'set_text:第二版')

    const turn = turnAt(fetcher, 1, 0)
    expect('patchStyle' in turn).toBe(false)
    expect(Object.keys(turn).sort()).toEqual(
      ['instruction', 'nodeType', 'patchProps', 'selectedNodeId'].sort(),
    )
  })

  it('混合轮：turn 同时携带 patchProps 与 patchStyle', async () => {
    const fetcher = scriptedFetcher([
      ok(mixedPatchBody(TARGET, '立即预订', { fontWeight: 'bold' })),
      ok(propsPatchBody(TARGET, '后续一轮')),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_text_style:立即预订|fontWeight=bold')
    await runRound(container, TARGET, 'set_text:后续一轮')

    const turn = turnAt(fetcher, 1, 0)
    expect(turn.patchProps).toEqual({ text: '立即预订' })
    expect(turn.patchStyle).toEqual({ fontWeight: 'bold' })
  })

  it('style patch 中越界节点的 op 不进入 patchStyle（只认本次提交节点）', async () => {
    const body = {
      success: true,
      patch: {
        version: '0.1',
        operations: [
          { op: 'update_style', targetNodeId: TARGET, style: { color: '#c0392b' } },
          { op: 'update_style', targetNodeId: WITNESS, style: { color: '#000' } },
        ],
      },
      document: docWithStyle(TARGET, { color: '#c0392b' }),
      integrity: { selectedNodeId: TARGET, nonTargetNodesUnchanged: true },
    }
    const fetcher = scriptedFetcher([ok(body), ok(propsPatchBody(TARGET, '第二版'))])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_style:color=#c0392b')
    await runRound(container, TARGET, 'set_text:第二版')

    expect(turnAt(fetcher, 1, 0).patchStyle).toEqual({ color: '#c0392b' })
  })

  it('style 轮次的非标量值在入队前被净化（请求体必然满足后端值域）', async () => {
    const body = bodyWithPatch(TARGET, {
      version: '0.1',
      operations: [
        {
          op: 'update_style',
          targetNodeId: TARGET,
          style: { color: '#c0392b', fontSize: 16, nested: { a: 1 } },
        },
      ],
    })
    const fetcher = scriptedFetcher([ok(body), ok(propsPatchBody(TARGET, '第二版'))])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_style:color=#c0392b')
    await runRound(container, TARGET, 'set_text:第二版')

    expect(turnAt(fetcher, 1, 0).patchStyle).toEqual({ color: '#c0392b' })
  })

  it('多轮累积：第三次请求的 history 保留两轮各自的 style / props 形状', async () => {
    const fetcher = scriptedFetcher([
      ok(stylePatchBody(TARGET, { color: '#c0392b' })),
      ok(propsPatchBody(TARGET, '第二版')),
      ok(stylePatchBody(TARGET, { fontSize: '2rem' })),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_style:color=#c0392b')
    await runRound(container, TARGET, 'set_text:第二版')
    await runRound(container, TARGET, 'set_style:fontSize=2rem')

    expect(historyTurnsAt(fetcher, 2)).toHaveLength(2)
    expect(turnAt(fetcher, 2, 0).patchStyle).toEqual({ color: '#c0392b' })
    expect('patchStyle' in turnAt(fetcher, 2, 1)).toBe(false)
  })

  it('首轮请求仍省略 history 键（DD-10 不受 style 影响）', async () => {
    const fetcher = scriptedFetcher([ok(stylePatchBody(TARGET, { color: '#c0392b' }))])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_style:color=#c0392b')

    expect('history' in requestBodyAt(fetcher, 0)).toBe(false)
  })
})

// ============================================================
// F. 失败隔离（AC-30）
// ============================================================

describe('F. style 轮失败不污染文档与 history', () => {
  const failures: Array<{ name: string; response: ScriptedResponse }> = [
    { name: '502 服务端拒绝（非法样式值）', response: { status: 502, body: serverFailureBody() } },
    {
      name: '本地 invalid_response（style 非对象）',
      response: ok(
        bodyWithPatch(TARGET, {
          version: '0.1',
          operations: [{ op: 'update_style', targetNodeId: TARGET, style: 'x' }],
        }),
      ),
    },
    {
      name: 'nonTargetNodesUnchanged: false',
      response: ok({
        success: true,
        patch: {
          version: '0.1',
          operations: [{ op: 'update_style', targetNodeId: TARGET, style: { color: '#c0392b' } }],
        },
        document: docWithStyle(TARGET, { color: '#c0392b' }),
        integrity: { selectedNodeId: TARGET, nonTargetNodesUnchanged: false },
      }),
    },
    {
      name: 'integrity.selectedNodeId 与本次提交不一致',
      response: ok({
        success: true,
        patch: {
          version: '0.1',
          operations: [{ op: 'update_style', targetNodeId: TARGET, style: { color: '#c0392b' } }],
        },
        document: docWithStyle(TARGET, { color: '#c0392b' }),
        integrity: { selectedNodeId: WITNESS, nonTargetNodesUnchanged: true },
      }),
    },
  ]

  for (const failure of failures) {
    it(`${failure.name}：文档 / history / 计数三者零变更`, async () => {
      const fetcher = scriptedFetcher([ok(propsPatchBody(TARGET, '第一版')), failure.response])
      const { container } = render(<App fetcher={fetcher} />)

      await runRound(container, TARGET, 'set_text:第一版')
      const historyBefore = historyItems()

      await runRound(container, TARGET, 'set_style:color=#c0392b')

      expect(screen.getByTestId('refine-error')).toBeTruthy()
      expect(nodeText(container, TARGET)).toBe('第一版')
      expect(nodeText(container, WITNESS)).toBe(GOLD_SUBTITLE)
      expect(historyItems()).toEqual(historyBefore)
      expect(screen.getByTestId('refine-history-count').textContent).toContain('1 / 20')
    })
  }
})

// ============================================================
// G. 结果面板展示（DD-29 / BC-8 / AC-26）
// ============================================================

describe('G. 结果面板的 style 分支', () => {
  it('style 轮：渲染 refine-patch-op=update_style 与 refine-patch-style', async () => {
    const fetcher = scriptedFetcher([ok(stylePatchBody(TARGET, { color: '#c0392b' }))])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_style:color=#c0392b')

    expect(screen.getByTestId('refine-patch-op').textContent).toBe('update_style')
    expect(screen.getByTestId('refine-patch-target').textContent).toBe(TARGET)
    expect(screen.getByTestId('refine-patch-style').textContent).toContain('#c0392b')
    expect(screen.queryByTestId('refine-patch-props')).toBeNull()
    expect(screen.getByTestId('refine-integrity-flag').textContent).toContain('true')
  })

  it('props 轮：既有 testid 保持不变，不出现 style 分支（BC-8）', async () => {
    const fetcher = scriptedFetcher([ok(propsPatchBody(TARGET, '第一版'))])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_text:第一版')

    expect(screen.getByTestId('refine-patch-op').textContent).toBe('update_props')
    expect(screen.getByTestId('refine-patch-props').textContent).toContain('第一版')
    expect(screen.queryByTestId('refine-patch-style')).toBeNull()
  })

  it('混合轮：两条 operation 各自渲染 props 与 style', async () => {
    const fetcher = scriptedFetcher([
      ok(mixedPatchBody(TARGET, '立即预订', { fontWeight: 'bold' })),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_text_style:立即预订|fontWeight=bold')

    expect(screen.getAllByTestId('refine-patch-operation')).toHaveLength(2)
    expect(
      screen.getAllByTestId('refine-patch-op').map((el) => el.textContent),
    ).toEqual(['update_props', 'update_style'])
    expect(screen.getByTestId('refine-patch-props').textContent).toContain('立即预订')
    expect(screen.getByTestId('refine-patch-style').textContent).toContain('bold')
  })

  it('style 轮后文档被替换：目标节点样式生效，见证节点文案零变更', async () => {
    const fetcher = scriptedFetcher([ok(stylePatchBody(TARGET, { color: 'rgb(192, 57, 43)' }))])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, TARGET, 'set_style:color=#c0392b')

    const target = container.querySelector(`[data-node-id="${TARGET}"]`)
    if (target === null) throw new Error('找不到目标节点')
    if (!(target instanceof HTMLElement)) throw new Error('目标节点不是 HTMLElement')
    expect(target.style.color).toBe('rgb(192, 57, 43)')
    expect(nodeText(container, WITNESS)).toBe(GOLD_SUBTITLE)
    expect(consoleErrorSpy).not.toHaveBeenCalled()
  })
})
