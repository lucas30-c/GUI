import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import App, { INTEGRITY_ERROR_MESSAGES } from '../App'
import { LOCAL_ERROR_MESSAGES } from '../api/refine'
import type { Fetcher } from '../api/refine'
import goldCaseRaw from '../../../examples/dsl/coffee-shop-landing.json'
// 源码文本（用于静态断言）：以 Vite ?raw 导入，避免依赖 node 类型
import appSourceRaw from '../App.tsx?raw'
import refineSourceRaw from '../api/refine.ts?raw'
import apiTypesSourceRaw from '../api/types.ts?raw'
import viteConfigSourceRaw from '../../vite.config.ts?raw'
import playwrightConfigSourceRaw from '../../playwright.config.ts?raw'

// --- Gold Case 初始文案（来自 examples/dsl/coffee-shop-landing.json）---

const GOLD_TITLE = 'Brew & Bean'
const GOLD_BUTTON = '查看菜单'
const GOLD_SUBTITLE = '每一杯都是匠心之作，从产地到杯中的精品咖啡体验'
const GOLD_CARD_NAME = '经典拿铁'

// --- JSON 文档工具（响应夹具构造，不复用生产类型以便构造非法结构）---

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
  extra?: Record<string, unknown>
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
    ...(options.extra ?? {}),
  }
}

function failureBody(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    success: false,
    error: {
      code: 'patch_boundary_violation',
      message: 'Patch 触碰了非目标节点',
      issues: [{ path: 'operations[0]', code: 'out_of_scope', message: '目标越界' }],
    },
    ...extra,
  }
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

/** 取出第 index 次调用参数（noUncheckedIndexedAccess 下需显式断言存在） */
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

