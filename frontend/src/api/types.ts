// frontend/src/api/types.ts
// 前端精修 API 契约类型 — 与 Spec 006「前端 API 契约」章节逐字对齐

import type { DslDocument } from '../dsl/types';

/** 单条校验问题 */
export interface ValidationIssue {
  path: string;
  code: string;
  message: string;
}

/** 错误详情 */
export interface ValidationErrorDetail {
  code: string;
  message: string;
  issues: ValidationIssue[];
}

/** Patch 操作 */
export interface PatchOperation {
  op: "update_props";
  targetNodeId: string;
  props: Record<string, unknown>;
}

/** Patch 文档 */
export interface PatchDocument {
  version: "0.1";
  operations: PatchOperation[];
}

/**
 * 完整性证明（候选形状：来自网络响应，尚未通过提交层检查）。
 * `nonTargetNodesUnchanged` 为 boolean——`false` 是合法的候选值，
 * API Client 只保证该字段存在且为 boolean；`=== true` 由提交层检查（C-5）。
 * 候选/未验证类型**不得**将该字段声明为字面量 `true`。
 */
export interface RefinementIntegrity {
  selectedNodeId: string;
  nonTargetNodesUnchanged: boolean;
}

/**
 * 已验证的完整性证明（成功状态侧类型）：仅在提交层运行时检查
 * `nonTargetNodesUnchanged === true` 通过后才能获得。收窄必须来自
 * 类型守卫 / 条件判断后的自然收窄，或在检查通过后构造新对象；
 * **禁止**用 `as` 类型断言伪造字面量 `true`。
 */
export interface VerifiedRefinementIntegrity {
  selectedNodeId: string;
  nonTargetNodesUnchanged: true;
}

/** 精修请求 */
export interface RefineRequest {
  document: DslDocument;
  selectedNodeId: string;
  instruction: string;
}

/** 精修成功响应 */
export interface RefineSuccess {
  success: true;
  patch: PatchDocument;
  document: DslDocument;
  integrity: RefinementIntegrity;
}

/** 精修失败响应 */
export interface RefineFailure {
  success: false;
  error: ValidationErrorDetail;
}

/** 精修响应联合类型（后端 envelope 的**期望形状**，仅作为检查参照；网络 JSON 到达时不得直接断言为此类型） */
export type RefineResponse = RefineSuccess | RefineFailure;

// --- 前端本地结果类型（API Client 对外返回值）---

/** 成功结果：三个字段均已通过 API Client 层的最小运行时结构检查。
 *  注意：`integrity.nonTargetNodesUnchanged` 此时仅保证为 boolean（可能为 `false`），
 *  `=== true` 的检查在提交层完成（C-5）。 */
export interface RefineClientSuccess {
  kind: "success";
  patch: PatchDocument;
  document: DslDocument;
  integrity: RefinementIntegrity;
}

/** 服务端结构化失败（HTTP 非 2xx + success:false），字段已净化 */
export interface RefineServerError {
  kind: "server";
  code: string;                // 来自后端 error.code
  message: string;             // 净化后的 error.message
  issues: ValidationIssue[];   // 净化后的 error.issues（缺失时为 []）
}

/** 前端本地错误码 */
export type RefineLocalErrorCode = "network_error" | "invalid_json" | "invalid_response";

/** 前端本地错误：网络失败、非法 JSON、非法或不一致的响应结构 */
export interface RefineLocalError {
  kind: "local";
  code: RefineLocalErrorCode;
  message: string;             // 前端自有固定文案，不含服务端原文、异常栈或 document 内容
}

/** API Client 对外返回的 discriminated union（禁用 `any`，禁止类型断言绕过检查） */
export type RefineClientResult =
  | RefineClientSuccess
  | RefineServerError
  | RefineLocalError;

// --- 初稿生成契约类型（Spec 007「前端 API 契约」）---

/** 初稿生成请求 */
export interface GenerateRequest {
  prompt: string;
}

/** 生成成功结果：document 已通过 API Client 层最小运行时结构检查 */
export interface GenerateClientSuccess {
  kind: "success";
  document: DslDocument;
}

/** 生成服务端结构化失败（HTTP 非 2xx + success:false），字段已净化 */
export interface GenerateServerError {
  kind: "server";
  code: string;
  message: string;
  issues: ValidationIssue[];   // 缺失时为 []
}

/** 生成本地错误：复用 RefineLocalErrorCode（三类语义完全相同） */
export interface GenerateLocalError {
  kind: "local";
  code: RefineLocalErrorCode;  // "network_error" | "invalid_json" | "invalid_response"
  message: string;             // 前端自有固定文案
}

/** 生成 API Client 对外返回的 discriminated union */
export type GenerateClientResult =
  | GenerateClientSuccess
  | GenerateServerError
  | GenerateLocalError;
