// frontend/src/test/malformed-patch.test.tsx
// 畸形 Patch 响应回归：success 响应中的 operations 逐条结构非法时，
// 必须在 API Client 层被 `isPatchDocumentShape` 拒为 invalid_response，
// 从而不会流入 `derivePatchProps()` 的结构化读取（operation.targetNodeId / operation.props）。

import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import App from '../App'
import { LOCAL_ERROR_MESSAGES, isPatchDocumentShape, refineNode } from '../api/refine'
import type { Fetcher } from '../api/refine'
import type { DslDocument } from '../dsl/types'
import type { RefineRequest } from '../api/types'
import goldCaseRaw from '../../../examples/dsl/coffee-shop-landing.json'

// --- 畸形 operations 用例表（每条都能通过旧守卫「operations 是数组」）---

interface MalformedCase {
  name: string
  operations: unknown[]
}

const MALFORMED_CASES: MalformedCase[] = [
  { name: 'operations: [null]', operations: [null] },
  { name: 'operations: [{}]', operations: [{}] },
  {
    name: 'operations: [{op:"invalid_op", targetNodeId:"hero.title", props:{}}]（非法 op）',
    operations: [{ op: 'invalid_op', targetNodeId: 'hero.title', props: {} }],
  },
  {
    name: 'operations: [{op:"update_props", props:{}}]（缺 targetNodeId）',
    operations: [{ op: 'update_props', props: {} }],
  },
  {
    name: 'operations: [{op:"update_props", targetNodeId:"hero.title"}]（缺 props）',
    operations: [{ op: 'update_props', targetNodeId: 'hero.title' }],
  },
  {
    name: 'operations: [{op:"update_props", targetNodeId:"hero.title", props:null}]',
    operations: [{ op: 'update_props', targetNodeId: 'hero.title', props: null }],
  },
]

// --- JSON 文档工具（只读夹具，深拷贝后使用）---

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

function docWithText(nodeId: string, text: string): JsonDoc {
  const base = cloneGold()
  const node = findJsonNode(base.root, nodeId)
  if (node === null) throw new Error(`夹具构造失败：找不到节点 ${nodeId}`)
  node.props = { ...(node.props ?? {}), text }
  return base
}

function successBody(
  nodeId: string,
  text: string,
  patchOverride?: unknown,
): Record<string, unknown> {
  return {
    success: true,
    patch:
      patchOverride === undefined
        ? {
            version: '0.1',
            operations: [{ op: 'update_props', targetNodeId: nodeId, props: { text } }],
          }
        : patchOverride,
    document: docWithText(nodeId, text),
    integrity: { selectedNodeId: nodeId, nonTargetNodesUnchanged: true },
  }
}

// --- fetcher 注入工具（不 mock 全局 fetch）---

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function okFetcher(bodies: Array<Record<string, unknown>>): Fetcher {
  let index = 0
  return vi.fn(async () => {
    const body = bodies[Math.min(index, bodies.length - 1)]
    if (body === undefined) throw new Error('okFetcher 未配置任何响应')
    index += 1
    return jsonResponse(200, body)
  })
}

// --- API Client 直调夹具 ---

const clientDocument: DslDocument = {
  version: '0.1',
  root: {
    id: 'page',
    type: 'Page',
    props: { title: 'Base' },
    children: [{ id: 'hero.title', type: 'Heading', props: { text: '原始标题', level: 1 } }],
  },
}

