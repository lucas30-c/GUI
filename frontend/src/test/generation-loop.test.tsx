import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import App, { MAX_PROMPT_LENGTH } from '../App'
import { GENERATE_LOCAL_ERROR_MESSAGES } from '../api/generate'
import type { Fetcher } from '../api/refine'
import goldCaseRaw from '../../../examples/dsl/coffee-shop-landing.json'
// 源码文本（用于静态断言）：以 Vite ?raw 导入，避免依赖 node 类型
import appSourceRaw from '../App.tsx?raw'
import generateSourceRaw from '../api/generate.ts?raw'
import apiTypesSourceRaw from '../api/types.ts?raw'

// --- Gold Case 初始文案（App 初始 currentDocument）---

const GOLD_TITLE = 'Brew & Bean'
const GOLD_SUBTITLE = '每一杯都是匠心之作，从产地到杯中的精品咖啡体验'

// --- 初稿夹具（模拟后端返回的咖啡店模板，内容独立于 Gold Case）---

const DRAFT_TITLE = '晨光咖啡工坊'
const DRAFT_SUBTITLE = '清晨现烘的豆子，配一杯慢下来的时间'

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

function draftDoc(overrides: Array<[string, string]> = []): JsonDoc {
  const doc: JsonDoc = {
    version: '0.1',
    metadata: { title: '咖啡店初稿' },
    root: {
      id: 'page',
      type: 'Page',
      props: { title: DRAFT_TITLE },
      children: [
        {
          id: 'hero',
          type: 'Section',
          props: { ariaLabel: '首屏介绍' },
          children: [
            { id: 'hero.title', type: 'Heading', props: { text: DRAFT_TITLE, level: 1 } },
            { id: 'hero.subtitle', type: 'Text', props: { text: DRAFT_SUBTITLE } },
            { id: 'hero.cta', type: 'Button', props: { text: '预订座位', variant: 'primary' } },
          ],
        },
      ],
    },
  }
  for (const [nodeId, text] of overrides) {
    const node = findJsonNode(doc.root, nodeId)
    if (node === null) throw new Error(`夹具构造失败：找不到节点 ${nodeId}`)
    node.props = { ...(node.props ?? {}), text }
  }
  return doc
}

function findJsonNode(node: JsonNode, id: string): JsonNode | null {
  if (node.id === id) return node
  for (const child of node.children ?? []) {
    const found = findJsonNode(child, id)
    if (found !== null) return found
  }
  return null
}

function cloneGold(): JsonDoc {
  const parsed: JsonDoc = JSON.parse(JSON.stringify(goldCaseRaw))
  return parsed
}

function goldWithText(entries: Array<[string, string]>): JsonDoc {
  const base = cloneGold()
  for (const [nodeId, text] of entries) {
    const node = findJsonNode(base.root, nodeId)
    if (node === null) throw new Error(`夹具构造失败：找不到节点 ${nodeId}`)
    node.props = { ...(node.props ?? {}), text }
  }
  return base
}

// --- envelope 夹具 ---

function generateSuccessBody(document: unknown = draftDoc()): Record<string, unknown> {
  return { success: true, document }
}

function generateFailureBody(
  code = 'unrecognized_intent',
  message = '无法识别需求意图',
): Record<string, unknown> {
  return {
    success: false,
    error: {
      code,
      message,
      issues: [{ path: 'prompt', code, message: '无匹配意图' }],
    },
  }
}

function refineSuccessBody(
  nodeId: string,
  text: string,
  document: unknown,
): Record<string, unknown> {
  return {
    success: true,
    patch: {
      version: '0.1',
      operations: [{ op: 'update_props', targetNodeId: nodeId, props: { text } }],
    },
    document,
    integrity: { selectedNodeId: nodeId, nonTargetNodesUnchanged: true },
  }
}

function refineFailureBody(): Record<string, unknown> {
  return {
    success: false,
    error: {
      code: 'patch_boundary_violation',
      message: 'Patch 触碰了非目标节点',
      issues: [{ path: 'operations[0]', code: 'out_of_scope', message: '目标越界' }],
    },
  }
}

// --- fetcher 注入工具（按 URL 分派生成 / 精修）---

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type FetchHandler = () => Promise<Response>

interface RoutedHandlers {
  generate?: FetchHandler[]
  refine?: FetchHandler[]
}

/** 请求目标归一化为字符串 URL（App 与 Client 始终传入相对路径字符串） */
function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.href
  return input.url
}

