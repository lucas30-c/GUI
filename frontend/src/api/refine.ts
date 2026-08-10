// frontend/src/api/refine.ts
// 精修 API Client — 网络 JSON 在边界上一律视为 unknown，
// 只允许通过返回 boolean 的类型守卫收窄（Spec 006 C-1 ~ C-4、C-8）。

import type { DslDocument } from '../dsl/types';
import type {
  PatchDocument,
  PatchOperation,
  RefineClientResult,
  RefineLocalError,
  RefineLocalErrorCode,
  RefinementIntegrity,
  RefineRequest,
  RefineServerError,
  ValidationIssue,
} from './types';

export type Fetcher = typeof fetch;

/** 精修端点：相对路径，由 Vite dev proxy 转发（DD-4 / DD-11） */
export const REFINE_ENDPOINT = '/api/v1/dsl/refine';

/** 本地错误固定文案：前端自有，不含服务端原文、异常栈或任何 document 内容（DD-13 / AC-23） */
export const LOCAL_ERROR_MESSAGES: Record<RefineLocalErrorCode, string> = {
  network_error: '网络请求失败：无法连接精修服务，请确认后端已启动后重试。',
  invalid_json: '响应解析失败：响应体不是合法 JSON，本次结果已被拒绝。',
  invalid_response: '响应结构非法：响应不符合精修契约，本次结果已被拒绝。',
};

function localError(code: RefineLocalErrorCode): RefineLocalError {
  return { kind: 'local', code, message: LOCAL_ERROR_MESSAGES[code] };
}

/** 普通对象守卫（排除 null 与数组） */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

/**
 * 单条 operation 结构守卫：按 `op` 判别式分派（DD-17@010）。
 * - `update_props` → targetNodeId 为非空字符串 + props 为普通对象
 * - `update_style` → targetNodeId 为非空字符串 + style 为普通对象
 * - 其他（未知 op / 缺 op）→ 一律拒绝
 * 下游（`derivePatchProps` / `derivePatchStyle` / Patch 列表展示）会结构化读取这些字段，
 * 因此逐条校验必须在本层完成，不能只检查 operations 是数组。
 * TS 类型不产生任何运行时保护，判别必须是**运行时**检查。
 */
function isPatchOperationShape(value: unknown): value is PatchOperation {
  if (!isRecord(value)) return false;
  if (!isNonEmptyString(value.targetNodeId)) return false;
  if (value.op === 'update_props') return isRecord(value.props);
  if (value.op === 'update_style') return isRecord(value.style);
  return false;
}

/** C-2：patch 基本结构 — 对象 + version === "0.1" + operations 为数组且每一条结构合法 */
export function isPatchDocumentShape(value: unknown): value is PatchDocument {
  if (!isRecord(value)) return false;
  if (value.version !== '0.1') return false;
  if (!Array.isArray(value.operations)) return false;
  for (const operation of value.operations) {
    if (!isPatchOperationShape(operation)) return false;
  }
  return true;
}

/** C-3：document 基本结构 — 对象 + version 为字符串 + root 为对象且含字符串 id 与 type */
export function isDslDocumentShape(value: unknown): value is DslDocument {
  if (!isRecord(value)) return false;
  if (typeof value.version !== 'string') return false;
  const root = value.root;
  if (!isRecord(root)) return false;
  if (typeof root.id !== 'string') return false;
  return typeof root.type === 'string';
}

/**
 * C-4：integrity 基本结构 — 对象 + selectedNodeId 为非空字符串
 * + nonTargetNodesUnchanged 存在且为 boolean。
 * `false` 是合法候选值，本层放行，由提交层 C-5 拒绝。
 */
export function isRefinementIntegrityShape(value: unknown): value is RefinementIntegrity {
  if (!isRecord(value)) return false;
  if (!isNonEmptyString(value.selectedNodeId)) return false;
  return typeof value.nonTargetNodesUnchanged === 'boolean';
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

/** C-8：失败响应净化 — 只提取 code / message / issues，丢弃 document / patch / trace 等一切额外字段 */
function toServerError(rawError: unknown): RefineServerError | null {
  if (!isRecord(rawError)) return null;
  if (typeof rawError.code !== 'string') return null;
  if (typeof rawError.message !== 'string') return null;
  return {
    kind: 'server',
    code: rawError.code,
    message: rawError.message,
    issues: sanitizeIssues(rawError.issues),
  };
}

/**
 * 接收 RefineRequest，返回已净化、已通过最小运行时结构检查的本地结果。
 * 任何异常、非法 JSON、非法结构均转为安全的本地失败结果，不向上抛异常。
 */
export async function refineNode(
  request: RefineRequest,
  fetcher: Fetcher = fetch,
): Promise<RefineClientResult> {
  let response: Response;
  try {
    response = await fetcher(REFINE_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        document: request.document,
        selectedNodeId: request.selectedNodeId,
        instruction: request.instruction,
        // 空 history 省略该键 → 缺省 / null / [] 三态在后端归一化为同一结果（DD-10）
        ...(request.history && request.history.length > 0
          ? { history: request.history }
          : {}),
      }),
    });
  } catch {
    return localError('network_error');
  }

  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    return localError('invalid_json');
  }

  // C-1：success discriminant 存在、为 boolean、且与 HTTP 状态一致
  if (!isRecord(raw)) return localError('invalid_response');
  const success = raw.success;
  if (typeof success !== 'boolean') return localError('invalid_response');
  const isHttpOk = response.status >= 200 && response.status < 300;
  if (success !== isHttpOk) return localError('invalid_response');

  if (!success) {
    const serverError = toServerError(raw.error);
    if (serverError === null) return localError('invalid_response');
    return serverError;
  }

  // C-2 / C-3 / C-4
  const patch = raw.patch;
  if (!isPatchDocumentShape(patch)) return localError('invalid_response');
  const document = raw.document;
  if (!isDslDocumentShape(document)) return localError('invalid_response');
  const integrity = raw.integrity;
  if (!isRefinementIntegrityShape(integrity)) return localError('invalid_response');

  // 只构造白名单字段的新对象：envelope 上的额外字段（debug / trace 等）不透传
  return {
    kind: 'success',
    patch: { version: patch.version, operations: patch.operations },
    document,
    integrity: {
      selectedNodeId: integrity.selectedNodeId,
      nonTargetNodesUnchanged: integrity.nonTargetNodesUnchanged,
    },
  };
}
