import { describe, it, expect, vi } from 'vitest'
import {
  GENERATE_ENDPOINT,
  GENERATE_LOCAL_ERROR_MESSAGES,
  GENERATE_SERVER_FALLBACK_MESSAGE,
  generateDraft,
} from '../api/generate'
import type { Fetcher } from '../api/refine'
import type { DslDocument } from '../dsl/types'

// --- 夹具 ---

const draftDocument: DslDocument = {
  version: '0.1',
  root: {
    id: 'page',
    type: 'Page',
    props: { title: '晨光咖啡工坊' },
    children: [
      { id: 'hero.title', type: 'Heading', props: { text: '晨光咖啡工坊', level: 1 } },
      { id: 'hero.subtitle', type: 'Text', props: { text: '慢烘豆香' } },
    ],
  },
}

function successBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { success: true, document: draftDocument, ...overrides }
}

function failureBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    success: false,
    error: {
      code: 'unrecognized_intent',
      message: '无法识别需求意图',
      issues: [{ path: 'prompt', code: 'unrecognized_intent', message: '无匹配意图' }],
    },
    ...overrides,
  }
}

function jsonFetcher(status: number, body: unknown): Fetcher {
  return vi.fn(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
  )
}

function textFetcher(status: number, text: string): Fetcher {
  return vi.fn(async () => new Response(text, { status }))
}

function throwingFetcher(error: unknown): Fetcher {
  return vi.fn(async () => {
    throw error
  })
}

function callAt(fetcher: Fetcher, index: number) {
  const call = vi.mocked(fetcher).mock.calls[index]
  if (call === undefined) throw new Error(`fetcher 未发生第 ${index + 1} 次调用`)
  return call
}

function firstCallInit(fetcher: Fetcher): RequestInit {
  const init = callAt(fetcher, 0)[1]
  expect(init).toBeDefined()
  return init ?? {}
}

function firstCallBody(fetcher: Fetcher): Record<string, unknown> {
  const body = firstCallInit(fetcher).body
  expect(typeof body).toBe('string')
  const parsed: unknown = JSON.parse(String(body))
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('request body 不是对象')
  }
  return { ...parsed }
}

// --- A. 请求构造（AC-43）---

describe('A. generateDraft 请求构造', () => {
  it('AC-43: 请求方法为 POST，端点为 /api/v1/dsl/generate', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await generateDraft({ prompt: '咖啡店落地页' }, fetcher)

    expect(callAt(fetcher, 0)[0]).toBe('/api/v1/dsl/generate')
    expect(GENERATE_ENDPOINT).toBe('/api/v1/dsl/generate')
    expect(firstCallInit(fetcher).method).toBe('POST')
  })

  it('AC-43: request body 恰好只含 prompt 一个字段', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await generateDraft({ prompt: '咖啡店落地页' }, fetcher)

    const body = firstCallBody(fetcher)
    expect(Object.keys(body)).toEqual(['prompt'])
    expect(body.prompt).toBe('咖啡店落地页')
  })

  it('AC-43: Content-Type 头为 application/json', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await generateDraft({ prompt: '咖啡' }, fetcher)

    expect(firstCallInit(fetcher).headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('AC-43: 只发起一次请求', async () => {
    const fetcher = jsonFetcher(200, successBody())
    await generateDraft({ prompt: '咖啡' }, fetcher)

    expect(vi.mocked(fetcher)).toHaveBeenCalledTimes(1)
  })
})

// --- B. G-1 网络失败（AC-44）---

describe('B. G-1 网络失败', () => {
  it('AC-44: fetcher 抛出 TypeError → network_error', async () => {
    const result = await generateDraft(
      { prompt: '咖啡' },
      throwingFetcher(new TypeError('Failed to fetch')),
    )

    expect(result.kind).toBe('local')
    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('network_error')
    expect(result.message).toBe(GENERATE_LOCAL_ERROR_MESSAGES.network_error)
  })

  it('AC-44: fetcher 抛出非 Error 值也不向上抛异常', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, throwingFetcher('boom'))

    expect(result.kind).toBe('local')
    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('network_error')
  })

  it('AC-44: 本地错误文案不含服务端原文或异常原文', async () => {
    const result = await generateDraft(
      { prompt: '咖啡' },
      throwingFetcher(new Error('SECRET_TRACE at /tmp/x.py')),
    )

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.message).not.toContain('SECRET_TRACE')
    expect(result.message).not.toContain('/tmp/x.py')
  })
})

// --- C. G-2 JSON 解析失败（AC-45）---

