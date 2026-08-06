import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import App, { MAX_HISTORY_TURNS, MAX_TURN_PROPS_KEYS, derivePatchProps } from '../App'
import type { Fetcher } from '../api/refine'
import type { PatchDocument } from '../api/types'
import goldCaseRaw from '../../../examples/dsl/coffee-shop-landing.json'
// 源码文本（用于静态断言）：以 Vite ?raw 导入，避免依赖 node 类型
import appSourceRaw from '../App.tsx?raw'
import refineSourceRaw from '../api/refine.ts?raw'
import apiTypesSourceRaw from '../api/types.ts?raw'

// --- 见证节点（Gold Case 中与目标无关的两个节点，用于非目标零变更断言）---

const WITNESS_A = 'hero.subtitle'
const WITNESS_B = 'menu.card-1.name'
const GOLD_SUBTITLE = '每一杯都是匠心之作，从产地到杯中的精品咖啡体验'
const GOLD_CARD_NAME = '经典拿铁'

// --- JSON 文档工具 ---

interface JsonNode {
  id: string
  type: string
  props?: Record<string, unknown>
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

function docWithText(entries: Array<[string, string]>, base: JsonDoc = cloneGold()): JsonDoc {
  for (const [nodeId, text] of entries) {
    const node = findJsonNode(base.root, nodeId)
    if (node === null) throw new Error(`夹具构造失败：找不到节点 ${nodeId}`)
    node.props = { ...(node.props ?? {}), text }
  }
  return base
}

function defaultPatch(nodeId: string, text: string): Record<string, unknown> {
  return {
    version: '0.1',
    operations: [{ op: 'update_props', targetNodeId: nodeId, props: { text } }],
  }
}

interface EnvelopeOptions {
  document?: unknown
  patch?: unknown
  integrity?: unknown
}

function successBody(
  nodeId: string,
  text: string,
  options: EnvelopeOptions = {},
): Record<string, unknown> {
  return {
    success: true,
    patch: 'patch' in options ? options.patch : defaultPatch(nodeId, text),
    document: 'document' in options ? options.document : docWithText([[nodeId, text]]),
    integrity:
      'integrity' in options
        ? options.integrity
        : { selectedNodeId: nodeId, nonTargetNodesUnchanged: true },
  }
}

function failureBody(): Record<string, unknown> {
  return {
    success: false,
    error: {
      code: 'patch_boundary_violation',
      message: 'Patch 触碰了非目标节点',
      issues: [{ path: 'operations[0]', code: 'out_of_scope', message: '目标越界' }],
    },
  }
}

function generateSuccessBody(document: unknown): Record<string, unknown> {
  return { success: true, document }
}

// --- fetcher 注入工具（不 mock 全局 fetch）---

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type FetchHandler = () => Promise<Response>

function scriptedFetcher(handlers: FetchHandler[]): Fetcher {
  let index = 0
  return vi.fn(async () => {
    const handler = handlers[Math.min(index, handlers.length - 1)]
    if (handler === undefined) throw new Error('scriptedFetcher 未配置任何 handler')
    index += 1
    return handler()
  })
}

function okFetcher(bodies: Array<Record<string, unknown>>): Fetcher {
  return scriptedFetcher(bodies.map((body) => async () => jsonResponse(200, body)))
}

interface RoutedHandlers {
  generate?: FetchHandler[]
  refine?: FetchHandler[]
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.href
  return input.url
}

function routedFetcher(handlers: RoutedHandlers): Fetcher {
  const counters = { generate: 0, refine: 0 }
  return vi.fn(async (input: RequestInfo | URL) => {
    const key = requestUrl(input).includes('/generate') ? 'generate' : 'refine'
    const queue = handlers[key]
    if (queue === undefined || queue.length === 0) {
      throw new Error(`routedFetcher 未配置 ${key} handler`)
    }
    const handler = queue[Math.min(counters[key], queue.length - 1)]
    if (handler === undefined) throw new Error(`routedFetcher ${key} handler 缺失`)
    counters[key] += 1
    return handler()
  })
}

interface Deferred {
  promise: Promise<Response>
  resolve: (response: Response) => void
}

function createDeferred(): Deferred {
  let resolve: (response: Response) => void = () => undefined
  const promise = new Promise<Response>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

function callAt(fetcher: Fetcher, index: number) {
  const call = vi.mocked(fetcher).mock.calls[index]
  if (call === undefined) throw new Error(`fetcher 未发生第 ${index + 1} 次调用`)
  return call
}

function requestBodyAt(fetcher: Fetcher, callIndex: number): Record<string, unknown> {
  const init = callAt(fetcher, callIndex)[1]
  const parsed: Record<string, unknown> = JSON.parse(String(init?.body))
  return parsed
}

const SOURCE_TEXT: Record<string, string> = {
  'src/App.tsx': appSourceRaw,
  'src/api/refine.ts': refineSourceRaw,
  'src/api/types.ts': apiTypesSourceRaw,
}

function readSource(relativePath: string): string {
  const source = SOURCE_TEXT[relativePath]
  if (source === undefined) throw new Error(`未登记的源码路径：${relativePath}`)
  return source
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

function typeInstruction(text: string): void {
  fireEvent.change(screen.getByTestId('refine-instruction'), { target: { value: text } })
}

function typePrompt(text: string): void {
  fireEvent.change(screen.getByTestId('generate-prompt'), { target: { value: text } })
}

async function clickSubmit(): Promise<void> {
  await act(async () => {
    fireEvent.click(screen.getByTestId('refine-submit'))
  })
}

async function clickGenerate(): Promise<void> {
  await act(async () => {
    fireEvent.click(screen.getByTestId('generate-submit'))
  })
}

async function settle(): Promise<void> {
  await waitFor(() => expect(screen.queryByTestId('refine-loading')).toBeNull())
}

function isPresent(testId: string): boolean {
  return screen.queryByTestId(testId) !== null
}

/** 已确认轮次数量（读 UI 列表，而不是读内部 state） */
function historyItems(): string[] {
  return screen.queryAllByTestId('refine-history-item').map((el) => el.textContent ?? '')
}

function historyCountText(): string {
  return screen.getByTestId('refine-history-count').textContent ?? ''
}

/** 完成一轮成功精修 */
async function runRound(container: HTMLElement, nodeId: string, instruction: string): Promise<void> {
  selectNode(container, nodeId)
  typeInstruction(instruction)
  await clickSubmit()
  await settle()
}

// ============================================================
// A. 成功入队与请求体形态
// ============================================================

describe('A. 成功入队与请求体形态', () => {
  it('AC-13: 首次提交请求体不含 history 键（三态归一化的前端一侧）', async () => {
    const fetcher = okFetcher([successBody('hero.title', '第一版')])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '改成第一版')

    const body = requestBodyAt(fetcher, 0)
    expect('history' in body).toBe(false)
    expect(Object.keys(body).sort()).toEqual(['document', 'instruction', 'selectedNodeId'])
  })

  it('AC-13: 成功一轮后第二次请求体携带恰 1 个 turn，四字段取自快照与已校验 patch', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', '第一版'),
      successBody('hero.title', '第二版'),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '改成第一版')
    await runRound(container, 'hero.title', '改成第二版')

    const history = requestBodyAt(fetcher, 1).history
    expect(history).toEqual([
      {
        instruction: '改成第一版',
        selectedNodeId: 'hero.title',
        nodeType: 'Heading',
        patchProps: { text: '第一版' },
      },
    ])
  })

  it('AC-14: 连续三轮后请求体 history 为 oldest → newest 的 2 个 turn', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', 'v1'),
      successBody('hero.title', 'v2'),
      successBody('hero.title', 'v3'),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '第一条')
    await runRound(container, 'hero.title', '第二条')
    await runRound(container, 'hero.title', '第三条')

    const history = requestBodyAt(fetcher, 2).history
    expect(Array.isArray(history)).toBe(true)
    const turns = history as Array<Record<string, unknown>>
    expect(turns.map((t) => t.instruction)).toEqual(['第一条', '第二条'])
    expect(turns.map((t) => t.patchProps)).toEqual([{ text: 'v1' }, { text: 'v2' }])
  })

  it('AC-15: nodeType 取自提交时刻的快照文档，而非响应内容', async () => {
    // 响应刻意在 integrity 之外给出与 Button 无关的内容；nodeType 仍必须是 Button
    const fetcher = okFetcher([
      successBody('hero.primary-button', '立即购买'),
      successBody('hero.primary-button', '再短点'),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.primary-button', '改按钮文案')
    await runRound(container, 'hero.primary-button', '再短一点')

    const turns = requestBodyAt(fetcher, 1).history as Array<Record<string, unknown>>
    expect(turns[0]?.nodeType).toBe('Button')
  })

  it('AC-14: 跨节点连续精修时 history 累积两个不同节点的轮次', async () => {
    const first = docWithText([['hero.title', 'T1']])
    const second = docWithText([
      ['hero.title', 'T1'],
      ['hero.subtitle', 'S1'],
    ])
    const fetcher = okFetcher([
      successBody('hero.title', 'T1', { document: first }),
      successBody('hero.subtitle', 'S1', { document: second }),
      successBody('menu.title', 'M1'),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '改标题')
    await runRound(container, 'hero.subtitle', '改副标题')
    await runRound(container, 'menu.title', '改菜单标题')

    const turns = requestBodyAt(fetcher, 2).history as Array<Record<string, unknown>>
    expect(turns.map((t) => t.selectedNodeId)).toEqual(['hero.title', 'hero.subtitle'])
    expect(turns.map((t) => t.nodeType)).toEqual(['Heading', 'Text'])
  })
})

// ============================================================
// B. 失败与丢弃一律不入队
// ============================================================

describe('B. 失败与旧响应不入队', () => {
  it('AC-16: 服务端错误响应后 history 不变', async () => {
    const fetcher = scriptedFetcher([
      async () => jsonResponse(200, successBody('hero.title', 'v1')),
      async () => jsonResponse(502, failureBody()),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '成功轮')
    await runRound(container, 'hero.title', '失败轮')

    expect(isPresent('refine-error')).toBe(true)
    expect(historyItems()).toHaveLength(1)
    expect(historyItems()[0]).toContain('成功轮')
  })

  it('AC-16: C-5（nonTargetNodesUnchanged 非 true）失败不入队', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', 'v1', {
        integrity: { selectedNodeId: 'hero.title', nonTargetNodesUnchanged: false },
      }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', 'C-5 轮')

    expect(isPresent('refine-error')).toBe(true)
    expect(historyItems()).toHaveLength(0)
    expect(isPresent('refine-history-empty')).toBe(true)
  })

  it('AC-16: C-6（integrity 节点不匹配）失败不入队', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', 'v1', {
        integrity: { selectedNodeId: 'hero.subtitle', nonTargetNodesUnchanged: true },
      }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', 'C-6 轮')

    expect(isPresent('refine-error')).toBe(true)
    expect(historyItems()).toHaveLength(0)
  })

  it('AC-16: C-7（返回文档缺失选中节点）失败不入队', async () => {
    const stripped = cloneGold()
    const hero = findJsonNode(stripped.root, 'hero')
    if (hero === null) throw new Error('夹具构造失败')
    hero.children = (hero.children ?? []).filter((child) => child.id !== 'hero.title')
    const fetcher = okFetcher([successBody('hero.title', 'v1', { document: stripped })])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', 'C-7 轮')

    expect(isPresent('refine-error')).toBe(true)
    expect(historyItems()).toHaveLength(0)
  })

  it('AC-16: 本地错误（响应结构非法）不入队', async () => {
    const fetcher = okFetcher([{ success: true, patch: 'not-a-patch' }])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '结构非法轮')

    expect(isPresent('refine-error')).toBe(true)
    expect(historyItems()).toHaveLength(0)
  })

  it('AC-17: 旧响应（提交后切换选择）被丢弃且不入队', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([() => deferred.promise])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('过期轮')
    await clickSubmit()
    selectNode(container, 'hero.subtitle')

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.title', '过期结果')))
    })
    await settle()

    expect(historyItems()).toHaveLength(0)
    expect(nodeText(container, 'hero.title')).not.toContain('过期结果')
  })

  it('AC-16: 失败轮之后的下一轮请求 history 仍只含此前已确认轮次', async () => {
    const fetcher = scriptedFetcher([
      async () => jsonResponse(200, successBody('hero.title', 'v1')),
      async () => jsonResponse(502, failureBody()),
      async () => jsonResponse(200, successBody('hero.title', 'v3')),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '轮一')
    await runRound(container, 'hero.title', '轮二')
    await runRound(container, 'hero.title', '轮三')

    const turns = requestBodyAt(fetcher, 2).history as Array<Record<string, unknown>>
    expect(turns.map((t) => t.instruction)).toEqual(['轮一'])
  })
})

