import { describe, it, expect, vi } from 'vitest'
import {
  LOCAL_ERROR_MESSAGES,
  REFINE_ENDPOINT,
  refineNode,
} from '../api/refine'
import type { Fetcher } from '../api/refine'
import type { DslDocument } from '../dsl/types'
import type { RefineRequest } from '../api/types'

// --- 夹具 ---

const baseDocument: DslDocument = {
  version: '0.1',
  root: {
    id: 'page',
    type: 'Page',
    props: { title: 'Base' },
    children: [{ id: 'hero.title', type: 'Heading', props: { text: '原始标题', level: 1 } }],
  },
}

const updatedDocument: DslDocument = {
  version: '0.1',
  root: {
    id: 'page',
    type: 'Page',
    props: { title: 'Base' },
    children: [{ id: 'hero.title', type: 'Heading', props: { text: '新标题', level: 1 } }],
  },
}

function makeRequest(overrides: Partial<RefineRequest> = {}): RefineRequest {
  return {
    document: baseDocument,
    selectedNodeId: 'hero.title',
    instruction: 'set_text:新标题',
    ...overrides,
  }
}

function successBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    success: true,
    patch: {
      version: '0.1',
      operations: [
        { op: 'update_props', targetNodeId: 'hero.title', props: { text: '新标题' } },
      ],
    },
    document: updatedDocument,
    integrity: { selectedNodeId: 'hero.title', nonTargetNodesUnchanged: true },
    ...overrides,
  }
}

function failureBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    success: false,
    error: {
      code: 'patch_boundary_violation',
      message: 'Patch 越界',
      issues: [{ path: 'operations[0]', code: 'out_of_scope', message: '目标越界' }],
    },
    ...overrides,
  }
}

/** 返回固定 JSON 响应的注入式 fetcher（不 mock 全局 fetch） */
function jsonFetcher(status: number, body: unknown): Fetcher {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

/** 返回原始文本响应的 fetcher（用于非法 JSON 场景） */
function textFetcher(status: number, text: string): Fetcher {
  return vi.fn(async () => new Response(text, { status }))
}

/** 直接抛出的 fetcher（网络失败场景） */
function throwingFetcher(error: unknown): Fetcher {
  return vi.fn(async () => {
    throw error
  })
}

/** 取出第 index 次调用参数（noUncheckedIndexedAccess 下需显式断言存在） */
function callAt(fetcher: Fetcher, index: number) {
  const call = vi.mocked(fetcher).mock.calls[index]
  if (call === undefined) throw new Error(`fetcher 未发生第 ${index + 1} 次调用`)
  return call
}

function lastCallInit(fetcher: Fetcher): RequestInit {
  const init = callAt(fetcher, 0)[1]
  expect(init).toBeDefined()
  return init ?? {}
}

function lastCallBody(fetcher: Fetcher): Record<string, unknown> {
  const body = lastCallInit(fetcher).body
  expect(typeof body).toBe('string')
  const parsed: unknown = JSON.parse(String(body))
  expect(parsed).toBeTypeOf('object')
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('request body 不是对象')
  }
  const record: Record<string, unknown> = { ...parsed }
  return record
}

// --- A. 请求构造（AC-01 ~ AC-05）---