/** 读取仓库内源码文本（供静态断言使用）；键为相对 frontend/ 根目录的路径 */
const SOURCE_TEXT: Record<string, string> = {
  'src/App.tsx': appSourceRaw,
  'src/api/refine.ts': refineSourceRaw,
  'src/api/types.ts': apiTypesSourceRaw,
  'vite.config.ts': viteConfigSourceRaw,
  'playwright.config.ts': playwrightConfigSourceRaw,
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

function submitButton(): HTMLElement {
  return screen.getByTestId('refine-submit')
}

/** 提交按钮是否 disabled（不依赖 jest-dom 匹配器，src 工程未引入其类型） */
function isSubmitDisabled(): boolean {
  return submitButton().hasAttribute('disabled')
}

/** instruction textarea 的当前值 */
function instructionTextarea(): HTMLTextAreaElement {
  const el = screen.getByTestId('refine-instruction')
  if (!(el instanceof HTMLTextAreaElement)) throw new Error('instruction 控件不是 textarea')
  return el
}

/** 指定 testid 元素是否存在于文档中 */
function isPresent(testId: string): boolean {
  return screen.queryByTestId(testId) !== null
}

async function clickSubmit(): Promise<void> {
  await act(async () => {
    fireEvent.click(submitButton())
  })
}

async function pressShortcut(modifier: 'ctrlKey' | 'metaKey'): Promise<void> {
  await act(async () => {
    fireEvent.keyDown(screen.getByTestId('refine-instruction'), {
      key: 'Enter',
      [modifier]: true,
    })
  })
}

async function settle(): Promise<void> {
  await waitFor(() => expect(screen.queryByTestId('refine-loading')).toBeNull())
}

/** 完成一轮成功精修（用于建立"上一轮成功结果"基线） */
async function runSuccessRound(
  container: HTMLElement,
  nodeId: string,
  text: string,
): Promise<void> {
  selectNode(container, nodeId)
  typeInstruction(`set_text:${text}`)
  await clickSubmit()
  await settle()
}

// --- C. 完整性检查与原子提交（AC-24 ~ AC-42）---

describe('C. 提交快照与原子提交', () => {
  it('AC-24: 提交后修改 instruction，请求体仍为提交时刻的快照值', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([() => deferred.promise])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:快照文案')
    await clickSubmit()
    typeInstruction('set_text:提交后又改的文案')

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.title', '快照文案')))
    })
    await settle()

    expect(requestBodyAt(fetcher, 0).instruction).toBe('set_text:快照文案')
    expect(nodeText(container, 'hero.title')).toBe('快照文案')
  })

  it('AC-24(b): 响应校验使用快照 selectedNodeId，而非响应到达时的当前 state', async () => {
    const fetcher = okFetcher([successBody('hero.title', '快照校验')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '快照校验')

    expect(requestBodyAt(fetcher, 0).selectedNodeId).toBe('hero.title')
    expect(screen.getByTestId('refine-integrity-node').textContent).toContain('hero.title')
  })

  it('AC-25: REFINE_START 设 loading 并清除上一轮遗留的 error', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([
      async () => {
        throw new TypeError('Failed to fetch')
      },
      () => deferred.promise,
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:第一次失败')
    await clickSubmit()
    await settle()
    expect(isPresent('refine-error')).toBe(true)

    typeInstruction('set_text:第二次尝试')
    await clickSubmit()

    expect(isPresent('refine-loading')).toBe(true)
    expect(screen.queryByTestId('refine-error')).toBeNull()

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.title', '第二次尝试')))
    })
    await settle()
  })

  it('AC-26: 源码中成功提交只有一个 REFINE_SUCCESS 入口，且不使用 useState 拼凑', () => {
    const source = readSource('src/App.tsx')
    expect(source).not.toContain('useState')
    expect(source.match(/currentDocument: action\.document/g)).toHaveLength(1)
    expect(source.match(/case 'REFINE_SUCCESS'/g)).toHaveLength(1)
    expect(source.match(/dispatch\(\{\s*type: 'REFINE_SUCCESS'/g)).toHaveLength(1)
  })

  it('AC-26(b): 一次成功后 document / patch / integrity / lastSuccess 同时可见（原子提交）', async () => {
    const fetcher = okFetcher([successBody('hero.title', '原子提交')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '原子提交')

    expect(nodeText(container, 'hero.title')).toBe('原子提交')
    expect(isPresent('refine-patch')).toBe(true)
    expect(isPresent('refine-integrity')).toBe(true)
    expect(screen.getByTestId('refine-last-success').textContent).toContain('hero.title')
  })

  it('AC-27: 成功后 currentDocument 严格等于响应 document（整文档替换，非 patch 应用）', async () => {
    // 响应 document 同时改了 hero.title 与 hero.subtitle，但 patch 只声明了 hero.title
    const document = docWithText([
      ['hero.title', '服务端标题'],
      ['hero.subtitle', '服务端副标题'],
    ])
    const fetcher = okFetcher([
      successBody('hero.title', '服务端标题', { document }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '服务端标题')

    expect(nodeText(container, 'hero.title')).toBe('服务端标题')
    expect(nodeText(container, 'hero.subtitle')).toBe('服务端副标题')
  })

  it('AC-28: integrity.selectedNodeId 与快照不一致 → 不提交，成功状态不变', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', '不该生效', {
        integrity: { selectedNodeId: 'menu.title', nonTargetNodesUnchanged: true },
      }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:不该生效')
    await clickSubmit()
    await settle()

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(screen.queryByTestId('refine-integrity')).toBeNull()
    expect(screen.queryByTestId('refine-last-success')).toBeNull()
    expect(screen.getByTestId('refine-error-message').textContent).toBe(
      INTEGRITY_ERROR_MESSAGES.nodeMismatch,
    )
  })

  it('AC-29: 返回 document 中不存在快照 selectedNodeId → 不提交，成功状态不变', async () => {
    const strangerDoc: JsonDoc = {
      version: '0.1',
      root: {
        id: 'page',
        type: 'Page',
        props: { title: '陌生文档' },
        children: [{ id: 'other.node', type: 'Text', props: { text: '陌生内容' } }],
      },
    }
    const fetcher = okFetcher([
      successBody('hero.title', '不该生效', { document: strangerDoc }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:不该生效')
    await clickSubmit()
    await settle()

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(container.querySelector('[data-node-id="other.node"]')).toBeNull()
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(screen.getByTestId('refine-error-message').textContent).toBe(
      INTEGRITY_ERROR_MESSAGES.nodeMissing,
    )
  })

  it('AC-30: nonTargetNodesUnchanged === false（API Client 放行）→ 提交层 C-5 拒绝', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', '不该生效', {
        integrity: { selectedNodeId: 'hero.title', nonTargetNodesUnchanged: false },
      }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:不该生效')
    await clickSubmit()
    await settle()

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(screen.queryByTestId('refine-integrity')).toBeNull()
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(screen.getByTestId('refine-error-message').textContent).toBe(
      INTEGRITY_ERROR_MESSAGES.nonTargetChanged,
    )
  })

  it('AC-31: nonTargetNodesUnchanged 缺失（API Client 判为 invalid_response）→ 不提交', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', '不该生效', {
        integrity: { selectedNodeId: 'hero.title' },
      }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:不该生效')
    await clickSubmit()
    await settle()

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(screen.getByTestId('refine-error-code').textContent).toBe('invalid_response')
    expect(screen.getByTestId('refine-error-message').textContent).toBe(
      LOCAL_ERROR_MESSAGES.invalid_response,
    )
  })

  it('AC-32: kind:"server" 结果不更新任何成功状态（上一轮结果完整保留）', async () => {
    const fetcher = scriptedFetcher([
      async () => jsonResponse(200, successBody('hero.title', '第一轮标题')),
      async () => jsonResponse(422, failureBody()),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '第一轮标题')

    typeInstruction('set_text:第二轮失败')
    await clickSubmit()
    await settle()

    expect(nodeText(container, 'hero.title')).toBe('第一轮标题')
    expect(screen.getByTestId('refine-patch-target').textContent).toBe('hero.title')
    expect(screen.getByTestId('refine-patch-props').textContent).toContain('第一轮标题')
    expect(screen.getByTestId('refine-integrity-flag').textContent).toContain('true')
    expect(screen.getByTestId('refine-last-success').textContent).toContain('hero.title')
    expect(screen.getByTestId('refine-error-code').textContent).toBe('patch_boundary_violation')
  })

  it('AC-33: 本地 network_error 不更新任何成功状态', async () => {
    const fetcher = scriptedFetcher([
      async () => {
        throw new TypeError('Failed to fetch')
      },
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:不该生效')
    await clickSubmit()
    await settle()

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(screen.queryByTestId('refine-integrity')).toBeNull()
    expect(screen.queryByTestId('refine-last-success')).toBeNull()
    expect(screen.getByTestId('refine-error-code').textContent).toBe('network_error')
  })

  it('AC-34: 本地 invalid_json 不更新任何成功状态', async () => {
    const fetcher = scriptedFetcher([
      async () => new Response('<html>not json</html>', { status: 200 }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:不该生效')
    await clickSubmit()
    await settle()

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(screen.queryByTestId('refine-last-success')).toBeNull()
    expect(screen.getByTestId('refine-error-code').textContent).toBe('invalid_json')
  })

  it('AC-35: 本地 invalid_response（2xx + success:false）不更新任何成功状态', async () => {
    const fetcher = scriptedFetcher([async () => jsonResponse(200, failureBody())])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:不该生效')
    await clickSubmit()
    await settle()

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(screen.getByTestId('refine-error-code').textContent).toBe('invalid_response')
  })

  it('AC-35(b): 本地 invalid_response（非 2xx + success:true）不更新任何成功状态', async () => {
    const fetcher = scriptedFetcher([
      async () => jsonResponse(500, successBody('hero.title', '不该生效')),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:不该生效')
    await clickSubmit()
    await settle()

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(screen.getByTestId('refine-error-code').textContent).toBe('invalid_response')
  })

  it('AC-36: 失败时 error 由无到有，成功状态同时保持不变', async () => {
    const fetcher = scriptedFetcher([async () => jsonResponse(422, failureBody())])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:失败请求')
    expect(screen.queryByTestId('refine-error')).toBeNull()

    await clickSubmit()
    await settle()

    expect(isPresent('refine-error')).toBe(true)
    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(isSubmitDisabled()).toBe(false)
  })

  it('AC-37: 失败后 instruction 保留提交前原值', async () => {
    const fetcher = scriptedFetcher([async () => jsonResponse(422, failureBody())])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:请保留我')
    await clickSubmit()
    await settle()

    expect(instructionTextarea().value).toBe('set_text:请保留我')
  })

  it('AC-38: 成功后 instruction 被清空', async () => {
    const fetcher = okFetcher([successBody('hero.title', '清空指令')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '清空指令')

    expect(instructionTextarea().value).toBe('')
  })

  it('AC-39: 前端永不应用 response.patch —— patch 声明的改动不在 document 中时页面不变', async () => {
    // patch 声称改了 hero.subtitle，但响应 document 只改了 hero.title
    const fetcher = okFetcher([
      successBody('hero.title', '仅文档生效', {
        patch: {
          version: '0.1',
          operations: [
            { op: 'update_props', targetNodeId: 'hero.subtitle', props: { text: 'PATCH 不该被应用' } },
          ],
        },
      }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '仅文档生效')

    expect(nodeText(container, 'hero.title')).toBe('仅文档生效')
    expect(nodeText(container, 'hero.subtitle')).toBe(GOLD_SUBTITLE)
    expect(screen.getByTestId('refine-patch-target').textContent).toBe('hero.subtitle')
  })

  it('AC-39(b): 前端源码不含 patch 应用逻辑（无 applyPatch / operations 写入式遍历）', () => {
    const appSource = readSource('src/App.tsx')
    const clientSource = readSource('src/api/refine.ts')
    for (const source of [appSource, clientSource]) {
      expect(source).not.toMatch(/applyPatch/)
      expect(source).not.toMatch(/operations\.(forEach|reduce)/)
    }
    expect(appSource).toMatch(/operations\.map/)
  })

  it('AC-40: 第二轮请求体 document 严格等于第一轮返回的 document', async () => {
    const firstDocument = docWithText([['hero.title', '第一轮标题']])
    const secondDocument = docWithText([
      ['hero.title', '第一轮标题'],
      ['hero.primary-button', '第二轮按钮'],
    ])
    const fetcher = okFetcher([
      successBody('hero.title', '第一轮标题', { document: firstDocument }),
      successBody('hero.primary-button', '第二轮按钮', { document: secondDocument }),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '第一轮标题')
    await runSuccessRound(container, 'hero.primary-button', '第二轮按钮')

    const secondRequest = requestBodyAt(fetcher, 1)
    expect(secondRequest.document).toEqual(firstDocument)
    expect(secondRequest.document).not.toEqual(cloneGold())
    expect(nodeText(container, 'hero.title')).toBe('第一轮标题')
    expect(nodeText(container, 'hero.primary-button')).toBe('第二轮按钮')
  })

  it('AC-41: loading 期间再次点击提交按钮不发起第二个请求', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([() => deferred.promise])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:并发保护')
    await clickSubmit()

    expect(isSubmitDisabled()).toBe(true)
    await clickSubmit()
    await clickSubmit()
    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(1)

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.title', '并发保护')))
    })
    await settle()
    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(1)
  })

  it('AC-42: 成功后 loading 被清除', async () => {
    const fetcher = okFetcher([successBody('hero.title', 'loading 清除')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', 'loading 清除')

    expect(screen.queryByTestId('refine-loading')).toBeNull()
    expect(submitButton().textContent).toBe('提交精修')
  })

  it('AC-42(b): 失败后 loading 被清除', async () => {
    const fetcher = scriptedFetcher([async () => jsonResponse(422, failureBody())])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:失败也要收尾')
    await clickSubmit()
    await settle()

    expect(screen.queryByTestId('refine-loading')).toBeNull()
    expect(isSubmitDisabled()).toBe(false)
  })
})


// --- D. UI 正向路径（AC-43 ~ AC-51）---

describe('D. UI 正向路径', () => {
  it('AC-43: 初始渲染以 Gold Case 为 currentDocument', () => {
    const fetcher = okFetcher([successBody('hero.title', '未使用')])
    const { container } = render(<App fetcher={fetcher} />)

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(nodeText(container, 'hero.subtitle')).toBe(GOLD_SUBTITLE)
    expect(nodeText(container, 'hero.primary-button')).toBe(GOLD_BUTTON)
    expect(nodeText(container, 'menu.card-1.name')).toBe(GOLD_CARD_NAME)
    expect(vi.mocked(fetcher)).not.toHaveBeenCalled()
  })

  it('AC-44: 点击节点后精修面板显示该节点的 ID 与 Type', () => {
    const fetcher = okFetcher([successBody('hero.title', '未使用')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.primary-button')

    expect(screen.getByTestId('panel-node-id').textContent).toBe('hero.primary-button')
    expect(screen.getByTestId('panel-node-type').textContent).toBe('Button')
    expect(screen.getByTestId('panel-node-props').textContent).toContain(GOLD_BUTTON)
  })

  it('AC-45: 输入 instruction 并点击提交后请求发送到 /api/v1/dsl/refine', async () => {
    const fetcher = okFetcher([successBody('hero.title', '发送成功')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '发送成功')

    expect(callAt(fetcher, 0)[0]).toBe('/api/v1/dsl/refine')
    expect(callAt(fetcher, 0)[1]?.method).toBe('POST')
  })

  it('AC-46: 请求进行中提交按钮 disabled 且 loading 指示可见', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([() => deferred.promise])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:进行中')
    await clickSubmit()

    expect(isSubmitDisabled()).toBe(true)
    expect(submitButton().textContent).toBe('精修中...')
    expect(isPresent('refine-loading')).toBe(true)

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.title', '进行中')))
    })
    await settle()
  })

  it('AC-47: 精修成功后页面中目标节点文案变为新值', async () => {
    const fetcher = okFetcher([successBody('hero.title', '全新标题')])
    const { container } = render(<App fetcher={fetcher} />)

    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    await runSuccessRound(container, 'hero.title', '全新标题')

    expect(nodeText(container, 'hero.title')).toBe('全新标题')
  })

  it('AC-48: 精修成功后结果面板显示 Patch 操作内容（op / targetNodeId / props）', async () => {
    const fetcher = okFetcher([successBody('hero.title', 'Patch 展示')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', 'Patch 展示')

    expect(screen.getByTestId('refine-patch-op').textContent).toBe('update_props')
    expect(screen.getByTestId('refine-patch-target').textContent).toBe('hero.title')
    expect(screen.getByTestId('refine-patch-props').textContent).toContain('Patch 展示')
  })

  it('AC-49: 精修成功后结果面板显示 nonTargetNodesUnchanged: true', async () => {
    const fetcher = okFetcher([successBody('hero.title', '完整性展示')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '完整性展示')

    expect(screen.getByTestId('refine-integrity-flag').textContent).toBe(
      'nonTargetNodesUnchanged: true',
    )
  })

  it('AC-50: 精修成功后目标节点保持选中（data-selected 仍在该节点）', async () => {
    const fetcher = okFetcher([successBody('hero.title', '保持选中')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '保持选中')

    const target = container.querySelector('[data-node-id="hero.title"]')
    expect(target?.getAttribute('data-selected')).toBe('true')
    expect(container.querySelectorAll('[data-selected]')).toHaveLength(1)
    expect(screen.getByTestId('panel-node-id').textContent).toBe('hero.title')
  })

  it('AC-51: 精修成功后非目标节点的 DOM 文案未发生变化', async () => {
    const fetcher = okFetcher([successBody('hero.title', '只改我')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '只改我')

    expect(nodeText(container, 'hero.subtitle')).toBe(GOLD_SUBTITLE)
    expect(nodeText(container, 'menu.card-1.name')).toBe(GOLD_CARD_NAME)
    expect(nodeText(container, 'hero.primary-button')).toBe(GOLD_BUTTON)
  })
})

// --- E. UI 失败路径与禁用态（AC-52 ~ AC-59）---

describe('E. UI 失败路径与禁用态', () => {
  it('AC-52: 未选中节点时提交按钮 disabled', () => {
    const fetcher = okFetcher([successBody('hero.title', '未使用')])
    render(<App fetcher={fetcher} />)

    typeInstruction('set_text:有指令但无选中')

    expect(isSubmitDisabled()).toBe(true)
  })

  it('AC-53: instruction 为空时提交按钮 disabled', () => {
    const fetcher = okFetcher([successBody('hero.title', '未使用')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')

    expect(instructionTextarea().value).toBe('')
    expect(isSubmitDisabled()).toBe(true)
  })

  it('AC-53(b): instruction 为纯空白时提交按钮 disabled', () => {
    const fetcher = okFetcher([successBody('hero.title', '未使用')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('   \n  \t ')

    expect(isSubmitDisabled()).toBe(true)
  })

  it('AC-54: instruction 超过 1000 字符时提交按钮 disabled', () => {
    const fetcher = okFetcher([successBody('hero.title', '未使用')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('长'.repeat(1001))

    expect(isSubmitDisabled()).toBe(true)
  })

  it('AC-54(b): instruction 恰好 1000 字符时提交按钮可用（边界内）', () => {
    const fetcher = okFetcher([successBody('hero.title', '未使用')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('长'.repeat(1000))

    expect(isSubmitDisabled()).toBe(false)
  })

  it('AC-55: 失败后画布 DOM 与提交前完全一致', async () => {
    const fetcher = scriptedFetcher([async () => jsonResponse(422, failureBody())])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    const before = container.querySelector('.workbench-canvas')?.innerHTML
    typeInstruction('set_text:注定失败')
    await clickSubmit()
    await settle()

    expect(container.querySelector('.workbench-canvas')?.innerHTML).toBe(before)
  })

  it('AC-56: 失败后错误面板显示净化后的 code / message / issues', async () => {
    const fetcher = scriptedFetcher([async () => jsonResponse(422, failureBody())])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:结构化错误')
    await clickSubmit()
    await settle()

    expect(screen.getByTestId('refine-error-code').textContent).toBe('patch_boundary_violation')
    expect(screen.getByTestId('refine-error-message').textContent).toBe('Patch 触碰了非目标节点')
    const issues = screen.getAllByTestId('refine-error-issue')
    expect(issues).toHaveLength(1)
    const firstIssue = issues[0]
    if (firstIssue === undefined) throw new Error('期望存在一条 issue')
    expect(firstIssue.textContent).toContain('operations[0]')
    expect(firstIssue.textContent).toContain('out_of_scope')
    expect(firstIssue.textContent).toContain('目标越界')
  })

  it('AC-57: 错误响应额外携带 document 时 UI 中不出现任何 document 内容', async () => {
    const leakedDoc = docWithText([['hero.title', '泄露标题不得出现']])
    const fetcher = scriptedFetcher([
      async () =>
        jsonResponse(422, failureBody({ document: leakedDoc, patch: defaultPatch('hero.title', '泄露') })),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:不该泄露')
    await clickSubmit()
    await settle()

    expect(container.textContent).not.toContain('泄露标题不得出现')
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
  })

  it('AC-58: 本地 network_error 在 UI 上有专属提示文案', async () => {
    const fetcher = scriptedFetcher([
      async () => {
        throw new TypeError('Failed to fetch')
      },
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:网络失败')
    await clickSubmit()
    await settle()

    expect(screen.getByTestId('refine-error-code').textContent).toBe('network_error')
    expect(screen.getByTestId('refine-error-message').textContent).toBe(
      LOCAL_ERROR_MESSAGES.network_error,
    )
    expect(screen.getByTestId('refine-error-kind').textContent).toBe('本地错误')
  })

  it('AC-58(b): 本地 invalid_json 在 UI 上有专属提示文案', async () => {
    const fetcher = scriptedFetcher([async () => new Response('oops', { status: 200 })])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:非法 JSON')
    await clickSubmit()
    await settle()

    expect(screen.getByTestId('refine-error-code').textContent).toBe('invalid_json')
    expect(screen.getByTestId('refine-error-message').textContent).toBe(
      LOCAL_ERROR_MESSAGES.invalid_json,
    )
  })

  it('AC-58(c): 本地 invalid_response 在 UI 上有专属提示文案', async () => {
    const fetcher = scriptedFetcher([
      async () => jsonResponse(200, successBody('hero.title', 'x', { patch: 'bad' })),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:非法结构')
    await clickSubmit()
    await settle()

    expect(screen.getByTestId('refine-error-code').textContent).toBe('invalid_response')
    expect(screen.getByTestId('refine-error-message').textContent).toBe(
      LOCAL_ERROR_MESSAGES.invalid_response,
    )
  })

  it('AC-58(d): 服务端错误与本地错误在 UI 上可区分', async () => {
    const fetcher = scriptedFetcher([async () => jsonResponse(422, failureBody())])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:服务端错误')
    await clickSubmit()
    await settle()

    expect(screen.getByTestId('refine-error-kind').textContent).toBe('服务端错误')
  })

  it('AC-59: 成功一轮后切换选中节点，结果面板保留上一轮结果并显示其归属节点', async () => {
    const fetcher = okFetcher([successBody('hero.title', '归属标题')])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '归属标题')
    selectNode(container, 'menu.card-1.name')

    expect(screen.getByTestId('panel-node-id').textContent).toBe('menu.card-1.name')
    expect(screen.getByTestId('refine-patch-target').textContent).toBe('hero.title')
    expect(screen.getByTestId('refine-integrity-node').textContent).toBe(
      '上一轮结果所属节点：hero.title',
    )
    expect(screen.getByTestId('refine-last-success').textContent).toContain('hero.title')
  })
})

// --- F. instruction 控件与键盘交互（AC-60 ~ AC-67）---

describe('F. instruction 控件与键盘交互', () => {
  it('AC-60: instruction 输入控件为 textarea', () => {
    const fetcher = okFetcher([successBody('hero.title', '未使用')])
    render(<App fetcher={fetcher} />)

    expect(screen.getByTestId('refine-instruction').tagName).toBe('TEXTAREA')
  })

  it('AC-61: 单独按 Enter 不触发提交（fetcher 未被调用）', async () => {
    const fetcher = okFetcher([successBody('hero.title', '不该提交')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:换行不提交')
    await act(async () => {
      fireEvent.keyDown(screen.getByTestId('refine-instruction'), { key: 'Enter' })
    })

    expect(vi.mocked(fetcher)).not.toHaveBeenCalled()
    expect(instructionTextarea().value).toBe('set_text:换行不提交')
  })

  it('AC-62: Ctrl+Enter 触发提交', async () => {
    const fetcher = okFetcher([successBody('hero.title', 'Ctrl 提交')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:Ctrl 提交')
    await pressShortcut('ctrlKey')
    await settle()

    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(1)
    expect(nodeText(container, 'hero.title')).toBe('Ctrl 提交')
  })

  it('AC-63: Cmd(Meta)+Enter 触发提交', async () => {
    const fetcher = okFetcher([successBody('hero.title', 'Meta 提交')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:Meta 提交')
    await pressShortcut('metaKey')
    await settle()

    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(1)
    expect(nodeText(container, 'hero.title')).toBe('Meta 提交')
  })

  it('AC-64: loading 期间 Ctrl+Enter 不触发第二次提交', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([() => deferred.promise])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:并发快捷键')
    await clickSubmit()
    await pressShortcut('ctrlKey')
    await pressShortcut('metaKey')

    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(1)

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.title', '并发快捷键')))
    })
    await settle()
    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(1)
  })

  it('AC-65: 未选中节点时 Ctrl+Enter 不触发提交', async () => {
    const fetcher = okFetcher([successBody('hero.title', '不该提交')])
    render(<App fetcher={fetcher} />)

    typeInstruction('set_text:无选中')
    await pressShortcut('ctrlKey')

    expect(vi.mocked(fetcher)).not.toHaveBeenCalled()
  })

  it('AC-66: instruction 为纯空白时 Ctrl+Enter 不触发提交', async () => {
    const fetcher = okFetcher([successBody('hero.title', '不该提交')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('    ')
    await pressShortcut('ctrlKey')

    expect(vi.mocked(fetcher)).not.toHaveBeenCalled()
  })

  it('AC-67: instruction 超过 1000 字符时 Ctrl+Enter 不触发提交', async () => {
    const fetcher = okFetcher([successBody('hero.title', '不该提交')])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('长'.repeat(1001))
    await pressShortcut('ctrlKey')
    await pressShortcut('metaKey')

    expect(vi.mocked(fetcher)).not.toHaveBeenCalled()
  })
})

// --- G. 配置与类型安全（AC-68 ~ AC-71）---

describe('G. 配置与类型安全', () => {
  it('AC-68: vite.config.ts 含 /api → http://127.0.0.1:8000 的 dev proxy', () => {
    const source = readSource('vite.config.ts')
    expect(source).toContain('proxy')
    expect(source).toContain("'/api'")
    expect(source).toContain("target: 'http://127.0.0.1:8000'")
    expect(source).toContain('changeOrigin: true')
  })

  it('AC-69: vite.config.ts 含 port: 5173 与 strictPort: true', () => {
    const source = readSource('vite.config.ts')
    expect(source).toContain('port: 5173')
    expect(source).toContain('strictPort: true')
  })

  it('AC-70: 源码中不存在绕过运行时检查的类型断言', () => {
    for (const path of ['src/api/refine.ts', 'src/api/types.ts', 'src/App.tsx']) {
      const source = readSource(path)
      expect(source).not.toMatch(/as\s+RefineResponse/)
      expect(source).not.toMatch(/as\s+RefineSuccess/)
      expect(source).not.toMatch(/as\s+RefineFailure/)
      expect(source).not.toMatch(/as\s+unknown\s+as/)
    }
  })

  it('AC-71: api/** 与 App 精修状态代码中不出现 any 类型', () => {
    for (const path of ['src/api/refine.ts', 'src/api/types.ts', 'src/App.tsx']) {
      const source = readSource(path)
      expect(source).not.toMatch(/:\s*any\b/)
      expect(source).not.toMatch(/<any>/)
      expect(source).not.toMatch(/as\s+any\b/)
    }
  })

  it('AC-76(静态): playwright.config.ts 用 webServer 数组同时启动 FastAPI 与 Vite', () => {
    const source = readSource('playwright.config.ts')
    expect(source).toContain("testDir: './e2e'")
    expect(source).toContain("baseURL: 'http://127.0.0.1:5173'")
    expect(source).toContain('webServer: [')
    expect(source).toContain('uvicorn genui_api.main:app')
    expect(source).toContain("command: 'npm run dev'")
    expect(source).toContain('reuseExistingServer: !process.env.CI')
  })
})

// --- K. 旧响应竞态（AC-92）---

describe('K. 旧响应竞态', () => {
  it('AC-92: pending 期间切换选中节点，旧响应返回后被丢弃且不覆盖 document 与当前选择', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([() => deferred.promise])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:旧响应内容')
    await clickSubmit()

    // 请求 pending 期间切换选中（选择交互不被禁用）
    selectNode(container, 'menu.card-1.name')
    expect(screen.getByTestId('panel-node-id').textContent).toBe('menu.card-1.name')

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.title', '旧响应内容')))
    })
    await settle()

    // document 未被旧响应覆盖
    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    // 当前选择仍为节点 B
    expect(screen.getByTestId('panel-node-id').textContent).toBe('menu.card-1.name')
    expect(
      container.querySelector('[data-node-id="menu.card-1.name"]')?.getAttribute('data-selected'),
    ).toBe('true')
    // 未触发 REFINE_SUCCESS：结果面板仍为空
    expect(screen.queryByTestId('refine-patch')).toBeNull()
    expect(screen.queryByTestId('refine-integrity')).toBeNull()
    expect(screen.queryByTestId('refine-last-success')).toBeNull()
  })

  it('AC-92(b): 旧响应不得覆盖上一轮成功结果（lastPatch / lastIntegrity / lastSuccess）', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([
      async () => jsonResponse(200, successBody('hero.title', '第一轮标题')),
      () => deferred.promise,
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runSuccessRound(container, 'hero.title', '第一轮标题')

    // 第二轮针对 hero.primary-button，pending 期间切换到别的节点
    selectNode(container, 'hero.primary-button')
    typeInstruction('set_text:第二轮按钮')
    await clickSubmit()
    selectNode(container, 'menu.card-1.name')

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.primary-button', '第二轮按钮')))
    })
    await settle()

    // 上一轮成功结果完整保留
    expect(screen.getByTestId('refine-patch-target').textContent).toBe('hero.title')
    expect(screen.getByTestId('refine-patch-props').textContent).toContain('第一轮标题')
    expect(screen.getByTestId('refine-integrity-node').textContent).toContain('hero.title')
    expect(screen.getByTestId('refine-last-success').textContent).toContain('hero.title')
    // 第二轮的 document 未被提交
    expect(nodeText(container, 'hero.primary-button')).toBe(GOLD_BUTTON)
    expect(nodeText(container, 'hero.title')).toBe('第一轮标题')
  })

  it('AC-92(c): 旧响应被丢弃后 loading 仍被结束（finally 生效），且不产生 error 面板污染成功状态', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([() => deferred.promise])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:旧响应收尾')
    await clickSubmit()
    selectNode(container, 'hero.subtitle')

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.title', '旧响应收尾')))
    })
    await settle()

    expect(screen.queryByTestId('refine-loading')).toBeNull()
    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
    expect(nodeText(container, 'hero.subtitle')).toBe(GOLD_SUBTITLE)
    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(1)
  })

  it('AC-92(d): 竞态期间用户在旧响应到达后可正常发起新一轮请求', async () => {
    const deferred = createDeferred()
    const fetcher = scriptedFetcher([
      () => deferred.promise,
      async () => jsonResponse(200, successBody('menu.card-1.name', '新一轮名称')),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    selectNode(container, 'hero.title')
    typeInstruction('set_text:旧响应内容')
    await clickSubmit()
    selectNode(container, 'menu.card-1.name')

    await act(async () => {
      deferred.resolve(jsonResponse(200, successBody('hero.title', '旧响应内容')))
    })
    await settle()

    typeInstruction('set_text:新一轮名称')
    await clickSubmit()
    await settle()

    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(2)
    expect(nodeText(container, 'menu.card-1.name')).toBe('新一轮名称')
    expect(nodeText(container, 'hero.title')).toBe(GOLD_TITLE)
  })
})