// ============================================================
// C. FIFO 上限
// ============================================================

describe('C. FIFO 上限', () => {
  it('AC-18: 第 21 轮后长度恒为 20 且最旧轮次被淘汰', async () => {
    const fetcher = scriptedFetcher([
      async () => jsonResponse(200, successBody('hero.title', 'v')),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    for (let i = 1; i <= MAX_HISTORY_TURNS + 1; i += 1) {
      await runRound(container, 'hero.title', `轮次-${i}`)
    }

    const items = historyItems()
    expect(items).toHaveLength(MAX_HISTORY_TURNS)
    expect(items.some((text) => text.includes('轮次-1 '))).toBe(false)
    expect(items[items.length - 1]).toContain(`轮次-${MAX_HISTORY_TURNS + 1}`)
    expect(historyCountText()).toContain(`${MAX_HISTORY_TURNS} / ${MAX_HISTORY_TURNS}`)
  })

  it('AC-18: 第 22 轮请求体 history 长度恰为 20（bounded 上界随请求生效）', async () => {
    const fetcher = scriptedFetcher([
      async () => jsonResponse(200, successBody('hero.title', 'v')),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    for (let i = 1; i <= MAX_HISTORY_TURNS + 2; i += 1) {
      await runRound(container, 'hero.title', `轮次-${i}`)
    }

    const turns = requestBodyAt(fetcher, MAX_HISTORY_TURNS + 1).history as unknown[]
    expect(turns).toHaveLength(MAX_HISTORY_TURNS)
  })
})

// ============================================================
// D. 清空与保留
// ============================================================

describe('D. 清空与保留', () => {
  it('AC-19: GENERATE_SUCCESS 清空 conversationHistory', async () => {
    const draft = docWithText([['hero.title', '初稿标题']])
    const fetcher = routedFetcher({
      refine: [async () => jsonResponse(200, successBody('hero.title', 'v1'))],
      generate: [async () => jsonResponse(200, generateSuccessBody(draft))],
    })
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '成功轮')
    expect(historyItems()).toHaveLength(1)

    typePrompt('一个咖啡店着陆页')
    await clickGenerate()

    expect(historyItems()).toHaveLength(0)
    expect(isPresent('refine-history-empty')).toBe(true)
    expect(historyCountText()).toContain(`0 / ${MAX_HISTORY_TURNS}`)
  })

  it('AC-19: 生成失败不清空 history', async () => {
    const fetcher = routedFetcher({
      refine: [async () => jsonResponse(200, successBody('hero.title', 'v1'))],
      generate: [
        async () =>
          jsonResponse(422, {
            success: false,
            error: { code: 'unrecognized_intent', message: '无法识别', issues: [] },
          }),
      ],
    })
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '成功轮')
    typePrompt('无法识别的需求')
    await clickGenerate()

    expect(isPresent('generate-error')).toBe(true)
    expect(historyItems()).toHaveLength(1)
  })

  it('AC-20: 切换选中节点不清空 history（DD-5）', async () => {
    const fetcher = okFetcher([successBody('hero.title', 'v1')])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '成功轮')
    selectNode(container, 'menu.card-1.name')
    selectNode(container, 'contact.form.submit')

    expect(historyItems()).toHaveLength(1)
    expect(historyItems()[0]).toContain('成功轮')
  })
})

// ============================================================
// E. patchProps 确定性派生与净化（DD-17）
// ============================================================

describe('E. patchProps 派生与净化', () => {
  function patch(operations: PatchDocument['operations']): PatchDocument {
    return { version: '0.1', operations }
  }

  it('只取 targetNodeId 等于本次提交节点的操作', () => {
    const result = derivePatchProps(
      patch([
        { op: 'update_props', targetNodeId: 'other', props: { text: '别人的' } },
        { op: 'update_props', targetNodeId: 'mine', props: { text: '我的' } },
      ]),
      'mine',
    )
    expect(result).toEqual({ text: '我的' })
  })

  it('同一节点的多个操作按数组顺序浅合并，后者覆盖前者', () => {
    const result = derivePatchProps(
      patch([
        { op: 'update_props', targetNodeId: 'mine', props: { text: '旧', level: 1 } },
        { op: 'update_props', targetNodeId: 'mine', props: { text: '新' } },
      ]),
      'mine',
    )
    expect(result).toEqual({ text: '新', level: 1 })
  })

  it('保留全部四种 JSON 标量，丢弃对象与数组', () => {
    const result = derivePatchProps(
      patch([
        {
          op: 'update_props',
          targetNodeId: 'mine',
          props: {
            text: 'hi',
            level: 2,
            disabled: false,
            variant: null,
            nested: { a: 1 },
            list: [1, 2],
          },
        },
      ]),
      'mine',
    )
    expect(result).toEqual({ text: 'hi', level: 2, disabled: false, variant: null })
  })

  it('键数超过 16 时按插入顺序保留前 16 个', () => {
    const props: Record<string, unknown> = {}
    for (let i = 0; i < 25; i += 1) props[`k${i}`] = i
    const result = derivePatchProps(
      patch([{ op: 'update_props', targetNodeId: 'mine', props }]),
      'mine',
    )
    expect(Object.keys(result)).toHaveLength(MAX_TURN_PROPS_KEYS)
    expect(Object.keys(result)[0]).toBe('k0')
    expect(Object.keys(result)[MAX_TURN_PROPS_KEYS - 1]).toBe(`k${MAX_TURN_PROPS_KEYS - 1}`)
  })

  it('无匹配操作时得到空对象（不抛错、不产生 undefined 值）', () => {
    const result = derivePatchProps(
      patch([{ op: 'update_props', targetNodeId: 'other', props: { text: 'x' } }]),
      'mine',
    )
    expect(result).toEqual({})
  })

  it('派生是确定性的：同一输入两次调用结果序列化后逐字节相同', () => {
    const input = patch([
      { op: 'update_props', targetNodeId: 'mine', props: { b: 1, a: 2 } },
      { op: 'update_props', targetNodeId: 'mine', props: { c: 3 } },
    ])
    expect(JSON.stringify(derivePatchProps(input, 'mine'))).toBe(
      JSON.stringify(derivePatchProps(input, 'mine')),
    )
  })

  it('净化后的 history 进入请求体：非标量值不出现在 patchProps 中', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', 'v1', {
        patch: {
          version: '0.1',
          operations: [
            {
              op: 'update_props',
              targetNodeId: 'hero.title',
              props: { text: 'v1', nested: { deep: true } },
            },
            { op: 'update_props', targetNodeId: 'hero.subtitle', props: { text: '别人的' } },
          ],
        },
      }),
      successBody('hero.title', 'v2'),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '第一轮')
    await runRound(container, 'hero.title', '第二轮')

    const turns = requestBodyAt(fetcher, 1).history as Array<Record<string, unknown>>
    expect(turns[0]?.patchProps).toEqual({ text: 'v1' })
  })
})