describe('C. G-2 JSON 解析失败', () => {
  it('AC-45: 200 + 非 JSON 文本 → invalid_json', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, textFetcher(200, '<html>oops'))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_json')
    expect(result.message).toBe(GENERATE_LOCAL_ERROR_MESSAGES.invalid_json)
  })

  it('AC-45: 502 + 非 JSON 文本 → invalid_json', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, textFetcher(502, 'Bad Gateway'))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_json')
  })

  it('AC-45: 空响应体 → invalid_json', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, textFetcher(200, ''))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_json')
  })
})

// --- D. G-3 响应体结构（AC-46）---

describe('D. G-3 响应体结构', () => {
  it('AC-46: 响应体为数组 → invalid_response', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, jsonFetcher(200, [1, 2, 3]))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
    expect(result.message).toBe(GENERATE_LOCAL_ERROR_MESSAGES.invalid_response)
  })

  it('AC-46: 响应体为 null → invalid_response', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, jsonFetcher(200, null))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-46: success 为字符串 "true" → invalid_response', async () => {
    const result = await generateDraft(
      { prompt: '咖啡' },
      jsonFetcher(200, { success: 'true', document: draftDocument }),
    )

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-46: success 字段缺失 → invalid_response', async () => {
    const result = await generateDraft(
      { prompt: '咖啡' },
      jsonFetcher(200, { document: draftDocument }),
    )

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })
})

// --- E. G-4 HTTP 状态与 envelope 一致性（AC-47）---

describe('E. G-4 HTTP 状态与 envelope 一致性', () => {
  it('AC-47: 200 + success:false → invalid_response', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, jsonFetcher(200, failureBody()))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-47: 422 + success:true → invalid_response', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, jsonFetcher(422, successBody()))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-47: 502 + success:true → invalid_response', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, jsonFetcher(502, successBody()))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-47: 204 状态被视为 2xx 成功侧（success:false 时不一致）', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, jsonFetcher(299, failureBody()))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })
})

// --- F. G-5 document 结构检查（AC-48）---

describe('F. G-5 document 结构检查', () => {
  it('AC-48: document 缺失 → invalid_response', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, jsonFetcher(200, { success: true }))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-48: document 为字符串 → invalid_response', async () => {
    const result = await generateDraft(
      { prompt: '咖啡' },
      jsonFetcher(200, { success: true, document: 'not-a-document' }),
    )

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-48: document 缺 version → invalid_response', async () => {
    const result = await generateDraft(
      { prompt: '咖啡' },
      jsonFetcher(200, { success: true, document: { root: draftDocument.root } }),
    )

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-48: document.root 缺 id / type → invalid_response', async () => {
    const result = await generateDraft(
      { prompt: '咖啡' },
      jsonFetcher(200, { success: true, document: { version: '0.1', root: { props: {} } } }),
    )

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-48: document.root 为数组 → invalid_response', async () => {
    const result = await generateDraft(
      { prompt: '咖啡' },
      jsonFetcher(200, { success: true, document: { version: '0.1', root: [] } }),
    )

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })
})

// --- G. G-6 成功路径与额外字段丢弃（AC-49）---

describe('G. G-6 成功路径', () => {
  it('AC-49: 200 + 合法 document → success 且 document 逐字段相等', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, jsonFetcher(200, successBody()))

    expect(result.kind).toBe('success')
    if (result.kind !== 'success') throw new Error('应为 success')
    expect(result.document).toEqual(draftDocument)
  })

  it('AC-49: 成功结果只含 kind / document 两个键', async () => {
    const result = await generateDraft({ prompt: '咖啡' }, jsonFetcher(200, successBody()))

    expect(Object.keys(result).sort()).toEqual(['document', 'kind'])
  })

  it('AC-49: 响应额外字段（debug / patch / integrity / trace）不出现在返回值中', async () => {
    const fetcher = jsonFetcher(
      200,
      successBody({
        debug: 'internal',
        patch: { version: '0.1', operations: [] },
        integrity: { selectedNodeId: 'x', nonTargetNodesUnchanged: true },
        trace: ['a', 'b'],
      }),
    )
    const result = await generateDraft({ prompt: '咖啡' }, fetcher)

    if (result.kind !== 'success') throw new Error('应为 success')
    const record: Record<string, unknown> = { ...result }
    expect(record.debug).toBeUndefined()
    expect(record.patch).toBeUndefined()
    expect(record.integrity).toBeUndefined()
    expect(record.trace).toBeUndefined()
  })
})

// --- H. G-7 失败净化（AC-50）---

