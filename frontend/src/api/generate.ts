// frontend/src/api/generate.ts
// 初稿生成 API Client — 网络 JSON 在边界上一律视为 unknown，
// 只允许通过返回 boolean 的类型守卫收窄（Spec 007 G-1 ~ G-7、DD-14 / DD-15）。

import { isDslDocumentShape, isRecord } from './refine';
import type { Fetcher } from './refine';
import type {
  GenerateClientResult,
  GenerateLocalError,
  GenerateRequest,
  GenerateServerError,
  RefineLocalErrorCode,
  ValidationIssue,
} from './types';

/** 生成端点：相对路径，由 Vite dev proxy 转发 */
export const GENERATE_ENDPOINT = '/api/v1/dsl/generate';

/** 生成侧本地错误固定文案：前端自有，不含服务端原文、异常栈或任何 document 内容 */
export const GENERATE_LOCAL_ERROR_MESSAGES: Record<RefineLocalErrorCode, string> = {
  network_error: '网络请求失败：无法连接初稿生成服务，请确认后端已启动后重试。',
  invalid_json: '响应解析失败：生成响应体不是合法 JSON，本次初稿已被拒绝。',
  invalid_response: '响应结构非法：生成响应不符合初稿契约，本次初稿已被拒绝。',
};

/** 服务端 error 字段缺失或非法时的兜底文案 */
export const GENERATE_SERVER_FALLBACK_MESSAGE =
  '初稿生成失败：服务端未提供可展示的错误说明。';

function localError(code: RefineLocalErrorCode): GenerateLocalError {
  return { kind: 'local', code, message: GENERATE_LOCAL_ERROR_MESSAGES[code] };
}

/** 单条 issue 净化守卫：只承认 path / code / message 三个字符串字段 */
function isValidationIssueShape(value: unknown): value is ValidationIssue {
  if (!isRecord(value)) return false;
  return (
    typeof value.path === 'string' &&
    typeof value.code === 'string' &&
    typeof value.message === 'string'
  );
}

/** 净化 issues：非数组按 [] 处理，逐条只取三个字符串字段，丢弃其余 */
function sanitizeIssues(value: unknown): ValidationIssue[] {
  if (!Array.isArray(value)) return [];
  const issues: ValidationIssue[] = [];
  for (const candidate of value) {
    if (isValidationIssueShape(candidate)) {
      issues.push({
        path: candidate.path,
        code: candidate.code,
        message: candidate.message,
      });
    }
  }
  return issues;
}

/** G-7：失败响应净化 — 只提取 code / message / issues，丢弃 document / trace 等一切额外字段。
 *  requestId 来自失败 envelope 顶层（或响应头 X-Request-ID），由调用方传入。 */
function toServerError(rawError: unknown, requestId: string): GenerateServerError | null {
  if (!isRecord(rawError)) return null;
  if (typeof rawError.code !== 'string') return null;
  const message =
    typeof rawError.message === 'string' && rawError.message.length > 0
      ? rawError.message
      : GENERATE_SERVER_FALLBACK_MESSAGE;
  return {
    kind: 'server',
    code: rawError.code,
    message,
    requestId,
    issues: sanitizeIssues(rawError.issues),
  };
}

/**
 * 接收 GenerateRequest，返回已净化、已通过最小运行时结构检查的本地结果。
 * 任何异常、非法 JSON、非法结构均转为安全的本地失败结果，不向上抛异常。
 */
export async function generateDraft(
  request: GenerateRequest,
  fetcher: Fetcher = fetch,
): Promise<GenerateClientResult> {
  let response: Response;
  try {
    // 请求体只含 prompt：不透传调用方对象上的任何额外字段
    response = await fetcher(GENERATE_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: request.prompt }),
    });
  } catch {
    // G-1
    return localError('network_error');
  }

  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    // G-2
    return localError('invalid_json');
  }

  // G-3：响应体为对象且 success 为 boolean
  if (!isRecord(raw)) return localError('invalid_response');
  const success = raw.success;
  if (typeof success !== 'boolean') return localError('invalid_response');

  // G-4：HTTP 状态与 envelope discriminant 一致
  const isHttpOk = response.status >= 200 && response.status < 300;
  if (success !== isHttpOk) return localError('invalid_response');

  if (!success) {
    // G-7；requestId：envelope 顶层优先，响应头兜底
    const requestId =
      typeof raw.requestId === 'string'
        ? raw.requestId
        : response.headers.get('X-Request-ID') ?? '';
    const serverError = toServerError(raw.error, requestId);
    if (serverError === null) return localError('invalid_response');
    return serverError;
  }

  // G-5
  const document = raw.document;
  if (!isDslDocumentShape(document)) return localError('invalid_response');

  // G-6：只提取 document，envelope 上的额外字段（patch / debug / trace 等）不透传
  return { kind: 'success', document };
}