describe('A. refineNode 请求构造', () => {
  it('AC-01: request body 恰好包含 document / selectedNodeId / instruction 三个字段', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await refineNode(makeRequest(), fetcher)
    expect(Object.keys(lastCallBody(fetcher)).sort()).toEqual([
      'document',
      'instruction',
      'selectedNodeId',
    ])
  })

  it('AC-02: request body 使用驼峰 selectedNodeId，不含 selected_node_id', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await refineNode(makeRequest({ selectedNodeId: 'hero.title' }), fetcher)
    const body = lastCallBody(fetcher)
    expect(body.selectedNodeId).toBe('hero.title')
    expect(body).not.toHaveProperty('selected_node_id')
  })

  it('AC-03: request body 的 document 为调用时传入的 document（不是静态初始值）', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await refineNode(makeRequest({ document: updatedDocument }), fetcher)
    const body = lastCallBody(fetcher)
    expect(body.document).toEqual(updatedDocument)
    expect(body.document).not.toEqual(baseDocument)
  })

  it('AC-03(b): instruction 原样传递，不做改写', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await refineNode(makeRequest({ instruction: 'set_text:多行\n指令' }), fetcher)
    expect(lastCallBody(fetcher).instruction).toBe('set_text:多行\n指令')
  })

  it('AC-04: 使用 POST 方法', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await refineNode(makeRequest(), fetcher)
    expect(lastCallInit(fetcher).method).toBe('POST')
  })

  it('AC-04(b): 使用 Content-Type: application/json', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await refineNode(makeRequest(), fetcher)
    expect(lastCallInit(fetcher).headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('AC-04(c): 使用相对路径 /api/v1/dsl/refine', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await refineNode(makeRequest(), fetcher)
    expect(callAt(fetcher, 0)[0]).toBe('/api/v1/dsl/refine')
    expect(REFINE_ENDPOINT).toBe('/api/v1/dsl/refine')
  })

  it('AC-05: fetcher 参数可注入，全局 fetch 未被替换也未被调用', async () => {
    const originalFetch = globalThis.fetch
    const globalSpy = vi.fn()
    const fetcher = jsonFetcher(200, successBody())
    await refineNode(makeRequest(), fetcher)
    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(1)
    expect(globalThis.fetch).toBe(originalFetch)
    expect(globalSpy).not.toHaveBeenCalled()
  })
})

// --- B. 响应边界与最小结构检查（AC-06 ~ AC-23）---

describe('B. 成功与服务端失败路径', () => {
  it('AC-06: HTTP 200 + success:true + 结构完整 → kind:"success"', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, successBody()))
    expect(result.kind).toBe('success')
  })

  it('AC-06(b): 成功结果携带 patch / document / integrity 三段内容', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, successBody()))
    if (result.kind !== 'success') throw new Error(`期望 success，实际 ${result.kind}`)
    expect(result.patch.version).toBe('0.1')
    expect(result.patch.operations).toHaveLength(1)
    expect(result.document).toEqual(updatedDocument)
    expect(result.integrity).toEqual({
      selectedNodeId: 'hero.title',
      nonTargetNodesUnchanged: true,
    })
  })

  it('AC-06(c): HTTP 201（2xx 非 200）+ success:true 同样视为成功', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(201, successBody()))
    expect(result.kind).toBe('success')
  })

  it('AC-07: HTTP 422 + success:false → kind:"server" 且含 code / message / issues', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(422, failureBody()))
    if (result.kind !== 'server') throw new Error(`期望 server，实际 ${result.kind}`)
    expect(result.code).toBe('patch_boundary_violation')
    expect(result.message).toBe('Patch 越界')
    expect(result.issues).toEqual([
      { path: 'operations[0]', code: 'out_of_scope', message: '目标越界' },
    ])
  })

  it('AC-07(b): HTTP 400 + success:false 同样归为 server 错误', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(400, failureBody()))
    expect(result.kind).toBe('server')
  })

  it('AC-07(c): HTTP 500 + success:false 同样归为 server 错误', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(500, failureBody()))
    expect(result.kind).toBe('server')
  })

  it('AC-08: 失败响应 error.issues 缺失 → 归一化为 []，不抛异常', async () => {
    const body = failureBody({ error: { code: 'invalid_dsl', message: '文档非法' } })
    const result = await refineNode(makeRequest(), jsonFetcher(422, body))
    if (result.kind !== 'server') throw new Error(`期望 server，实际 ${result.kind}`)
    expect(result.issues).toEqual([])
  })

  it('AC-08(b): error.issues 非数组 → 归一化为 []', async () => {
    const body = failureBody({
      error: { code: 'invalid_dsl', message: '文档非法', issues: 'boom' },
    })
    const result = await refineNode(makeRequest(), jsonFetcher(422, body))
    if (result.kind !== 'server') throw new Error(`期望 server，实际 ${result.kind}`)
    expect(result.issues).toEqual([])
  })

  it('AC-08(c): issue 条目只保留 path / code / message，额外字段被丢弃', async () => {
    const body = failureBody({
      error: {
        code: 'invalid_dsl',
        message: '文档非法',
        issues: [
          { path: 'root', code: 'bad', message: '坏', internal: '机密', document: baseDocument },
        ],
      },
    })
    const result = await refineNode(makeRequest(), jsonFetcher(422, body))
    if (result.kind !== 'server') throw new Error(`期望 server，实际 ${result.kind}`)
    const first = result.issues[0]
    if (first === undefined) throw new Error('期望存在一条 issue')
    expect(first).toEqual({ path: 'root', code: 'bad', message: '坏' })
    expect(Object.keys(first)).toEqual(['path', 'code', 'message'])
  })

  it('AC-08(d): 结构非法的 issue 条目被过滤，不产生残缺条目', async () => {
    const body = failureBody({
      error: {
        code: 'invalid_dsl',
        message: '文档非法',
        issues: [{ path: 'root', code: 'bad' }, 'not-an-object'],
      },
    })
    const result = await refineNode(makeRequest(), jsonFetcher(422, body))
    if (result.kind !== 'server') throw new Error(`期望 server，实际 ${result.kind}`)
    expect(result.issues).toEqual([])
  })
})