/** 按端点分派的 fetcher：单一 fetcher prop 同时服务生成与精修两条链路 */
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

function okHandler(status: number, body: unknown): FetchHandler {
  return async () => jsonResponse(status, body)
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

function callUrls(fetcher: Fetcher): string[] {
  return vi.mocked(fetcher).mock.calls.map((call) => String(call[0]))
}

function countCalls(fetcher: Fetcher, fragment: string): number {
  return callUrls(fetcher).filter((url) => url.includes(fragment)).length
}

function requestBodyAt(fetcher: Fetcher, index: number): Record<string, unknown> {
  const init = callAt(fetcher, index)[1]
  const parsed: Record<string, unknown> = JSON.parse(String(init?.body))
  return parsed
}

// --- 源码静态断言工具 ---

const SOURCE_TEXT: Record<string, string> = {
  'src/App.tsx': appSourceRaw,
  'src/api/generate.ts': generateSourceRaw,
  'src/api/types.ts': apiTypesSourceRaw,
}

function readSource(relativePath: string): string {
  const source = SOURCE_TEXT[relativePath]
  if (source === undefined) throw new Error(`未登记的源码路径：${relativePath}`)
  return source
}

// --- 交互工具 ---

function promptInput(): HTMLInputElement {
  const el = screen.getByTestId('generate-prompt')
  if (!(el instanceof HTMLInputElement)) throw new Error('prompt 控件不是 input')
  return el
}

function instructionTextarea(): HTMLTextAreaElement {
  const el = screen.getByTestId('refine-instruction')
  if (!(el instanceof HTMLTextAreaElement)) throw new Error('instruction 控件不是 textarea')
  return el
}

function generateButton(): HTMLElement {
  return screen.getByTestId('generate-submit')
}

function refineButton(): HTMLElement {
  return screen.getByTestId('refine-submit')
}

function isDisabled(element: HTMLElement): boolean {
  return element.hasAttribute('disabled')
}

function isPresent(testId: string): boolean {
  return screen.queryByTestId(testId) !== null
}

function typePrompt(text: string): void {
  fireEvent.change(promptInput(), { target: { value: text } })
}

function typeInstruction(text: string): void {
  fireEvent.change(instructionTextarea(), { target: { value: text } })
}

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

async function clickGenerate(): Promise<void> {
  await act(async () => {
    fireEvent.click(generateButton())
  })
}

async function pressPromptEnter(): Promise<void> {
  await act(async () => {
    fireEvent.keyDown(promptInput(), { key: 'Enter' })
  })
}

async function clickRefine(): Promise<void> {
  await act(async () => {
    fireEvent.click(refineButton())
  })
}

async function pressRefineShortcut(): Promise<void> {
  await act(async () => {
    fireEvent.keyDown(instructionTextarea(), { key: 'Enter', ctrlKey: true })
  })
}

async function settleGenerate(): Promise<void> {
  await waitFor(() => expect(screen.queryByTestId('generate-loading')).toBeNull())
}

async function settleRefine(): Promise<void> {
  await waitFor(() => expect(screen.queryByTestId('refine-loading')).toBeNull())
}

/** 完成一次成功生成（返回值为渲染容器） */
async function runGeneration(prompt: string): Promise<void> {
  typePrompt(prompt)
  await clickGenerate()
  await settleGenerate()
}

// --- A. UI 结构与按钮 disabled（AC-62 ~ AC-64）---

describe('A. 生成区 UI', () => {
  it('AC-62: 页面顶部存在单行文本输入与「生成初稿」按钮', () => {
    const { container } = render(<App />)

    const bar = container.querySelector('.generate-bar')
    expect(bar).not.toBeNull()
    expect(promptInput().getAttribute('type')).toBe('text')
    expect(bar?.contains(promptInput())).toBe(true)
    expect(bar?.contains(generateButton())).toBe(true)
    expect(generateButton().textContent).toBe('生成初稿')
  })

  it('AC-62: 生成区位于画布之前（顶部）', () => {
    const { container } = render(<App />)

    const bar = container.querySelector('.generate-bar')
    const canvas = container.querySelector('.workbench-canvas')
    if (bar === null || canvas === null) throw new Error('生成区或画布缺失')
    // DOCUMENT_POSITION_FOLLOWING = 4：canvas 在 bar 之后
    expect(bar.compareDocumentPosition(canvas) & 4).toBe(4)
  })

  it('AC-63: prompt 为空时生成按钮 disabled', () => {
    render(<App />)

    expect(isDisabled(generateButton())).toBe(true)
  })

  it('AC-63: prompt 仅含空白时生成按钮 disabled 且 Enter 不发请求', async () => {
    const fetcher = routedFetcher({ generate: [okHandler(200, generateSuccessBody())] })
    render(<App fetcher={fetcher} />)

    typePrompt('    ')
    expect(isDisabled(generateButton())).toBe(true)

    await pressPromptEnter()
    expect(vi.mocked(fetcher)).not.toHaveBeenCalled()
  })

  it('AC-63: prompt 超过 500 字符时生成按钮 disabled 且 Enter 不发请求', async () => {
    const fetcher = routedFetcher({ generate: [okHandler(200, generateSuccessBody())] })
    render(<App fetcher={fetcher} />)

    typePrompt('咖'.repeat(MAX_PROMPT_LENGTH + 1))
    expect(isDisabled(generateButton())).toBe(true)

    await pressPromptEnter()
    expect(vi.mocked(fetcher)).not.toHaveBeenCalled()
  })

  it('AC-63: prompt 恰好 500 字符时按钮可用', () => {
    render(<App />)

    typePrompt('咖'.repeat(MAX_PROMPT_LENGTH))
    expect(isDisabled(generateButton())).toBe(false)
  })

  it('AC-63: prompt 合法时在输入框内按 Enter 触发生成请求（发送 trim 后的 prompt）', async () => {
    const fetcher = routedFetcher({ generate: [okHandler(200, generateSuccessBody())] })
    render(<App fetcher={fetcher} />)

    typePrompt('  我要一个咖啡店的落地页  ')
    await pressPromptEnter()
    await settleGenerate()

    expect(countCalls(fetcher, '/generate')).toBe(1)
    expect(requestBodyAt(fetcher, 0)).toEqual({ prompt: '我要一个咖啡店的落地页' })
  })

  it('AC-64: 生成请求在途期间按钮 disabled 且 loading 指示可见', async () => {
    const deferred = createDeferred()
    const fetcher = routedFetcher({ generate: [() => deferred.promise] })
    render(<App fetcher={fetcher} />)

    typePrompt('咖啡店')
    await clickGenerate()

    expect(isPresent('generate-loading')).toBe(true)
    expect(isDisabled(generateButton())).toBe(true)
    expect(generateButton().textContent).toBe('生成中...')

    await act(async () => {
      deferred.resolve(jsonResponse(200, generateSuccessBody()))
    })
    await settleGenerate()
  })
})

// --- B. GENERATE_SUCCESS 原子设置 9 项（AC-52 / AC-65）---

describe('B. 生成成功的原子状态提交', () => {
  it('AC-52 / AC-65: 单次成功生成原子清空全部旧状态并替换文档', async () => {
    const fetcher = routedFetcher({
      refine: [
        okHandler(200, refineSuccessBody('hero.title', '旧文档精修', goldWithText([['hero.title', '旧文档精修']]))),
        okHandler(422, refineFailureBody()),
      ],
      generate: [
        okHandler(422, generateFailureBody()),
        okHandler(200, generateSuccessBody()),
      ],
    })
    const { container } = render(<App fetcher={fetcher} />)

    // 建立"旧成功状态"：一轮成功精修 → lastPatch / lastIntegrity / lastSuccess
    selectNode(container, 'hero.title')
    typeInstruction('set_text:旧文档精修')
    await clickRefine()
    await settleRefine()
    // 再来一轮失败精修 → error 非空，同时保留 lastPatch
    typeInstruction('set_text:失败一轮')
    await clickRefine()
    await settleRefine()
    // 一次失败生成 → generateError 非空
    typePrompt('无法识别的需求')
    await clickGenerate()
    await settleGenerate()

    // 提交前基线：8 项均为非初始值
    expect(isPresent('refine-patch')).toBe(true)
    expect(isPresent('refine-integrity')).toBe(true)
    expect(isPresent('refine-last-success')).toBe(true)
    expect(isPresent('refine-error')).toBe(true)
    expect(isPresent('generate-error')).toBe(true)
    expect(screen.getByTestId('panel-node-id').textContent).toBe('hero.title')
    expect(instructionTextarea().value).toBe('set_text:失败一轮')
    expect(nodeText(container, 'hero.title')).toBe('旧文档精修')

    // 成功生成
    typePrompt('我要一个咖啡店的落地页')
    await clickGenerate()
    await settleGenerate()

    // 1. currentDocument 替换为响应 document
    expect(nodeText(container, 'hero.title')).toBe(DRAFT_TITLE)
    expect(nodeText(container, 'hero.subtitle')).toBe(DRAFT_SUBTITLE)
    expect(container.querySelector('[data-node-id="menu"]')).toBeNull()
    // 2. selectedNodeId = null（无选中态、面板回到未选中）
    expect(container.querySelectorAll('[data-selected]')).toHaveLength(0)
    expect(container.querySelectorAll('.dsl-node-selected')).toHaveLength(0)
    expect(isPresent('panel-node-id')).toBe(false)
    // 3~5. lastPatch / lastIntegrity / lastSuccess 清空
    expect(isPresent('refine-patch')).toBe(false)
    expect(isPresent('refine-integrity')).toBe(false)
    expect(isPresent('refine-last-success')).toBe(false)
    expect(isPresent('refine-result-empty')).toBe(true)
    // 6. error 清空
    expect(isPresent('refine-error')).toBe(false)
    // 7. instruction 清空
    expect(instructionTextarea().value).toBe('')
    // 8. prompt 清空
    expect(promptInput().value).toBe('')
    // 9. generateError 清空
    expect(isPresent('generate-error')).toBe(false)
  })

  it('AC-52: 生成成功后旧文档节点不再存在于 DOM（整文档替换而非局部合并）', async () => {
    const fetcher = routedFetcher({ generate: [okHandler(200, generateSuccessBody())] })
    const { container } = render(<App fetcher={fetcher} />)

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    await runGeneration('咖啡店')

    expect(container.querySelector('[data-node-id="hero.primary-button"]')).toBeNull()
    expect(nodeText(container, 'hero.subtitle')).toBe(DRAFT_SUBTITLE)
  })

  it('AC-53: 源码在 GENERATE_SUCCESS dispatch 之前同步重置 latestSelectedNodeIdRef', () => {
    const source = readSource('src/App.tsx')

    const resetIndex = source.indexOf('latestSelectedNodeIdRef.current = null')
    const dispatchIndex = source.indexOf("dispatch({ type: 'GENERATE_SUCCESS'")
    expect(resetIndex).toBeGreaterThan(-1)
    expect(dispatchIndex).toBeGreaterThan(-1)
    expect(resetIndex).toBeLessThan(dispatchIndex)
    // 二者位于同一 handler 的相邻语句（中间不存在 await）
    const between = source.slice(resetIndex, dispatchIndex)
    expect(between).not.toMatch(/await/)
  })

  it('AC-52: 成功提交只有一个 GENERATE_SUCCESS 入口', () => {
    const source = readSource('src/App.tsx')

    expect(source.match(/case 'GENERATE_SUCCESS'/g)).toHaveLength(1)
    expect(source.match(/dispatch\(\{\s*type: 'GENERATE_SUCCESS'/g)).toHaveLength(1)
  })

  it('AC-61: 生成成功后 generateLoading 为 false（loading 指示消失、按钮恢复文案）', async () => {
    const fetcher = routedFetcher({ generate: [okHandler(200, generateSuccessBody())] })
    render(<App fetcher={fetcher} />)

    await runGeneration('咖啡店')

    expect(isPresent('generate-loading')).toBe(false)
    expect(generateButton().textContent).toBe('生成初稿')
  })
})

// --- C. 生成失败隔离（AC-54 / AC-55 / AC-66）---

describe('C. 生成失败隔离', () => {
  it('AC-54 / AC-55: 服务端失败不污染文档与精修成功状态，DOM 与提交前一致', async () => {
    const fetcher = routedFetcher({
      refine: [
        okHandler(200, refineSuccessBody('hero.title', '精修保留', goldWithText([['hero.title', '精修保留']]))),
      ],
      generate: [okHandler(422, generateFailureBody())],
    })
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:精修保留')
    await clickRefine()
    await settleRefine()

    typeInstruction('set_text:提交前指令')
    const canvasBefore = container.querySelector('.workbench-canvas')?.innerHTML

    typePrompt('无法识别的需求')
    await clickGenerate()
    await settleGenerate()

    // 生成侧错误可见
    expect(screen.getByTestId('generate-error-code').textContent).toBe('unrecognized_intent')
    expect(screen.getByTestId('generate-error-kind').textContent).toBe('服务端错误')
    expect(screen.getByTestId('generate-error-issue').textContent).toContain('unrecognized_intent')
    // 文档与精修状态未被污染
    expect(container.querySelector('.workbench-canvas')?.innerHTML).toBe(canvasBefore)
    expect(nodeText(container, 'hero.title')).toBe('精修保留')
    expect(screen.getByTestId('panel-node-id').textContent).toBe('hero.title')
    expect(isPresent('refine-patch')).toBe(true)
    expect(isPresent('refine-integrity')).toBe(true)
    expect(isPresent('refine-last-success')).toBe(true)
    expect(isPresent('refine-error')).toBe(false)
    expect(instructionTextarea().value).toBe('set_text:提交前指令')
    // prompt 保留（失败不消费输入）
    expect(promptInput().value).toBe('无法识别的需求')
  })

  it('AC-54: 生成失败不写入精修错误面板（两侧 error 分离）', async () => {
    const fetcher = routedFetcher({ generate: [okHandler(502, generateFailureBody('provider_error', '上游失败'))] })
    render(<App fetcher={fetcher} />)

    typePrompt('咖啡店')
    await clickGenerate()
    await settleGenerate()

    expect(isPresent('generate-error')).toBe(true)
    expect(isPresent('refine-error')).toBe(false)
  })

  it('AC-66: 三类本地错误文案可区分', async () => {
    const cases: Array<[FetchHandler, string]> = [
      [
        async () => {
          throw new TypeError('Failed to fetch')
        },
        GENERATE_LOCAL_ERROR_MESSAGES.network_error,
      ],
      [async () => new Response('<html>', { status: 200 }), GENERATE_LOCAL_ERROR_MESSAGES.invalid_json],
      [okHandler(200, { success: true }), GENERATE_LOCAL_ERROR_MESSAGES.invalid_response],
    ]

    for (const [handler, expected] of cases) {
      const fetcher = routedFetcher({ generate: [handler] })
      const view = render(<App fetcher={fetcher} />)

      typePrompt('咖啡店')
      await clickGenerate()
      await settleGenerate()

      expect(screen.getByTestId('generate-error-kind').textContent).toBe('本地错误')
      expect(screen.getByTestId('generate-error-message').textContent).toBe(expected)
      expect(isPresent('generate-error-issues')).toBe(false)
      view.unmount()
    }
  })

  it('AC-61: 生成失败后 generateLoading 也回到 false', async () => {
    const fetcher = routedFetcher({
      generate: [
        async () => {
          throw new TypeError('Failed to fetch')
        },
      ],
    })
    render(<App fetcher={fetcher} />)

    typePrompt('咖啡店')
    await clickGenerate()
    await settleGenerate()

    expect(isPresent('generate-loading')).toBe(false)
  })

  it('AC-54: 生成失败后重试成功，错误面板被清空', async () => {
    const fetcher = routedFetcher({
      generate: [okHandler(422, generateFailureBody()), okHandler(200, generateSuccessBody())],
    })
    const { container } = render(<App fetcher={fetcher} />)

    typePrompt('无法识别的需求')
    await clickGenerate()
    await settleGenerate()
    expect(isPresent('generate-error')).toBe(true)

    typePrompt('咖啡店')
    await clickGenerate()
    await settleGenerate()

    expect(isPresent('generate-error')).toBe(false)
    expect(nodeText(container, 'hero.title')).toBe(DRAFT_TITLE)
  })
})

// --- D. 生成侧重复提交守卫（AC-56）---

describe('D. 生成重复提交守卫', () => {
  it('AC-56: 在途期间通过 Enter 快捷键再次提交不发起第二个请求', async () => {
    const deferred = createDeferred()
    const fetcher = routedFetcher({ generate: [() => deferred.promise] })
    render(<App fetcher={fetcher} />)

    typePrompt('咖啡店')
    await clickGenerate()
    // 快捷键路径：绕过按钮 disabled，由 generateInFlightRef 同步守卫拦截
    await pressPromptEnter()
    await pressPromptEnter()

    expect(countCalls(fetcher, '/generate')).toBe(1)

    await act(async () => {
      deferred.resolve(jsonResponse(200, generateSuccessBody()))
    })
    await settleGenerate()
  })

  it('AC-56: 同一同步窗口内连续两次触发生成只发出一个请求', async () => {
    const deferred = createDeferred()
    const fetcher = routedFetcher({ generate: [() => deferred.promise] })
    render(<App fetcher={fetcher} />)

    typePrompt('咖啡店')
    await act(async () => {
      fireEvent.keyDown(promptInput(), { key: 'Enter' })
      fireEvent.keyDown(promptInput(), { key: 'Enter' })
    })

    expect(countCalls(fetcher, '/generate')).toBe(1)

    await act(async () => {
      deferred.resolve(jsonResponse(200, generateSuccessBody()))
    })
    await settleGenerate()
  })

  it('AC-56: 生成结束后可再次提交（ref 已释放）', async () => {
    const fetcher = routedFetcher({
      generate: [okHandler(200, generateSuccessBody()), okHandler(200, generateSuccessBody())],
    })
    render(<App fetcher={fetcher} />)

    await runGeneration('咖啡店')
    await runGeneration('咖啡店第二次')

    expect(countCalls(fetcher, '/generate')).toBe(2)
  })
})

// --- E. 跨链路互斥（AC-57 ~ AC-60）---

describe('E. 生成与精修互斥', () => {
  it('AC-57: 生成在途期间精修按钮 disabled 且 Ctrl/Cmd+Enter 不发精修请求', async () => {
    const deferred = createDeferred()
    const fetcher = routedFetcher({
      generate: [() => deferred.promise],
      refine: [okHandler(200, refineSuccessBody('hero.title', 'x', goldWithText([['hero.title', 'x']])))],
    })
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:生成期间的精修')
    typePrompt('咖啡店')
    await clickGenerate()

    expect(isDisabled(refineButton())).toBe(true)
    await pressRefineShortcut()
    await clickRefine()
    expect(countCalls(fetcher, '/refine')).toBe(0)

    await act(async () => {
      deferred.resolve(jsonResponse(200, generateSuccessBody()))
    })
    await settleGenerate()
  })

  it('AC-57: 生成在途期间节点选择不被禁用', async () => {
    const deferred = createDeferred()
    const fetcher = routedFetcher({ generate: [() => deferred.promise] })
    const { container } = render(<App fetcher={fetcher} />)

    typePrompt('咖啡店')
    await clickGenerate()

    // 生成中仍可改变选中态
    selectNode(container, 'hero.subtitle')
    expect(screen.getByTestId('panel-node-id').textContent).toBe('hero.subtitle')
    const selected = container.querySelector('[data-node-id="hero.subtitle"]')
    expect(selected?.getAttribute('data-selected')).toBe('true')

    selectNode(container, 'hero.title')
    expect(screen.getByTestId('panel-node-id').textContent).toBe('hero.title')

    await act(async () => {
      deferred.resolve(jsonResponse(200, generateSuccessBody()))
    })
    await settleGenerate()
  })

  it('AC-58: 精修在途期间生成按钮 disabled 且 Enter 不发生成请求', async () => {
    const deferred = createDeferred()
    const fetcher = routedFetcher({
      refine: [() => deferred.promise],
      generate: [okHandler(200, generateSuccessBody())],
    })
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:精修期间')
    typePrompt('咖啡店')
    await clickRefine()

    expect(isDisabled(generateButton())).toBe(true)
    await pressPromptEnter()
    await clickGenerate()
    expect(countCalls(fetcher, '/generate')).toBe(0)

    await act(async () => {
      deferred.resolve(
        jsonResponse(200, refineSuccessBody('hero.title', '精修期间', goldWithText([['hero.title', '精修期间']]))),
      )
    })
    await settleRefine()
    expect(nodeText(container, 'hero.title')).toBe('精修期间')
  })

  it('AC-59: 同一同步窗口先精修后生成 → 只有精修请求发出', async () => {
    const deferred = createDeferred()
    const fetcher = routedFetcher({
      refine: [() => deferred.promise],
      generate: [okHandler(200, generateSuccessBody())],
    })
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:同步窗口精修先行')
    typePrompt('咖啡店')

    // 同一 act 块内先触发精修快捷键、再触发生成快捷键：
    // 生成侧由 inFlightRef 同步守卫拦截（未依赖按钮 disabled）
    let generateDisabledMidWindow = true
    await act(async () => {
      fireEvent.keyDown(instructionTextarea(), { key: 'Enter', ctrlKey: true })
      // 同步窗口内 React 尚未重渲染：生成按钮此刻仍未 disabled
      generateDisabledMidWindow = isDisabled(generateButton())
      fireEvent.keyDown(promptInput(), { key: 'Enter' })
    })

    expect(generateDisabledMidWindow).toBe(false)
    expect(countCalls(fetcher, '/refine')).toBe(1)
    expect(countCalls(fetcher, '/generate')).toBe(0)

    await act(async () => {
      deferred.resolve(
        jsonResponse(
          200,
          refineSuccessBody('hero.title', '同步窗口精修先行', goldWithText([['hero.title', '同步窗口精修先行']])),
        ),
      )
    })
    await settleRefine()
    expect(nodeText(container, 'hero.title')).toBe('同步窗口精修先行')
  })

  it('AC-60: 同一同步窗口先生成后精修 → 只有生成请求发出', async () => {
    const deferred = createDeferred()
    const fetcher = routedFetcher({
      generate: [() => deferred.promise],
      refine: [okHandler(200, refineSuccessBody('hero.title', 'x', goldWithText([['hero.title', 'x']])))],
    })
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:同步窗口精修被拦截')
    typePrompt('咖啡店')

    // 同一 act 块内先触发生成、再触发精修快捷键：
    // 精修侧由 generateInFlightRef 同步守卫拦截（未依赖按钮 disabled）
    let refineDisabledMidWindow = true
    await act(async () => {
      fireEvent.keyDown(promptInput(), { key: 'Enter' })
      // 同步窗口内 React 尚未重渲染：精修按钮此刻仍未 disabled
      refineDisabledMidWindow = isDisabled(refineButton())
      fireEvent.keyDown(instructionTextarea(), { key: 'Enter', ctrlKey: true })
    })

    expect(refineDisabledMidWindow).toBe(false)
    expect(countCalls(fetcher, '/generate')).toBe(1)
    expect(countCalls(fetcher, '/refine')).toBe(0)

    await act(async () => {
      deferred.resolve(jsonResponse(200, generateSuccessBody()))
    })
    await settleGenerate()
    expect(nodeText(container, 'hero.title')).toBe(DRAFT_TITLE)
  })

  it('AC-59 / AC-60（静态）: 两个提交 handler 均同步检查双 ref', () => {
    const source = readSource('src/App.tsx')

    const refineStart = source.indexOf('async function submitRefinement()')
    const refineDispatch = source.indexOf("dispatch({ type: 'REFINE_START' })")
    const generateStart = source.indexOf('async function submitGeneration()')
    const generateDispatch = source.indexOf("dispatch({ type: 'GENERATE_START' })")
    expect(refineStart).toBeGreaterThan(-1)
    expect(generateStart).toBeGreaterThan(-1)

    const refineGuard = source.slice(refineStart, refineDispatch)
    expect(refineGuard).toContain('inFlightRef.current')
    expect(refineGuard).toContain('generateInFlightRef.current')

    const generateGuard = source.slice(generateStart, generateDispatch)
    expect(generateGuard).toContain('generateInFlightRef.current')
    expect(generateGuard).toContain('inFlightRef.current')
    // 先设 ref 再 dispatch START
    expect(source.indexOf('generateInFlightRef.current = true')).toBeLessThan(generateDispatch)
  })

  it('DD-21（静态）: 未引入生成序号 / latest-wins / 取消语义', () => {
    const source = readSource('src/App.tsx')

    expect(source).not.toMatch(/generationSeqRef/)
    expect(source).not.toMatch(/AbortController/)
    expect(source).not.toMatch(/AbortSignal/)
  })
})

// --- F. 生成 → 选择 → 精修串联（AC-67）---

describe('F. 生成后精修闭环', () => {
  it('AC-67: 生成成功后选中新文档节点并精修成功', async () => {
    const refined = draftDoc([['hero.title', '精修后的初稿标题']])
    const fetcher = routedFetcher({
      generate: [okHandler(200, generateSuccessBody())],
      refine: [okHandler(200, refineSuccessBody('hero.title', '精修后的初稿标题', refined))],
    })
    const { container } = render(<App fetcher={fetcher} />)

    await runGeneration('我要一个咖啡店的落地页')
    expect(nodeText(container, 'hero.title')).toBe(DRAFT_TITLE)

    selectNode(container, 'hero.title')
    expect(screen.getByTestId('panel-node-id').textContent).toBe('hero.title')
    expect(screen.getByTestId('panel-node-type').textContent).toBe('Heading')

    typeInstruction('set_text:精修后的初稿标题')
    await clickRefine()
    await settleRefine()

    expect(nodeText(container, 'hero.title')).toBe('精修后的初稿标题')
    // 见证节点不变
    expect(nodeText(container, 'hero.subtitle')).toBe(DRAFT_SUBTITLE)
    expect(isPresent('refine-patch')).toBe(true)
    expect(screen.getByTestId('refine-integrity-flag').textContent).toContain('true')
    expect(screen.getByTestId('refine-last-success').textContent).toContain('hero.title')
  })

  it('AC-67: 精修请求携带的 document 为生成返回的初稿（不是 Gold Case）', async () => {
    const refined = draftDoc([['hero.title', '第二版标题']])
    const fetcher = routedFetcher({
      generate: [okHandler(200, generateSuccessBody())],
      refine: [okHandler(200, refineSuccessBody('hero.title', '第二版标题', refined))],
    })
    const { container } = render(<App fetcher={fetcher} />)

    await runGeneration('咖啡店')
    selectNode(container, 'hero.title')
    typeInstruction('set_text:第二版标题')
    await clickRefine()
    await settleRefine()

    const body = requestBodyAt(fetcher, 1)
    expect(body.selectedNodeId).toBe('hero.title')
    expect(body.document).toEqual(draftDoc())
    expect(JSON.stringify(body.document)).not.toContain(GOLD_TITLE)
    expect(JSON.stringify(body.document)).not.toContain(GOLD_SUBTITLE)
  })

  it('AC-67: 生成 → 精修 → 再次生成，链路可重复', async () => {
    const refined = draftDoc([['hero.title', '中间一轮']])
    const fetcher = routedFetcher({
      generate: [okHandler(200, generateSuccessBody()), okHandler(200, generateSuccessBody())],
      refine: [okHandler(200, refineSuccessBody('hero.title', '中间一轮', refined))],
    })
    const { container } = render(<App fetcher={fetcher} />)

    await runGeneration('咖啡店')
    selectNode(container, 'hero.title')
    typeInstruction('set_text:中间一轮')
    await clickRefine()
    await settleRefine()
    expect(nodeText(container, 'hero.title')).toBe('中间一轮')

    await runGeneration('咖啡店再来一次')

    expect(nodeText(container, 'hero.title')).toBe(DRAFT_TITLE)
    expect(isPresent('refine-patch')).toBe(false)
    expect(container.querySelectorAll('[data-selected]')).toHaveLength(0)
  })
})

// --- G. 边界安全静态断言（AC-51 / AC-78 / AC-79）---

describe('G. 前端边界安全', () => {
  it('AC-51: generate.ts 复用 refine.ts 导出的守卫，不重复实现', () => {
    const source = readSource('src/api/generate.ts')

    expect(source).toMatch(/import\s*\{[^}]*isDslDocumentShape[^}]*\}\s*from\s*'\.\/refine'/)
    expect(source).toMatch(/isRecord/)
    expect(source).not.toMatch(/function isDslDocumentShape/)
    expect(source).not.toMatch(/function isRecord/)
  })

  it('AC-51 / AC-78: 生成侧源码无 any 与类型断言绕过', () => {
    for (const path of ['src/api/generate.ts', 'src/api/types.ts', 'src/App.tsx']) {
      const source = readSource(path)
      expect(source).not.toMatch(/:\s*any\b/)
      expect(source).not.toMatch(/<any>/)
      expect(source).not.toMatch(/as\s+any\b/)
      expect(source).not.toMatch(/as\s+GenerateSuccess/)
      expect(source).not.toMatch(/as\s+GenerateFailure/)
      expect(source).not.toMatch(/as\s+GenerateClientResult/)
      expect(source).not.toMatch(/as\s+unknown\s+as/)
    }
  })

  it('AC-79: 生成侧源码无禁止内容', () => {
    for (const path of ['src/api/generate.ts', 'src/App.tsx']) {
      const source = readSource(path)
      expect(source).not.toMatch(/dangerouslySetInnerHTML/)
      expect(source).not.toMatch(/\beval\(/)
      expect(source).not.toMatch(/new Function\(/)
    }
  })

  it('DD-16: App 不本地拼装或修改 DSL（新文档只来自响应 document）', () => {
    const source = readSource('src/App.tsx')

    expect(source).not.toMatch(/applyPatch/)
    expect(source).not.toMatch(/currentDocument:\s*\{/)
    expect(source.match(/currentDocument: action\./g)).toHaveLength(1)
    expect(source).toMatch(/currentDocument: generatedDocument/)
  })

  it('DD-5: 前端 MAX_PROMPT_LENGTH 与后端同值 500', () => {
    expect(MAX_PROMPT_LENGTH).toBe(500)
    expect(readSource('src/App.tsx')).toMatch(/MAX_PROMPT_LENGTH = 500/)
  })
})