describe('H. G-7 失败响应净化', () => {
  it('AC-50: 422 + 完整 error → server 错误并保留 code / message / issues', async () => {
    const result = await generateDraft({ prompt: 'xyz' }, jsonFetcher(422, failureBody()))

    expect(result.kind).toBe('server')
    if (result.kind !== 'server') throw new Error('应为 server')
    expect(result.code).toBe('unrecognized_intent')
    expect(result.message).toBe('无法识别需求意图')
    expect(result.issues).toEqual([
      { path: 'prompt', code: 'unrecognized_intent', message: '无匹配意图' },
    ])
  })

  it('AC-50: issues 缺失 → []', async () => {
    const result = await generateDraft(
      { prompt: 'xyz' },
      jsonFetcher(502, { success: false, error: { code: 'provider_error', message: '上游失败' } }),
    )

    if (result.kind !== 'server') throw new Error('应为 server')
    expect(result.issues).toEqual([])
  })

  it('AC-50: issues 非数组 → []', async () => {
    const result = await generateDraft(
      { prompt: 'xyz' },
      jsonFetcher(502, {
        success: false,
        error: { code: 'provider_error', message: '上游失败', issues: 'oops' },
      }),
    )

    if (result.kind !== 'server') throw new Error('应为 server')
    expect(result.issues).toEqual([])
  })

  it('AC-50: issues 中非法条目被丢弃，合法条目只保留三个字段', async () => {
    const result = await generateDraft(
      { prompt: 'xyz' },
      jsonFetcher(502, {
        success: false,
        error: {
          code: 'invalid_generated_document',
          message: '候选非法',
          issues: [
            { path: 'root', code: 'duplicate_id', message: '重复', extra: 'drop-me' },
            { path: 'root', code: 42, message: '类型错' },
            'not-an-object',
            null,
          ],
        },
      }),
    )

    if (result.kind !== 'server') throw new Error('应为 server')
    expect(result.issues).toEqual([{ path: 'root', code: 'duplicate_id', message: '重复' }])
  })

  it('AC-50: error.code 非字符串 → 降级为本地 invalid_response', async () => {
    const result = await generateDraft(
      { prompt: 'xyz' },
      jsonFetcher(422, { success: false, error: { code: 500, message: 'x' } }),
    )

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-50: error 字段缺失 → 本地 invalid_response', async () => {
    const result = await generateDraft({ prompt: 'xyz' }, jsonFetcher(422, { success: false }))

    if (result.kind !== 'local') throw new Error('应为 local')
    expect(result.code).toBe('invalid_response')
  })

  it('AC-50: error.message 非字符串或空串 → 使用固定兜底文案', async () => {
    for (const message of [undefined, '', 123, null]) {
      const result = await generateDraft(
        { prompt: 'xyz' },
        jsonFetcher(500, { success: false, error: { code: 'internal_error', message } }),
      )
      if (result.kind !== 'server') throw new Error('应为 server')
      expect(result.message).toBe(GENERATE_SERVER_FALLBACK_MESSAGE)
    }
  })

  it('AC-50: 失败响应额外携带的 document 被丢弃', async () => {
    const result = await generateDraft(
      { prompt: 'xyz' },
      jsonFetcher(502, {
        success: false,
        document: draftDocument,
        error: { code: 'invalid_generated_document', message: '候选非法' },
      }),
    )

    if (result.kind !== 'server') throw new Error('应为 server')
    const record: Record<string, unknown> = { ...result }
    expect(record.document).toBeUndefined()
    expect(Object.keys(record).sort()).toEqual([
      'code',
      'issues',
      'kind',
      'message',
      'requestId',
    ])
  })

  it('AC-50: error 内的额外字段（trace / stack）被丢弃', async () => {
    const result = await generateDraft(
      { prompt: 'xyz' },
      jsonFetcher(502, {
        success: false,
        error: {
          code: 'provider_error',
          message: '上游失败',
          trace: 'Traceback ...',
          stack: 'at /tmp/x.py',
        },
      }),
    )

    if (result.kind !== 'server') throw new Error('应为 server')
    const record: Record<string, unknown> = { ...result }
    expect(record.trace).toBeUndefined()
    expect(record.stack).toBeUndefined()
  })
})

// --- I. 本地错误文案（AC-66）---

describe('I. 本地错误文案', () => {
  it('AC-66: 三类本地错误文案互不相同且非空', () => {
    const messages = [
      GENERATE_LOCAL_ERROR_MESSAGES.network_error,
      GENERATE_LOCAL_ERROR_MESSAGES.invalid_json,
      GENERATE_LOCAL_ERROR_MESSAGES.invalid_response,
    ]
    for (const message of messages) expect(message.length).toBeGreaterThan(0)
    expect(new Set(messages).size).toBe(3)
  })

  it('AC-66: 生成侧文案与精修侧文案语义可区分（提到初稿/生成）', () => {
    const joined = Object.values(GENERATE_LOCAL_ERROR_MESSAGES).join('|')
    expect(joined).toMatch(/生成|初稿/)
  })
})