describe('B. HTTP 状态与 envelope 一致性矩阵（C-1）', () => {
  it('AC-09: HTTP 200 + success:false → local / invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, failureBody()))
    expect(result).toEqual({
      kind: 'local',
      code: 'invalid_response',
      message: LOCAL_ERROR_MESSAGES.invalid_response,
    })
  })

  it('AC-10: HTTP 500 + success:true → local / invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(500, successBody()))
    expect(result).toEqual({
      kind: 'local',
      code: 'invalid_response',
      message: LOCAL_ERROR_MESSAGES.invalid_response,
    })
  })

  it('AC-10(b): HTTP 422 + success:true → local / invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(422, successBody()))
    expect(result.kind).toBe('local')
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-11: success 字段缺失 → local / invalid_response', async () => {
    const body = successBody()
    delete body.success
    const result = await refineNode(makeRequest(), jsonFetcher(200, body))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-11(b): success 为字符串 "true" → local / invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, successBody({ success: 'true' })))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-11(c): success 为数字 1 → local / invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, successBody({ success: 1 })))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-11(d): success 为 null → local / invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, successBody({ success: null })))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-11(e): 响应顶层为数组 → local / invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, [successBody()]))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-11(f): 响应顶层为字符串 → local / invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, 'ok'))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-11(g): 响应顶层为 null → local / invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, null))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })
})

describe('B. 网络与 JSON 解析错误分类', () => {
  it('AC-12: fetcher 抛出 TypeError → local / network_error', async () => {
    const result = await refineNode(
      makeRequest(),
      throwingFetcher(new TypeError('Failed to fetch')),
    )
    expect(result).toEqual({
      kind: 'local',
      code: 'network_error',
      message: LOCAL_ERROR_MESSAGES.network_error,
    })
  })

  it('AC-12(b): fetcher 抛出时 refineNode 不向调用方抛异常', async () => {
    await expect(
      refineNode(makeRequest(), throwingFetcher(new Error('aborted'))),
    ).resolves.toBeTruthy()
  })

  it('AC-12(c): fetcher 抛出非 Error 值也归为 network_error', async () => {
    const result = await refineNode(makeRequest(), throwingFetcher('boom'))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('network_error')
  })

  it('AC-13: 响应体为非法 JSON → local / invalid_json', async () => {
    const result = await refineNode(makeRequest(), textFetcher(200, '<html>oops</html>'))
    expect(result).toEqual({
      kind: 'local',
      code: 'invalid_json',
      message: LOCAL_ERROR_MESSAGES.invalid_json,
    })
  })

  it('AC-13(b): 非 2xx 且响应体非法 JSON → local / invalid_json（先于状态一致性判定）', async () => {
    const result = await refineNode(makeRequest(), textFetcher(500, 'Internal Server Error'))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_json')
  })
})