// ============================================================
// F. 多轮稳定性与 UI
// ============================================================

describe('F. 多轮稳定性与 UI', () => {
  it('AC-21: 同节点 3 连轮后目标更新、两个见证节点文案零变更', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', 'v1'),
      successBody('hero.title', 'v2', { document: docWithText([['hero.title', 'v2']]) }),
      successBody('hero.title', 'v3', { document: docWithText([['hero.title', 'v3']]) }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '轮一')
    await runRound(container, 'hero.title', '轮二')
    await runRound(container, 'hero.title', '轮三')

    expect(nodeText(container, 'hero.title')).toBe('v3')
    expect(nodeText(container, WITNESS_A)).toBe(GOLD_SUBTITLE)
    expect(nodeText(container, WITNESS_B)).toBe(GOLD_CARD_NAME)
    expect(historyItems()).toHaveLength(3)
  })

  it('初始为空态：显示空态提示、不渲染列表、计数为 0', () => {
    render(<App fetcher={okFetcher([successBody('hero.title', 'v')])} />)

    expect(isPresent('refine-history-empty')).toBe(true)
    expect(isPresent('refine-history-list')).toBe(false)
    expect(historyCountText()).toContain(`0 / ${MAX_HISTORY_TURNS}`)
  })

  it('每轮次条目显示序号、目标节点与指令原文', async () => {
    const fetcher = okFetcher([successBody('hero.title', 'v1')])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '把标题改短一点')

    const items = historyItems()
    expect(items).toHaveLength(1)
    expect(items[0]).toContain('1')
    expect(items[0]).toContain('hero.title')
    expect(items[0]).toContain('把标题改短一点')
  })

  it('计数随成功轮次单调增长：0 → 1 → 2', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', 'v1'),
      successBody('hero.title', 'v2'),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    expect(historyCountText()).toContain('0 /')
    await runRound(container, 'hero.title', '轮一')
    expect(historyCountText()).toContain('1 /')
    await runRound(container, 'hero.title', '轮二')
    expect(historyCountText()).toContain('2 /')
  })
})