function clientRequest(): RefineRequest {
  return {
    document: clientDocument,
    selectedNodeId: 'hero.title',
    instruction: 'set_text:新标题',
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

// --- 未捕获异常探针：React 会把事件处理器内的异常打到 console.error ---

let consoleErrorSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

afterEach(() => {
  consoleErrorSpy.mockRestore()
})

// ============================================================
// A. 守卫层：逐条 operation 结构校验
// ============================================================

describe('A. isPatchDocumentShape 逐条 operation 校验', () => {
  it('合法 patch 通过（含空 operations 数组）', () => {
    expect(isPatchDocumentShape({ version: '0.1', operations: [] })).toBe(true)
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [{ op: 'update_props', targetNodeId: 'hero.title', props: { text: 'x' } }],
      }),
    ).toBe(true)
  })

  for (const malformed of MALFORMED_CASES) {
    it(`拒绝 ${malformed.name}`, () => {
      expect(isPatchDocumentShape({ version: '0.1', operations: malformed.operations })).toBe(
        false,
      )
    })
  }

  it('数组中任意一条非法即整体拒绝（首条合法、次条畸形）', () => {
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [
          { op: 'update_props', targetNodeId: 'hero.title', props: { text: 'x' } },
          null,
        ],
      }),
    ).toBe(false)
  })

  it('targetNodeId 为空字符串 / props 为数组均被拒绝', () => {
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [{ op: 'update_props', targetNodeId: '', props: {} }],
      }),
    ).toBe(false)
    expect(
      isPatchDocumentShape({
        version: '0.1',
        operations: [{ op: 'update_props', targetNodeId: 'x', props: [] }],
      }),
    ).toBe(false)
  })
})

// ============================================================
// B. API Client：畸形 operations → invalid_response，且不抛异常
// ============================================================

describe('B. refineNode 对畸形 operations 的处理', () => {
  for (const malformed of MALFORMED_CASES) {
    it(`${malformed.name} → invalid_response（Promise 正常 resolve，不抛异常）`, async () => {
      const body = successBody('hero.title', '新标题', {
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

// ============================================================
// C. 应用层：文档与 conversationHistory 零变更、无未捕获异常
// ============================================================

describe('C. 畸形 Patch 响应不污染任何状态', () => {
  for (const malformed of MALFORMED_CASES) {
    it(`${malformed.name}：document 不变、history 不变、无未捕获异常`, async () => {
      const fetcher = okFetcher([
        successBody('hero.title', '第一版'),
        successBody('hero.title', '第二版', {
          version: '0.1',
          operations: malformed.operations,
        }),
      ])
      const { container } = render(<App fetcher={fetcher} />)

      // 第一轮成功：建立可观察的文档状态与 1 条已确认轮次
      await runRound(container, 'hero.title', '改成第一版')
      expect(nodeText(container, 'hero.title')).toBe('第一版')
      const historyBefore = historyItems()
      expect(historyBefore).toHaveLength(1)

      // 第二轮响应携带畸形 operations
      await runRound(container, 'hero.title', '改成第二版')

      expect(screen.getByTestId('refine-error-code').textContent).toBe('invalid_response')
      expect(screen.getByTestId('refine-error-message').textContent).toBe(
        LOCAL_ERROR_MESSAGES.invalid_response,
      )
      // document 未变：仍是第一轮结果
      expect(nodeText(container, 'hero.title')).toBe('第一版')
      // conversationHistory 未变：条数与内容逐条相同
      expect(historyItems()).toEqual(historyBefore)
      // 无未捕获异常（React 会把事件处理器内的异常打到 console.error）
      expect(consoleErrorSpy).not.toHaveBeenCalled()
    })
  }

  it('畸形轮之后仍可继续正常精修（状态未被破坏）', async () => {
    const fetcher = okFetcher([
      successBody('hero.title', '第一版'),
      successBody('hero.title', '第二版', { version: '0.1', operations: [null] }),
      successBody('hero.title', '第三版'),
    ])
    const { container } = render(<App fetcher={fetcher} />)

    await runRound(container, 'hero.title', '改成第一版')
    await runRound(container, 'hero.title', '改成第二版')
    await runRound(container, 'hero.title', '改成第三版')

    expect(nodeText(container, 'hero.title')).toBe('第三版')
    expect(historyItems()).toHaveLength(2)
    expect(screen.queryByTestId('refine-error-code')).toBeNull()
    expect(consoleErrorSpy).not.toHaveBeenCalled()
  })
})