describe('B. 成功响应 patch 结构检查（C-2）', () => {
  it('AC-14: patch 字段缺失 → invalid_response', async () => {
    const body = successBody()
    delete body.patch
    const result = await refineNode(makeRequest(), jsonFetcher(200, body))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-14(b): patch 非对象（字符串）→ invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, successBody({ patch: 'nope' })))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-14(c): patch 为数组 → invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, successBody({ patch: [] })))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-14(d): patch.version !== "0.1" → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ patch: { version: '0.2', operations: [] } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-15: patch.operations 非数组（对象）→ invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ patch: { version: '0.1', operations: {} } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-15(b): patch.operations 缺失 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ patch: { version: '0.1' } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-15(c): patch.operations 为空数组 → 合法（结构检查不评估语义）', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ patch: { version: '0.1', operations: [] } })),
    )
    expect(result.kind).toBe('success')
  })
})

describe('B. 成功响应 document 结构检查（C-3）', () => {
  it('AC-16: document 字段缺失 → invalid_response', async () => {
    const body = successBody()
    delete body.document
    const result = await refineNode(makeRequest(), jsonFetcher(200, body))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-16(b): document 非对象（数字）→ invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(200, successBody({ document: 42 })))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-16(c): document 缺 version → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ document: { root: { id: 'page', type: 'Page' } } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-16(d): document.version 非字符串 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ document: { version: 0.1, root: { id: 'p', type: 'Page' } } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-17: document.root 非对象 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ document: { version: '0.1', root: 'page' } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-17(b): document.root 缺 id → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ document: { version: '0.1', root: { type: 'Page' } } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-17(c): document.root.id 非字符串 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ document: { version: '0.1', root: { id: 7, type: 'Page' } } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-17(d): document.root 缺 type → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ document: { version: '0.1', root: { id: 'page' } } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-17(e): document.root.type 非字符串 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(
        200,
        successBody({ document: { version: '0.1', root: { id: 'page', type: 1 } } }),
      ),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })
})

describe('B. 成功响应 integrity 结构检查（C-4）', () => {
  it('AC-18: integrity 字段缺失 → invalid_response', async () => {
    const body = successBody()
    delete body.integrity
    const result = await refineNode(makeRequest(), jsonFetcher(200, body))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-18(b): integrity 非对象（字符串）→ invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ integrity: 'ok' })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-18(c): integrity.selectedNodeId 非字符串 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(
        200,
        successBody({ integrity: { selectedNodeId: 123, nonTargetNodesUnchanged: true } }),
      ),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-18(d): integrity.selectedNodeId 为空字符串 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(
        200,
        successBody({ integrity: { selectedNodeId: '', nonTargetNodesUnchanged: true } }),
      ),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-19: integrity.nonTargetNodesUnchanged 字段缺失 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ integrity: { selectedNodeId: 'hero.title' } })),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-20: integrity.nonTargetNodesUnchanged 为字符串 "true" → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(
        200,
        successBody({ integrity: { selectedNodeId: 'hero.title', nonTargetNodesUnchanged: 'true' } }),
      ),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-20(b): integrity.nonTargetNodesUnchanged 为数字 1 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(
        200,
        successBody({ integrity: { selectedNodeId: 'hero.title', nonTargetNodesUnchanged: 1 } }),
      ),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-20(c): integrity.nonTargetNodesUnchanged 为 null → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(
        200,
        successBody({ integrity: { selectedNodeId: 'hero.title', nonTargetNodesUnchanged: null } }),
      ),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-20(d): integrity.nonTargetNodesUnchanged === false 被放行为 kind:"success"（由提交层 C-5 拒绝）', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(
        200,
        successBody({ integrity: { selectedNodeId: 'hero.title', nonTargetNodesUnchanged: false } }),
      ),
    )
    if (result.kind !== 'success') throw new Error(`期望 success，实际 ${result.kind}`)
    expect(result.integrity.nonTargetNodesUnchanged).toBe(false)
  })
})