// ============================================================
// G. 源码级约束（无持久化、无状态推断、常量镜像）
// ============================================================

describe('G. 源码级约束', () => {
  it('DD-21: 前端上限常量与后端镜像值一致', () => {
    expect(MAX_HISTORY_TURNS).toBe(20)
    expect(MAX_TURN_PROPS_KEYS).toBe(16)
  })

  it('不引入任何浏览器持久化设施（localStorage / sessionStorage / IndexedDB / cookie）', () => {
    for (const path of ['src/App.tsx', 'src/api/refine.ts', 'src/api/types.ts']) {
      const source = readSource(path)
      for (const token of ['localStorage', 'sessionStorage', 'indexedDB', 'document.cookie']) {
        expect(source.includes(token)).toBe(false)
      }
    }
  })

  it('不引入会话标识字段（conversationId / sessionId / timestamp）', () => {
    for (const path of ['src/App.tsx', 'src/api/types.ts']) {
      const source = readSource(path)
      for (const token of ['conversationId', 'sessionId', 'timestamp']) {
        expect(source.includes(token)).toBe(false)
      }
    }
  })

  it('DD-17: nodeType 由快照文档解析，解析失败时直接返回不发请求', () => {
    const source = readSource('src/App.tsx')
    expect(source).toContain('const snapshotNode = findNodeById(snapshot.document.root, snapshotSelectedNodeId)')
    expect(source).toContain('if (snapshotNode === null) return;')
    expect(source).toContain('const snapshotNodeType = snapshotNode.type;')
  })

  it('DD-10: 空 history 时请求体省略 history 键（客户端实现层面）', () => {
    const source = readSource('src/api/refine.ts')
    expect(source).toContain('request.history && request.history.length > 0')
  })

  it('history 在提交快照中一次性捕获，并以 MAX_HISTORY_TURNS 收束', () => {
    const source = readSource('src/App.tsx')
    expect(source).toContain('history: state.conversationHistory.slice(-MAX_HISTORY_TURNS)')
    expect(source).toContain('history: snapshot.history')
  })
})