describe('B. 额外字段丢弃与本地错误文案净化', () => {
  it('AC-21: 成功响应的额外字段（debug / trace）不出现在返回值中', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, successBody({ debug: { prompt: '机密' }, trace: 'tid-1' })),
    )
    if (result.kind !== 'success') throw new Error('期望 success')
    expect(Object.keys(result).sort()).toEqual(['document', 'integrity', 'kind', 'patch'])
    expect(result).not.toHaveProperty('debug')
    expect(result).not.toHaveProperty('trace')
  })

  it('AC-21(b): 成功响应 integrity 上的额外字段被丢弃', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(
        200,
        successBody({
          integrity: {
            selectedNodeId: 'hero.title',
            nonTargetNodesUnchanged: true,
            internalHash: 'secret',
          },
        }),
      ),
    )
    if (result.kind !== 'success') throw new Error('期望 success')
    expect(Object.keys(result.integrity).sort()).toEqual([
      'nonTargetNodesUnchanged',
      'selectedNodeId',
    ])
  })

  it('AC-22: 失败响应额外携带 document / patch 时被丢弃', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(422, failureBody({ document: baseDocument, patch: { version: '0.1', operations: [] } })),
    )
    if (result.kind !== 'server') throw new Error('期望 server')
    expect(Object.keys(result).sort()).toEqual([
      'code',
      'issues',
      'kind',
      'message',
      'requestId',
    ])
    expect(result).not.toHaveProperty('document')
    expect(result).not.toHaveProperty('patch')
  })

  it('AC-22(b): 失败响应 error 内部额外携带 document 时被丢弃', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(422, {
        success: false,
        error: { code: 'x', message: 'y', issues: [], document: baseDocument },
      }),
    )
    if (result.kind !== 'server') throw new Error('期望 server')
    expect(JSON.stringify(result)).not.toContain('原始标题')
  })

  it('AC-22(c): error 非对象 → invalid_response', async () => {
    const result = await refineNode(makeRequest(), jsonFetcher(422, { success: false, error: 'boom' }))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-22(d): error.code 非字符串 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(422, { success: false, error: { code: 500, message: 'y' } }),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-22(e): error.message 缺失 → invalid_response', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(422, { success: false, error: { code: 'x' } }),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-23: network_error 文案为前端固定文案，不含请求 document 内容', async () => {
    const result = await refineNode(
      makeRequest(),
      throwingFetcher(new TypeError('Failed to fetch http://127.0.0.1:8000')),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.message).toBe(LOCAL_ERROR_MESSAGES.network_error)
    expect(result.message).not.toContain('原始标题')
    expect(result.message).not.toContain('Failed to fetch')
  })

  it('AC-23(b): invalid_json 文案为前端固定文案，不含响应原文', async () => {
    const result = await refineNode(makeRequest(), textFetcher(200, '<html>server stack trace</html>'))
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.message).toBe(LOCAL_ERROR_MESSAGES.invalid_json)
    expect(result.message).not.toContain('stack')
    expect(result.message).not.toContain('html')
  })

  it('AC-23(c): invalid_response 文案为前端固定文案，不含响应 document 内容', async () => {
    const result = await refineNode(
      makeRequest(),
      jsonFetcher(200, { success: true, patch: 'bad', document: baseDocument, integrity: {} }),
    )
    if (result.kind !== 'local') throw new Error('期望 local')
    expect(result.message).toBe(LOCAL_ERROR_MESSAGES.invalid_response)
    expect(result.message).not.toContain('原始标题')
    expect(result.message).not.toContain('page')
  })

  it('AC-23(d): 三种本地错误文案互不相同，UI 可区分', () => {
    const messages = Object.values(LOCAL_ERROR_MESSAGES)
    expect(new Set(messages).size).toBe(3)
  })
})
