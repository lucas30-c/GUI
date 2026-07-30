# Spec 006 — 前后端局部精修闭环（M3-02）

## 元信息

| 字段 | 值 |
|------|------|
| Spec 编号 | 006 |
| 标题 | 前后端局部精修闭环（M3-02） |
| 前置 Spec | 004（Renderer + Selection）、005（Refinement Pipeline + API） |
| 前置条件 | M3-01 实现完成、后端 310 测试通过 |

## 目标 (Goal)

1. 前端加载 Gold Case（`examples/dsl/coffee-shop-landing.json`）作为初始 `currentDocument`，页面渲染与选中交互保持 M2 行为不变。
2. 用户点击选中一个节点后，右侧精修面板显示选中信息，并提供 instruction 输入框和提交按钮。
3. 用户输入 **Mock Provider 支持的确定性精修指令**并提交，前端构造 `RefineRequest` 发送至 `POST /api/v1/dsl/refine`。本轮指令语义由 Spec 005 的 MockProvider 定义（`set_text:<新文案>` 前缀，或整条指令文本作为新文案），按选中节点类型映射到单一文案字段；**真正自由的自然语言理解留到 M4**，不属于本轮范围与验收标准。
4. 成功响应且通过"最小运行时响应检查"后，前端**原子替换** `currentDocument` 为后端返回的 `document`，页面即时反映变化。
5. 精修面板展示本次返回的 `patch`（操作列表），使用户可见"后端做了什么修改"。
6. 精修面板展示 `integrity.nonTargetNodesUnchanged = true`，证明非目标区域零变更。
7. 失败响应后，全部成功状态（`currentDocument`、`selectedNodeId`、`lastPatch`、`lastIntegrity`、`lastSuccess`）与 instruction 输入均保持不变，面板展示净化后的结构化错误信息。
8. 支持连续多轮精修：第二轮及后续轮次始终发送**上一轮成功提交后的最新 `currentDocument`**，而非静态初始值。
9. Vite 开发代理将 `/api` 请求透明转发至后端 `http://127.0.0.1:8000`，开发期间无跨域问题。
10. 前端在响应边界与提交层分层执行**最小运行时响应检查**（分层定义见"最小运行时响应检查"章节）：API Client 层负责 success discriminant、HTTP 状态与 envelope 一致性、patch/document/integrity 基本结构（含 `nonTargetNodesUnchanged` 字段存在且为 boolean）；提交层负责 `nonTargetNodesUnchanged === true`、`integrity.selectedNodeId` 与提交快照一致、返回 document 中仍存在该 selectedNodeId。任一项不通过即视为失败，不更新任何成功状态。

## 已拍板的产品与技术决策 (Design Decisions)

| # | 决策 | 理由 |
|---|------|------|
| DD-1 | 精修状态使用单个 `useReducer` 复合 state 管理（`currentDocument` / `selectedNodeId` / `lastPatch` / `lastIntegrity` / `lastSuccess` / `loading` / `error` / `instruction`），`currentDocument` 初始值为 Gold Case | 成功提交需一次性更新多个字段，单次 `dispatch` 天然保证原子性；仍不引入外部状态库（延续 M2 D1） |
| DD-2 | 前端**不重复**完整 DSL Schema 校验，**后端仍是 DSL/Patch 合法性的最终事实来源**；但网络 JSON 在边界上一律先视为 `unknown`，只有通过"最小运行时响应检查"后，`document` 才允许提交为新状态 | 重复完整校验无额外安全收益且增加前端体积；但"不做完整校验"≠"无条件信任响应"——最小检查用于防御结构畸形、完整性缺失与过期响应 |
| DD-3 | API Client 使用原生 `fetch`，不引入 axios 或其他 HTTP 库 | 减少依赖；fetch 已满足需求；与审批闸门一致 |
| DD-4 | 使用相对路径 `/api/v1/dsl/refine`，通过 Vite dev proxy 转发 | 无需硬编码后端地址；生产部署时可通过反向代理对齐 |
| DD-5 | 前端运行时检查分两层：API Client 检查 `integrity` 基本结构存在且 `nonTargetNodesUnchanged` 为 boolean；提交层检查 `nonTargetNodesUnchanged === true`、且 `integrity.selectedNodeId === 提交快照中的 selectedNodeId` | 防御响应结构畸形、完整性缺失、以及过期响应覆盖当前状态；两层检查各自可独立测试触发 |
| DD-6 | 成功提交为**整文档替换**（通过检查的 `document` 直接成为新 `currentDocument`）；前端**永不应用** `response.patch` | 后端已完成 Patch 应用 + 完整性校验；前端二次应用会引入双写与漂移风险。`patch` 仅用于面板展示 |
| DD-7 | instruction 前端限制最大 1000 字符（与后端对齐），超出时提交按钮 disabled | 前端体验优化；最终校验仍在后端 |
| DD-8 | 单请求并发策略：提交中禁止第二次提交（按钮 disabled + 忽略 `Ctrl/Cmd+Enter`） | 防止并发竞态导致状态漂移 |
| DD-9 | 失败**只允许**更新 `loading` 与 `error`；`currentDocument`、`selectedNodeId`、`lastPatch`、`lastIntegrity`、`lastSuccess`、`instruction` 一律不变 | 状态一致性优先；用户可直接修改 instruction 重试 |
| DD-10 | Vite `server.proxy` 仅用于本地开发，不修改后端 CORS 配置 | 最小变更原则；生产部署方案不在本轮范围 |
| DD-11 | 不引入环境变量配置 API 地址——固定相对路径 `/api/v1/dsl/refine` | 本阶段单机本地运行，无需多环境配置 |
| DD-12 | API Client 的 `fetch` 函数可通过参数注入替换，支持测试 | 不 mock 全局 fetch；函数签名接受可选 fetcher 参数 |
| DD-13 | 响应解析失败（非 JSON、`success` 非 boolean、必要结构缺失）视为本地错误，不更新状态；**禁止**使用 `as RefineResponse` / `as RefineSuccess` / `as unknown as RefineResponse` 等类型断言绕过运行时检查 | 防御性编程；类型断言只欺骗编译器，不校验运行时数据 |
| DD-14 | 成功后清空 instruction 输入框 | 表达"本轮指令已被消费"；用户可直接输入下一轮 |
| DD-15 | 切换选中节点后保留结果面板内容，直到新的提交发生 | 避免切换节点时丢失上一轮结果的可见性 |
| DD-16 | instruction 使用 `<textarea>`；`Enter` 输入换行，`Ctrl+Enter` / `Cmd+Enter` 提交（OD-2 拍板） | 1000 字符上限下需要多行输入；换行与提交语义分离，避免误提交 |
| DD-17 | 精修面板与现有 Info Panel 合并在右侧 320px 区域（先选中信息，后精修操作） | 复用已有布局；避免三栏复杂化 |
| DD-18 | 新增 `@playwright/test` 为 devDependency，用于 E2E 测试 | AGENTS.md §4 明确"后期 Playwright"；本轮需 E2E 验证前后端闭环 |
| DD-19 | E2E 由 `playwright.config.ts` 的 `webServer` **数组**统一启动 FastAPI 与 Vite dev server（OD-1 拍板），本地 `reuseExistingServer: !process.env.CI` | 单一入口、可重复执行；不引入 docker-compose |
| DD-20 | 不修改现有 DslRenderer 契约语义（props 接口、渲染行为、选中行为保持不变） | M2 交付已通过验收；本轮只在 App 层集成 |
| DD-21 | API Client 返回前端自有的 `RefineClientResult` discriminated union（`kind: "success" \| "server" \| "local"`），不把后端 envelope 原样透传给 UI；不使用 `any` | 本地错误与服务端错误必须可区分；UI 只消费净化后的字段 |
| DD-22 | 只允许一个 in-flight 精修请求；`loading` 期间的按钮点击与快捷键一律忽略，不发起第二次请求 | 防止并发竞态导致状态漂移 |
| DD-23 | 每次提交先捕获 `(currentDocument, selectedNodeId, instruction)` 快照，响应到达后一律用快照校验；快照 `selectedNodeId` 与当前选择（经 `latestSelectedNodeIdRef` 读取，见"旧响应校验机制"章节）不一致的旧响应被丢弃 | 防止过期响应覆盖更新后的选择或文档状态 |
| DD-24 | 真实 API smoke test 使用 `httpx.ASGITransport` 内嵌调用现有 FastAPI 应用，不启动端口、不新增 `backend/**` 文件 | 用真实后端而非 mock 验证前后端公开字段契约；零侵入、可在单条命令中执行 |
| DD-25 | `vite.config.ts` 的 `server` 段固定 `port: 5173` + `strictPort: true` | E2E baseURL 确定；避免端口漂移导致 Playwright 连接到错误服务 |

## 前端 API 契约 (Frontend API Contract)

文件位置：`frontend/src/api/types.ts`

```typescript
// frontend/src/api/types.ts

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

/** 前端本地错误：网络失败、非法 JSON、非法或不一致的响应结构 */
export interface RefineLocalError {
  kind: "local";
  code: "network_error" | "invalid_json" | "invalid_response";
  message: string;             // 前端自有固定文案，不含服务端原文、异常栈或 document 内容
}

/** API Client 对外返回的 discriminated union（禁用 `any`，禁止类型断言绕过检查） */
export type RefineClientResult =
  | RefineClientSuccess
  | RefineServerError
  | RefineLocalError;
```

命名可在实现时微调，但必须保持：以 `kind` 为 discriminant 的 union、三种互斥结果（成功 / 服务端错误 / 本地错误）、无 `any`。

## API Client 设计

文件位置：`frontend/src/api/refine.ts`

### 公开接口

```typescript
// frontend/src/api/refine.ts

import type { RefineRequest, RefineClientResult } from './types';

export type Fetcher = typeof fetch;

/**
 * 接收 RefineRequest，返回已净化、已通过最小运行时结构检查的本地结果。
 * 任何异常、非法 JSON、非法结构均转为安全的本地失败结果，不向上抛异常。
 */
export async function refineNode(
  request: RefineRequest,
  fetcher: Fetcher = fetch,
): Promise<RefineClientResult> { ... }
```

### 设计规则

1. **Content-Type**：`application/json`。
2. **路径**：相对路径 `/api/v1/dsl/refine`（Vite proxy 转发）。
3. **方法**：POST；**请求体**：`JSON.stringify(request)`，字段为 `document` / `selectedNodeId` / `instruction`。
4. **响应在边界上是 `unknown`**：`const raw: unknown = await response.json()`。后续一切字段访问必须经过返回 `boolean` 的类型守卫（type predicate，如 `isRecord(v): v is Record<string, unknown>`）窄化。**禁止** `as RefineResponse` / `as RefineSuccess` / `as unknown as RefineResponse` 等断言。
5. **HTTP 状态与 envelope 一致性**（先于内容检查）：

   | HTTP 状态 | envelope `success` | 结果 |
   |---|---|---|
   | 2xx | `true` | 继续成功结构检查（C-2 ~ C-4） |
   | 非 2xx | `false` | 预期失败 → `kind: "server"` |
   | 2xx | `false` | 不一致 → `kind: "local"`, `code: "invalid_response"` |
   | 非 2xx | `true` | 不一致 → `kind: "local"`, `code: "invalid_response"` |
   | 任意 | 缺失或非 boolean | 不可信 → `kind: "local"`, `code: "invalid_response"` |

6. **成功响应检查**：必须同时通过 `patch`、`document`、`integrity` 的必要结构检查（见下节 C-2 ~ C-4）；任一项不通过 → `kind: "local"`, `code: "invalid_response"`。对 `nonTargetNodesUnchanged`，API Client **只**检查字段存在且为 boolean 类型；`false` 是合法的候选值，API Client **不得**将其转换为 `invalid_response`，必须原样放行给上层（`=== true` 由提交层 C-5 检查并拒绝 `false`）。
7. **失败响应净化**：只提取并返回 `error.code`、`error.message`、`error.issues`（逐条只取 `path`/`code`/`message` 三个字符串字段；`issues` 缺失时为 `[]`）。
8. **额外字段不透传**：API Client 只构造包含白名单字段的新对象返回。服务端 envelope 上的任何额外字段（包括错误响应上携带的 `document`、`patch`、`trace` 等）必须被丢弃，不得到达 UI。
9. **错误分类**：
   - fetch 抛出（网络失败 / 请求被中止）→ `kind: "local"`, `code: "network_error"`。
   - `response.json()` 抛出（非法 JSON）→ `kind: "local"`, `code: "invalid_json"`。
   - 结构不合法 / HTTP 与 envelope 不一致 → `kind: "local"`, `code: "invalid_response"`。
10. **不泄露**：本地错误的 `message` 为前端自有固定文案，**不得**包含完整请求 document、响应 document、异常栈或 `error` 原始 JSON 串。
11. **测试替换**：`fetcher` 参数允许测试注入自定义 fetch 实现，不依赖全局 mock。
12. **不抛异常**：`refineNode` 任何情况下都返回 `RefineClientResult`，不向调用方抛出异常。

## 最小运行时响应检查 (Minimal Runtime Response Checks)

前端**不重复**完整 DSL Schema 校验（节点类型联合、props 必填、style 白名单、ID 全局唯一等一律由后端负责，**后端仍是最终事实来源**）。以下检查仅用于拒收畸形、不一致、完整性缺失或过期的响应：

| # | 检查项 | 执行位置 | 不通过结果 |
|---|--------|----------|-----------|
| C-1 | `success` discriminant 存在、为 boolean、且与 HTTP 状态一致 | API Client | `invalid_response` |
| C-2 | `patch` 基本结构：对象 + `version === "0.1"` + `operations` 为数组 | API Client | `invalid_response` |
| C-3 | `document` 基本结构：对象 + `version` 为字符串 + `root` 为对象且含字符串 `id` 与 `type` | API Client | `invalid_response` |
| C-4 | `integrity` 基本结构：对象 + `selectedNodeId` 为非空字符串 + `nonTargetNodesUnchanged` 字段存在且为 boolean（`false` 为合法候选值，放行给上层，不在本层拒绝） | API Client | `invalid_response`（字段缺失或非 boolean 归此） |
| C-5 | `integrity.nonTargetNodesUnchanged === true` | 提交层 | 拒绝提交，展示完整性错误 |
| C-6 | `integrity.selectedNodeId === 提交快照.selectedNodeId` | 提交层 | 拒绝提交 |
| C-7 | 返回 `document` 中仍存在提交快照的 `selectedNodeId`（递归查找） | 提交层 | 拒绝提交 |
| C-8 | 失败响应 `error` 基本结构：对象 + `code`/`message` 为字符串（`issues` 缺失时按 `[]` 处理） | API Client | `invalid_response` |

约束：

- C-1 ~ C-4、C-8 在 API Client 内完成，使提交层只面对已窄化的 `RefineClientResult`。
- C-5 ~ C-7 必须在提交层完成，因为它们需要本轮**提交快照**作为参照。
- **C-4 与 C-5 的分工**：API Client 只检查 `nonTargetNodesUnchanged` 存在且为 boolean，不检查其值；`false` 由且仅由提交层的 C-5 拒绝。两层检查各自可被独立测试触发——API Client 层用"缺失 / 非 boolean"触发 C-4，提交层用 `kind: "success"` 且值为 `false` 的结果触发 C-5，不存在不可达分支。
- 只有通过提交层检查（C-5 ~ C-7）后，才允许将 `integrity` 写入成功状态（`lastIntegrity`）。
- 以上任一项不通过，`document` 一律**不得**成为新状态。
- 以上检查不构成"前端校验层"，不得被用来"修复"、补全或重写后端响应；只能接受或拒绝。

## 状态提交规则 (State Commit Rules)

### Reducer 与原子性维护方案

精修状态由单个 `useReducer` 管理（DD-1）。复合 state 形状：

```typescript
interface RefinementState {
  currentDocument: DslDocument;                    // 前端侧页面状态
  selectedNodeId: string | null;
  lastPatch: PatchDocument | null;                 // 仅用于展示
  lastIntegrity: VerifiedRefinementIntegrity | null; // 仅用于展示；只能写入"已验证为 true"的完整性记录
  lastSuccess: { selectedNodeId: string } | null;  // 上一轮成功结果归属的节点
  loading: boolean;
  error: RefineServerError | RefineLocalError | null;
  instruction: string;
}
```

Reducer action 类型清单（穷举，不得存在其他 action）：

| Action | Payload | 语义 | 允许修改的字段 |
|---|---|---|---|
| `SELECT_NODE` | `{ nodeId: string }` | 用户点击 / 键盘选中节点 | `selectedNodeId` |
| `SET_INSTRUCTION` | `{ instruction: string }` | textarea 输入 | `instruction` |
| `REFINE_START` | — | 提交开始 | `loading: true`、`error: null` |
| `REFINE_SUCCESS` | `{ document, patch, integrity, selectedNodeId }`（其中 `integrity` 为已通过提交层 C-5 检查、类型收窄为 `VerifiedRefinementIntegrity` 的完整性记录） | **唯一的成功提交入口**，单次 dispatch 一次性完成全部更新 | `currentDocument`、`lastPatch`、`lastIntegrity`、`lastSuccess`、`instruction: ""`、`error: null`（`selectedNodeId` 保持提交快照值） |
| `REFINE_FAILURE` | `{ error: RefineServerError \| RefineLocalError }` | 服务端错误、本地错误，或任一完整性检查不通过 | 仅 `error` |
| `REFINE_END` | — | `finally` 收尾 | 仅 `loading: false` |

原子性保证：

- `REFINE_SUCCESS` 是**唯一**能写入 `currentDocument` 的 action，且在单次 `dispatch` 中完成所有成功字段更新——React 不会渲染出"document 已换、patch 未换"的中间状态。
- `REFINE_FAILURE` 在结构上无法写入任何成功字段（reducer 中只返回 `{ ...state, error }`）。
- 不得用多个独立 `useState` setter 拼凑成功提交。

### 原子提交过程（10 步）

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 捕获快照 `snapshot = { document: currentDocument, selectedNodeId, instruction }` | 之后所有校验一律以快照为参照，不读当时的最新 state |
| 2 | `dispatch(REFINE_START)`：设置 loading、清除本轮旧 error | in-flight 期间忽略新的提交触发 |
| 3 | `await refineNode({ document, selectedNodeId, instruction })` | 使用快照字段构造 `RefineRequest` |
| 4 | HTTP 状态与 envelope 一致性已通过（由 API Client 保证，C-1） | 提交层不再直接判断 HTTP 状态码 |
| 5 | 检查 `result.kind === "success"` | `"server"` / `"local"` → `REFINE_FAILURE` |
| 6 | 检查 `result.integrity.nonTargetNodesUnchanged === true`（C-5） | 非 true → `REFINE_FAILURE`（完整性错误）；`false` 在本层被拒绝——API Client 已保证该字段为 boolean 并放行 `false` 候选值，本分支可被独立测试触发 |
| 7 | 检查 `result.integrity.selectedNodeId === snapshot.selectedNodeId`（C-6） | 不等 → `REFINE_FAILURE` |
| 8 | 检查 `findNodeById(result.document.root, snapshot.selectedNodeId) !== null`（C-7） | 找不到 → `REFINE_FAILURE` |
| 9 | 全部通过 → 一次性 `dispatch(REFINE_SUCCESS)` | `currentDocument` / `lastPatch` / `lastIntegrity` / `lastSuccess` 更新，`selectedNodeId` 保持快照值，`instruction` 清空；`integrity` 经步骤 6 的运行时检查后自然收窄为 `VerifiedRefinementIntegrity` 写入（通过类型守卫 / 条件判断后的自然收窄，或在检查通过后构造新对象；**禁止** `as` 断言伪造字面量 `true`） |
| 10 | `finally` 中 `dispatch(REFINE_END)` 清除 loading | 成功与失败路径都必须执行 |

### 旧响应校验机制（latestSelectedNodeIdRef）

响应到达后需要比较"请求发起时的快照选择"与"当前最新选择"。异步回调若直接读取 reducer state，会因闭包捕获而读到发起请求那一刻的旧 state，导致旧响应校验失效。为此明确以下实现机制：

1. **维护一个始终同步最新选择的 ref**：`const latestSelectedNodeIdRef = useRef<string | null>(null)`。
2. **同步时机（写死为一种）**：在触发选择的**同一同步代码路径**中，先写入 `latestSelectedNodeIdRef.current = nodeId`，再 `dispatch(SELECT_NODE)`（即节点点击 / 键盘选中的事件处理函数内，ref 写入语句紧邻并先于 dispatch）。这保证任何异步响应回调读取 ref 时，其值一定是用户最新的选择，不受 React 渲染批处理或闭包影响。不采用"在 effect 中监听 state 变化后回写 ref"的方案。
3. **响应到达后的比较**：`refineNode` 返回后（提交过程步骤 3 之后、步骤 5 之前），比较 `latestSelectedNodeIdRef.current` 与请求发起时的 `snapshot.selectedNodeId`。
4. **不一致时丢弃响应**：一律丢弃，不得触发 `REFINE_SUCCESS`。该丢弃路径允许更新 `loading` / `error` 等瞬时状态（如通过 `REFINE_END` 结束 loading），但不得更新任何成功状态（`currentDocument`、`lastPatch`、`lastIntegrity`、`lastSuccess`、当前选择等）。
5. **不得规避**：不得通过禁止请求期间的用户选择交互（如 loading 期间禁用节点点击）来绕过该问题；现有选择交互保持不变。

### 禁止与保证（Prohibitions & Guarantees）

1. **失败不得更新成功状态**：步骤 5～8 中任一检查失败时，一律不得更新 `currentDocument`、`selectedNodeId`、`lastPatch`、`lastIntegrity`、`lastSuccess`。
2. **失败只允许更新 `loading` 与 `error`**。
3. **instruction 失败时保留**：只有 `REFINE_SUCCESS` 清空 instruction。
4. **前端永远不得应用 `response.patch`**：`patch` 只写入 `lastPatch` 用于展示；前端不得存在任何 patch 应用逻辑。
5. **第二轮必须读取第一轮成功提交后的 `currentDocument`**：快照在提交时刻从最新 state 捕获，不得闭包捕获初始 Gold Case。
6. **只允许一个 in-flight 请求**：`loading === true` 时，按钮点击与 `Ctrl/Cmd+Enter` 均不发起新请求。
7. **旧响应不得覆盖更新后的选择或文档状态**：若响应到达时 `snapshot.selectedNodeId !== latestSelectedNodeIdRef.current`（见"旧响应校验机制"章节，不得从异步闭包读取旧 state），该响应一律丢弃（既不提交成功状态，也不写入成功面板；允许结束 loading 等瞬时状态更新）。
8. **不得向用户展示服务端额外字段**：失败结果只含 `code` / `message` / `issues`（API Client 已丢弃其余字段，包括错误响应上携带的 `document`）。

## UI 布局与交互 (UI Layout & Interaction)

### 布局

```text
┌────────────────────────────────────────────────────┐
│  Header: GenUI  |  状态: 局部精修（Mock Provider）  │
├────────────────────────────┬───────────────────────┤
│                            │  精修面板（320px）     │
│   DSL 页面预览（中间）      │  ┌─ 选中信息 ───────┐ │
│   (currentDocument 渲染)   │  │  ID / Type / Props│ │
│                            │  └──────────────────┘ │
│                            │  ┌─ 精修操作 ───────┐ │
│                            │  │ instruction       │ │
│                            │  │ textarea          │ │
│                            │  │ (Ctrl/Cmd+Enter)  │ │
│                            │  │  [提交] 按钮      │ │
│                            │  └──────────────────┘ │
│                            │  ┌─ 结果 ──────────┐ │
│                            │  │  Patch 操作列表  │ │
│                            │  │  完整性证明      │ │
│                            │  │  或 错误信息     │ │
│                            │  └──────────────────┘ │
└────────────────────────────┴───────────────────────┘
```

### 交互规则（12 项明确答案）

| # | 交互问题 | 确定答案 |
|---|----------|----------|
| I-1 | 未选中节点时，提交按钮行为？ | 提交按钮 `disabled`，不可点击 |
| I-2 | instruction 为空白时，提交按钮行为？ | 提交按钮 `disabled`，不可点击（`trim()` 后为空即视为空白） |
| I-3 | 提交请求进行中时，UI 如何表现？ | 提交按钮 `disabled` + 按钮文案变为 loading 指示（如"精修中..."） |
| I-4 | instruction 使用什么输入控件、如何键盘提交？ | 使用 `<textarea>`：`Enter` 插入换行、**不提交**；`Ctrl+Enter` / `Cmd+Enter`（Meta）提交（OD-2 拍板） |
| I-5 | 服务端返回错误时如何展示？ | 精修面板结果区域显示 `error.code` + `error.message`（+ `issues` 列表），红色文字 |
| I-6 | 精修成功后 instruction 输入框行为？ | 清空输入框内容 |
| I-7 | 切换选中节点后结果面板行为？ | 保留上一次结果内容，并同时显示该结果所属的 `selectedNodeId`（取 `lastIntegrity.selectedNodeId`），避免被误读为属于当前新选中节点 |
| I-8 | 连续多轮精修时 document 来源？ | 始终发送提交时刻最新的 `currentDocument`（上一轮 `REFINE_SUCCESS` 之后的值） |
| I-9 | 精修失败后页面 / 选中 / instruction 行为？ | 成功状态与 instruction 全部保持不变——页面不变、选中节点不变、instruction 内容保留；仅 `loading` 与 `error` 变化 |
| I-10 | 快捷键在哪些情况下不得提交？ | 四种情况一律不提交：`loading` 中、未选中节点、instruction 空白、instruction 超过 1000 字符 |
| I-11 | 本地错误如何展示？ | 显示本地 `code`（`network_error` / `invalid_json` / `invalid_response`）+ 前端固定文案；不显示异常栈、请求体或响应 document |
| I-12 | 错误响应额外携带 `document` 时如何处理？ | API Client 已在边界丢弃，UI 既拿不到也不得显示任何 document 内容 |

## Vite 开发代理 (Vite Dev Proxy)

在 `frontend/vite.config.ts` 中新增 `server.proxy` 配置：

```typescript
// vite.config.ts 中新增
server: {
  port: 5173,
  strictPort: true,
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
    }
  }
}
```

约束：

- 仅用于本地开发（`npm run dev`）与 E2E。
- `strictPort: true` 保证 Playwright `baseURL`（`http://127.0.0.1:5173`）确定（DD-25）。
- 不修改后端 CORS 配置。
- 不引入环境变量。
- 生产构建（`vite build`）不包含此代理。

## E2E 方案 (E2E Setup)

### webServer 配置（OD-1 拍板）

`frontend/playwright.config.ts` 使用 `webServer` **数组**统一管理两个服务：

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://127.0.0.1:5173' },
  webServer: [
    {
      // 后端：uvicorn 仅存在于 backend/.venv（系统 python3 未安装 uvicorn）
      command: 'PYTHONPATH=src .venv/bin/python -m uvicorn genui_api.main:app --host 127.0.0.1 --port 8000',
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/health',
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
```

约束：

- 命令从仓库现有入口推导：后端模块级实例为 `genui_api.main:app`（见 `backend/src/genui_api/main.py`）；前端使用 `frontend/package.json` 已有的 `dev` 脚本。
- 后端解释器使用 `backend/.venv/bin/python`——本仓库系统 `python3` 未安装 `uvicorn`，直接写 `python3 -m uvicorn` 会启动失败。
- 两个服务的 `timeout` 均为 120s。
- 本地 `reuseExistingServer: !process.env.CI`：本地复用已启动的服务，CI 不复用。
- Chromium 安装为独立准备步骤：`npx playwright install chromium`（不写入 `postinstall`）。
- 不引入 docker-compose、不引入额外进程管理工具。
- 新增 `frontend/package.json` 脚本：`"test:e2e": "playwright test"`。

### E2E 场景：连续两轮精修

Gold Case 节点选择（来自 `examples/dsl/coffee-shop-landing.json`）：

| 角色 | 节点 ID | 类型 | 初始文案 |
|---|---|---|---|
| 第一轮目标 | `hero.title` | Heading | `Brew & Bean` |
| 第二轮目标 | `hero.primary-button` | Button | `查看菜单` |
| 非目标见证 A | `hero.subtitle` | Text | `每一杯都是匠心之作，从产地到杯中的精品咖啡体验` |
| 非目标见证 B | `menu.card-1.name` | Heading | `经典拿铁` |

执行步骤（单个 E2E 用例内顺序执行，共 12 步）：

| 步骤 | 动作 / 断言 |
|---|---|
| 1 | 由 `webServer` 启动 FastAPI（MockProvider 为默认 Provider） |
| 2 | 由 `webServer` 启动 Vite dev server |
| 3 | 打开 `baseURL` 页面，Gold Case 渲染完成 |
| 4 | 点击 `[data-node-id="hero.title"]` 选中第一轮目标节点，面板显示该 ID |
| 5 | 在 instruction textarea 输入 `set_text:E2E 第一轮标题` 并提交，第一轮完成 |
| 6 | 断言 `[data-node-id="hero.title"]` 文案变为 `E2E 第一轮标题` |
| 7 | 断言非目标内容不变：`hero.subtitle` 与 `menu.card-1.name` 文案保持初始值 |
| 8 | 断言结果面板可见 Patch 操作（`update_props` + `targetNodeId=hero.title`）与 `nonTargetNodesUnchanged: true` |
| 9 | 点击 `[data-node-id="hero.primary-button"]`，输入 `set_text:E2E 第二轮按钮` 并提交，第二轮完成 |
| 10 | 断言第二轮请求使用第一轮返回的最新 document：第二轮成功后页面上 `hero.title` 仍为 `E2E 第一轮标题`（若第二轮发送了初始 Gold Case，此处会回退为 `Brew & Bean`） |
| 11 | 断言两轮修改累计存在：`hero.title` = `E2E 第一轮标题` **且** `hero.primary-button` = `E2E 第二轮按钮` |
| 12 | 断言第二轮非目标节点仍保持不变：`hero.subtitle` 与 `menu.card-1.name` 文案仍为初始值 |

## 真实 API Smoke Test (Real API Smoke Test)

目的：用**真实 FastAPI 应用 + MockProvider**（而非前端 mock）验证前后端公开 JSON 字段契约一致。

约束：

- 使用 `httpx.ASGITransport` 内嵌调用 `genui_api.main:app`，**无需启动端口**（DD-24）。
- 请求字段与前端 `RefineRequest` 完全一致：`document` / `selectedNodeId`（驼峰）/ `instruction`。
- `document` 为真实 Gold Case（从 `examples/dsl/coffee-shop-landing.json` 读取，不复制、不改写）。
- `instruction` 使用 `set_text:` 前缀指令。
- 断言：HTTP 200、`success === true`、返回 document 中目标节点文案已更新、`integrity.nonTargetNodesUnchanged === true`、`integrity.selectedNodeId` 与请求一致、非目标节点文案未变。
- **不依赖也不修改 `backend/**`**：不新增后端源文件或测试文件，全部逻辑写在验证命令的内联脚本中（见 V-16）。

## 范围之外 (Out of Scope)

- 页面生成（从自然语言生成初始 DSL Document）
- 真实模型 Provider（OpenAI / Claude）
- 后端代码修改（backend/** 禁止修改）
- DSL/Patch Schema 修改
- Renderer 组件样式修改（不变更现有 CSS 选中态等样式语义）
- 聊天历史持久化 / 会话管理
- Undo / Redo
- 多轮对话上下文记忆（本轮每次请求只发当前 document + instruction）
- 拖拽编辑
- 属性编辑器（非自然语言编辑）
- 多用户、权限
- Docker / CI
- 真实环境部署
- API Key 配置
- 模板推荐
- 指标采集面板（M4 范围）
- **自由自然语言指令理解（M4 范围）**：本轮仅支持 Spec 005 MockProvider 定义的确定性指令（`set_text:` 前缀等），不实现任意自然语言意图识别
- 新增 React 状态管理库
- 新增 CSS-in-JS 库
- 新增 HTTP 请求库（axios 等）

## 允许的文件 (Allowed Files)

### 新建

- `specs/006-frontend-refinement-loop.md`（本文件）
- `frontend/src/api/refine.ts`（API Client）
- `frontend/src/api/types.ts`（API 类型定义）
- `frontend/src/test/refine-api.test.ts`（API Client 单元测试）
- `frontend/src/test/refinement-loop.test.tsx`（前后端闭环集成测试）
- `frontend/e2e/refinement-loop.spec.ts`（Playwright E2E 测试）
- `frontend/playwright.config.ts`（Playwright 配置）

### 允许修改

- `frontend/src/App.tsx`（集成精修面板 + currentDocument 状态）
- `frontend/src/app.css`（精修面板样式）
- `frontend/vite.config.ts`（添加 dev proxy）
- `frontend/package.json`（添加 @playwright/test devDependency + E2E 脚本）
- `frontend/package-lock.json`（锁定文件自动更新）
- `README.md`（M3-02 状态更新）
- `docs/ARCHITECTURE.md`（M3-02 里程碑更新）
- `docs/GLOSSARY.md`（新增前端 API 相关术语）
- `.gitignore`（仅添加 Playwright 产物：`test-results/`、`playwright-report/`）

### 禁止修改

- `backend/**`
- `contracts/**`
- `examples/**`
- `AGENTS.md`
- `specs/000-005`
- 现有 DSL/Patch Schema
- 现有 Renderer 契约语义（`DslRenderer` 的 props 接口与渲染行为不变）
- `frontend/src/dsl/**`（Renderer 模块源码不变）
- `frontend/src/test/renderer.test.tsx`（现有渲染测试不变）
- `frontend/src/test/selection.test.tsx`（现有选中测试不变）

## 验收标准 (Acceptance Criteria)

共 92 条，编号 AC-01 ~ AC-92 连续且不重复。

**每条 AC 必须对应一个可独立触发的测试分支**：一个测试用例只断言一条 AC 描述的那一个分支，禁止用一条宽泛测试覆盖多个分支（例如不得用「各种非法响应都不更新状态」的单个测试同时充当 AC-24 ~ AC-42 中的多条）。

### A. API Client 请求构造（AC-01 ~ AC-05）

| # | 标准 |
|---|------|
| AC-01 | `refineNode()` 构造的 request body 恰好包含 `document`、`selectedNodeId`、`instruction` 三个字段 |
| AC-02 | request body 使用 `selectedNodeId`（驼峰）作为字段名，不使用 `selected_node_id` |
| AC-03 | request body 中 `document` 为调用时传入的 `RefineRequest.document`（即最新 `currentDocument`），不是静态初始 Gold Case |
| AC-04 | 请求使用 `POST` + `Content-Type: application/json` + 相对路径 `/api/v1/dsl/refine` |
| AC-05 | `fetcher` 参数可替换为测试注入的 mock 函数，测试不 mock 全局 `fetch` |

### B. API Client 响应边界与最小结构检查（AC-06 ~ AC-23）

| # | 标准 |
|---|------|
| AC-06 | HTTP 2xx + `success: true` + 结构完整 → 返回 `kind: "success"`，含 `patch` / `document` / `integrity` |
| AC-07 | HTTP 非 2xx + `success: false` → 返回 `kind: "server"`，携带 `code` / `message` / `issues` |
| AC-08 | 失败响应 `error.issues` 缺失时归一化为 `[]`，不抛异常 |
| AC-09 | HTTP 2xx + `success: false` → 返回 `kind: "local"`，`code = "invalid_response"`（状态与 envelope 不一致） |
| AC-10 | HTTP 非 2xx + `success: true` → 返回 `kind: "local"`，`code = "invalid_response"`（状态与 envelope 不一致） |
| AC-11 | `success` 字段缺失或非 boolean → 返回 `kind: "local"`，`code = "invalid_response"` |
| AC-12 | `fetcher` 抛出异常（网络失败）→ 返回 `kind: "local"`，`code = "network_error"`，不向上抛异常 |
| AC-13 | 响应体非法 JSON（`response.json()` 抛出）→ 返回 `kind: "local"`，`code = "invalid_json"` |
| AC-14 | 成功响应 `patch` 缺失或非对象或 `patch.version !== "0.1"` → `invalid_response` |
| AC-15 | 成功响应 `patch.operations` 不是数组 → `invalid_response` |
| AC-16 | 成功响应 `document` 缺失或非对象或缺 `version` → `invalid_response` |
| AC-17 | 成功响应 `document.root` 非对象或缺 `id` / `type` → `invalid_response` |
| AC-18 | 成功响应 `integrity` 缺失或非对象或 `integrity.selectedNodeId` 非字符串 → `invalid_response` |
| AC-19 | 成功响应 `integrity.nonTargetNodesUnchanged` 字段缺失 → `invalid_response`（C-4 拒绝分支之一） |
| AC-20 | 成功响应 `integrity.nonTargetNodesUnchanged` 字段存在但非 boolean（如字符串 `"true"` 或数字 `1`）→ `invalid_response`（C-4 拒绝分支之一；注意 `false` 为合法 boolean 候选值，**不**触发本分支，API Client 放行后由提交层拒绝，见 AC-30） |
| AC-21 | 成功响应携带的额外字段（如 `debug`、`trace`）不出现在 `RefineClientSuccess` 返回值中 |
| AC-22 | 失败响应额外携带 `document` / `patch` 字段时，API Client 丢弃，`RefineServerError` 中无这些字段 |
| AC-23 | 本地错误的 `message` 为前端自有固定文案，不含服务端响应原文、异常栈或任何 document 内容 |

### C. 完整性检查与原子提交（AC-24 ~ AC-42）

| # | 标准 |
|---|------|
| AC-24 | 提交前捕获 `(currentDocument, selectedNodeId, instruction)` 快照，响应到达后一律用快照而非当前 state 校验 |
| AC-25 | `REFINE_START` 设 `loading: true` 并清除本轮之前遗留的 `error` |
| AC-26 | 全部检查通过后由**单个** `REFINE_SUCCESS` dispatch 一次性提交，源码中不存在多个 setter 串行拼凑成功状态 |
| AC-27 | `REFINE_SUCCESS` 后 `currentDocument` 严格等于响应 `document`（整文档替换） |
| AC-28 | `integrity.selectedNodeId` 不等于快照 `selectedNodeId` → 不提交，全部成功状态不变 |
| AC-29 | 返回 `document` 中不存在快照 `selectedNodeId` 对应节点 → 不提交，全部成功状态不变 |
| AC-30 | `integrity.nonTargetNodesUnchanged === false` 的响应（API Client 按 C-4 放行为 `kind: "success"`）→ 提交层按 C-5 拒绝，不提交，全部成功状态不变 |
| AC-31 | `integrity.nonTargetNodesUnchanged` 缺失的响应（API Client 按 C-4 拒为 `invalid_response`）→ 不提交，全部成功状态不变 |
| AC-32 | `kind: "server"` 结果 → 不更新 `currentDocument` / `selectedNodeId` / `lastPatch` / `lastIntegrity` / `lastSuccess` |
| AC-33 | `kind: "local"` 且 `code = "network_error"` → 不更新任何成功状态 |
| AC-34 | `kind: "local"` 且 `code = "invalid_json"` → 不更新任何成功状态 |
| AC-35 | `kind: "local"` 且 `code = "invalid_response"` → 不更新任何成功状态 |
| AC-36 | 失败时**允许**更新 `loading` 与 `error`（`error` 从 `null` 变为非 `null`），成功状态同时保持不变 |
| AC-37 | 失败时 `instruction` 保留提交前原值 |
| AC-38 | 成功时 `instruction` 被清空 |
| AC-39 | 前端**永不应用** `response.patch`：源码中不存在对 `patch.operations` 的写入式遍历或任何 patch 应用函数，`patch` 仅用于面板展示 |
| AC-40 | 第二轮请求体中 `document` 严格等于第一轮 `REFINE_SUCCESS` 提交后的 `currentDocument` |
| AC-41 | `loading` 期间再次点击提交按钮不发起第二个请求（`fetcher` 调用次数仍为 1） |
| AC-42 | 无论成功或失败，请求结束后 `loading` 均被清除为 `false` |

### D. UI 正向路径（AC-43 ~ AC-51）

| # | 标准 |
|---|------|
| AC-43 | 初始渲染以 Gold Case 为 `currentDocument`，页面正确显示 |
| AC-44 | 点击节点后精修面板显示该节点的 ID 与 Type |
| AC-45 | 输入 instruction 并点击提交后，请求发送到 `/api/v1/dsl/refine` |
| AC-46 | 请求进行中提交按钮 disabled 且 loading 指示可见 |
| AC-47 | 精修成功后页面中目标节点文案变为新值（DOM 可见差异） |
| AC-48 | 精修成功后结果面板显示 Patch 操作内容（`op` / `targetNodeId` / `props`） |
| AC-49 | 精修成功后结果面板显示 `nonTargetNodesUnchanged: true` |
| AC-50 | 精修成功后目标节点保持选中（`selectedNodeId` 不变、`data-selected` 仍在该节点） |
| AC-51 | 精修成功后非目标节点的 DOM 文案未发生变化 |

### E. UI 失败路径与禁用态（AC-52 ~ AC-59）

| # | 标准 |
|---|------|
| AC-52 | 未选中节点时提交按钮 disabled |
| AC-53 | instruction 为空或纯空白时提交按钮 disabled |
| AC-54 | instruction 超过 1000 字符时提交按钮 disabled |
| AC-55 | 失败后页面 DOM 与提交前完全一致（`currentDocument` 未变） |
| AC-56 | 失败后错误面板显示净化后的 `code` / `message` / `issues` |
| AC-57 | 错误响应额外携带 `document` 时，UI 中不出现任何 document 内容（API Client 已丢弃） |
| AC-58 | 三种本地错误（`network_error` / `invalid_json` / `invalid_response`）在 UI 上有可区分的提示文案 |
| AC-59 | 成功一轮后切换选中到另一节点，结果面板仍显示上一轮结果及其对应的 `lastIntegrity.selectedNodeId`（DD-15） |

### F. instruction 控件与键盘交互（AC-60 ~ AC-67）

| # | 标准 |
|---|------|
| AC-60 | instruction 输入控件为 `<textarea>`（OD-2 拍板） |
| AC-61 | 单独按 `Enter` 在 textarea 中插入换行，**不**触发提交（`fetcher` 未被调用） |
| AC-62 | `Ctrl+Enter` 触发提交 |
| AC-63 | `Cmd(Meta)+Enter` 触发提交 |
| AC-64 | `loading` 期间 `Ctrl/Cmd+Enter` 不触发提交 |
| AC-65 | 未选中节点时 `Ctrl/Cmd+Enter` 不触发提交 |
| AC-66 | instruction 为空或纯空白时 `Ctrl/Cmd+Enter` 不触发提交 |
| AC-67 | instruction 超过 1000 字符时 `Ctrl/Cmd+Enter` 不触发提交 |

### G. 配置与类型安全（AC-68 ~ AC-71）

| # | 标准 |
|---|------|
| AC-68 | `vite.config.ts` 含 `/api` → `http://127.0.0.1:8000` 的 dev proxy |
| AC-69 | `vite.config.ts` 含 `port: 5173` + `strictPort: true`（DD-25） |
| AC-70 | 前端源码中不存在 `as RefineResponse` / `as RefineSuccess` / `as unknown as RefineResponse` 等绕过运行时检查的类型断言（DD-13） |
| AC-71 | `frontend/src/api/**` 与 App 精修状态代码中不出现 `any` 类型 |

### H. 真实 API Smoke Test（AC-72 ~ AC-75）

| # | 标准 |
|---|------|
| AC-72 | Smoke test 通过 `httpx.ASGITransport` 调用真实 `genui_api.main:app` 的 `POST /api/v1/dsl/refine`，使用真实 Gold Case document 与前端同名驼峰字段，HTTP 状态为 200 |
| AC-73 | Smoke test 响应 `success === true` |
| AC-74 | Smoke test 返回 document 中目标节点文案已更新为 `set_text:` 指定的新值 |
| AC-75 | Smoke test 响应 `integrity.nonTargetNodesUnchanged === true`、`integrity.selectedNodeId` 与请求一致、且非目标节点文案未变 |

### I. E2E 连续两轮闭环（AC-76 ~ AC-83）

| # | 标准 |
|---|------|
| AC-76 | `playwright.config.ts` 的 `webServer` 数组同时启动 FastAPI 与 Vite，E2E 可由单条命令运行（OD-1 拍板） |
| AC-77 | 页面加载后可点击选中 `hero.title` 节点 |
| AC-78 | 第一轮：对 `hero.title` 提交 `set_text:` 指令后，页面该节点文案更新为新值 |
| AC-79 | 第一轮后非目标节点 `hero.subtitle` 与 `menu.card-1.name` 文案保持原值不变 |
| AC-80 | 第一轮后页面可见 Patch 操作内容与 `nonTargetNodesUnchanged: true` |
| AC-81 | 第二轮：选中 `hero.primary-button` 并提交 `set_text:` 指令后成功返回 |
| AC-82 | 第二轮完成后两轮修改**累计**存在：`hero.title` 与 `hero.primary-button` 同时显示各自的新文案（证明第二轮请求基于第一轮返回的最新 document） |
| AC-83 | 第二轮后非目标节点 `hero.subtitle` 与 `menu.card-1.name` 仍保持原值不变 |

### J. 回归（AC-84 ~ AC-91）

| # | 标准 |
|---|------|
| AC-84 | 前端全部单元测试通过，总数 ≥ 140（现有 75 个 + 本轮新增分支测试） |
| AC-85 | 后端 310 个测试通过（无回归） |
| AC-86 | `DslRenderer` 契约语义与 `frontend/src/dsl/**` 源码未修改 |
| AC-87 | 现有 `renderer.test.tsx` / `selection.test.tsx` / `style.test.ts` 未被修改、削弱或删除，且全部通过 |
| AC-88 | DSL Schema 与 Patch Schema 文件未变更 |
| AC-89 | Gold Case `examples/dsl/coffee-shop-landing.json` 未变更 |
| AC-90 | `backend/**` 未变更（含 smoke test 不新增后端文件） |
| AC-91 | `npm run typecheck` 与 `npm run build` 均通过 |

### K. 旧响应竞态（AC-92）

| # | 标准 |
|---|------|
| AC-92 | 请求进行期间用户切换选中节点，旧响应返回后被丢弃：不得覆盖当前选择（`selectedNodeId`）、`currentDocument` 或上一轮成功结果（`lastPatch` / `lastIntegrity` / `lastSuccess`），不触发 `REFINE_SUCCESS`（允许结束 loading 等瞬时状态更新） |

**AC-92 竞态测试实现策略**（写入 `frontend/src/test/refinement-loop.test.tsx`）：使用 deferred Promise（手动控制 resolve 时机的 Promise）mock API Client 的 `fetcher`——

1. 选中节点 A，发起精修请求；mock `fetcher` 返回一个尚未 resolve 的 deferred Promise（请求处于 pending）；
2. 模拟用户点击切换选中到节点 B（选择交互不被禁用，见"旧响应校验机制"第 5 条）；
3. 手动 resolve 该 deferred Promise，让针对节点 A 的旧响应此时才返回；
4. 断言：`currentDocument` 未被旧响应的 document 覆盖、当前选择仍为节点 B、上一轮成功结果（`lastPatch` / `lastIntegrity` / `lastSuccess`）均未被覆盖。

## 验证命令 (Verification Commands)

共 27 条（V-01 ~ V-27）。全部使用**仓库相对路径**，均从仓库根目录执行；不得出现任何本机绝对路径。需切换目录的命令统一用子 shell `( cd … && … )` 包裹，避免目录漂移。优先复用 `frontend/package.json` 已有脚本。

```bash
# === 准备 ===

# V-01. 安装前端依赖（含新增 @playwright/test）
( cd frontend && npm install )

# V-02. 安装 Playwright Chromium 浏览器（E2E 前置）
( cd frontend && npx playwright install chromium )

# === 前端验证 ===

# V-03. TypeScript 类型检查（复用已有 script）
( cd frontend && npm run typecheck )

# V-04. 全部前端单元测试（npm test 为 watch 模式，必须传 --run）
( cd frontend && npm test -- --run )

# V-05. API Client 专项测试
( cd frontend && npm test -- --run src/test/refine-api.test.ts )

# V-06. 精修闭环集成测试
( cd frontend && npm test -- --run src/test/refinement-loop.test.tsx )

# V-07. 现有 Renderer / Selection / Style 测试无回归
( cd frontend && npm test -- --run src/test/renderer.test.tsx src/test/selection.test.tsx src/test/style.test.ts )

# V-08. 生产构建成功（复用已有 script，内含 tsc -b）
( cd frontend && npm run build )

# V-09. 依赖白名单检查（仅允许新增 @playwright/test）
( cd frontend && python3 -c "
import json,sys
pkg = json.load(open('package.json'))
allowed_deps = {'react','react-dom'}
allowed_dev = {'typescript','vite','@vitejs/plugin-react','vitest','jsdom',
  '@testing-library/react','@testing-library/jest-dom','@testing-library/user-event',
  '@types/react','@types/react-dom','@playwright/test'}
extra_deps = set(pkg.get('dependencies',{})) - allowed_deps
extra_devs = set(pkg.get('devDependencies',{})) - allowed_dev
if extra_deps: print(f'FAIL: 未批准运行时依赖: {extra_deps}'); sys.exit(1)
if extra_devs: print(f'FAIL: 未批准开发依赖: {extra_devs}'); sys.exit(1)
print('DEPS OK')
" )

# V-10. 安全扫描（禁止内容不得出现在前端源码）
grep -rn -E "dangerouslySetInnerHTML|eval\(|new Function\(|exec\(" frontend/src/ && echo "FAIL: 存在禁止内容" || echo "OK: clean"

# V-11. 禁止用类型断言绕过运行时检查（AC-70）
grep -rn -E "as +(RefineResponse|RefineSuccess|RefineFailure)|as +unknown +as" frontend/src/api/ frontend/src/App.tsx && echo "FAIL: 存在类型断言绕过" || echo "OK: no assertion bypass"

# V-12. 禁止 any（AC-71）
grep -rn -E ":\s*any\b|<any>|as +any" frontend/src/api/ frontend/src/App.tsx && echo "FAIL: 存在 any" || echo "OK: no any"

# V-13. Vite proxy 与 strictPort 配置存在（AC-68 / AC-69）
grep -nE "proxy|127\.0\.0\.1:8000|strictPort|port" frontend/vite.config.ts

# V-14. 前端不应用 response.patch（AC-39）
grep -rn -E "applyPatch|apply_patch|operations\.(forEach|reduce)" frontend/src/ && echo "FAIL: 前端尝试应用 patch" || echo "OK: patch 仅展示"

# === 后端回归验证 ===

# V-15. 后端全量测试通过
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest --tb=short -q )

# V-16. 后端 API 专项测试（含 /api/v1/dsl/refine）
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/api/ --tb=short -q )

# V-17. 后端测试计数（确认 310 个）
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest --collect-only -q | tail -1 )

# === 真实 API Smoke Test ===

# V-18. 用真实 FastAPI 应用 + 真实 Gold Case 验证前端公开字段契约（AC-72 ~ AC-75）
#       httpx.ASGITransport 内嵌调用，不启动端口、不新增 backend/** 文件
( cd backend && PYTHONPATH=src .venv/bin/python - <<'PY'
import asyncio, json, httpx
from genui_api.main import app

GOLD = "../examples/dsl/coffee-shop-landing.json"
TARGET = "hero.title"        # Heading, props.text = "Brew & Bean"
WITNESS = "hero.subtitle"    # 非目标见证节点
NEW_TEXT = "Smoke Test 标题"

def find_node(node, node_id):
    if node.get("id") == node_id:
        return node
    for child in node.get("children") or []:
        hit = find_node(child, node_id)
        if hit is not None:
            return hit
    return None

with open(GOLD, encoding="utf-8") as fh:
    document = json.load(fh)

before_target = find_node(document["root"], TARGET)["props"]["text"]
before_witness = find_node(document["root"], WITNESS)["props"]["text"]

# 字段名与前端 RefineRequest 完全一致（驼峰 selectedNodeId）
payload = {
    "document": document,
    "selectedNodeId": TARGET,
    "instruction": f"set_text:{NEW_TEXT}",
}

async def call():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:
        return await client.post("/api/v1/dsl/refine", json=payload)

resp = asyncio.run(call())
assert resp.status_code == 200, f"FAIL status={resp.status_code} body={resp.text[:200]}"
body = resp.json()
assert body["success"] is True, f"FAIL success={body}"

after_target = find_node(body["document"]["root"], TARGET)["props"]["text"]
after_witness = find_node(body["document"]["root"], WITNESS)["props"]["text"]

assert after_target == NEW_TEXT, f"FAIL target not updated: {after_target!r}"
assert after_target != before_target, "FAIL target unchanged"
assert after_witness == before_witness, f"FAIL witness changed: {after_witness!r}"
assert body["integrity"]["nonTargetNodesUnchanged"] is True, "FAIL integrity flag"
assert body["integrity"]["selectedNodeId"] == TARGET, "FAIL integrity.selectedNodeId"
assert body["patch"]["version"] == "0.1", "FAIL patch.version"
assert isinstance(body["patch"]["operations"], list), "FAIL patch.operations"

print("SMOKE OK", json.dumps(
    {"before": before_target, "after": after_target, "witness": after_witness},
    ensure_ascii=False))
PY
)

# === E2E ===

# V-19. Playwright E2E 连续两轮闭环（webServer 数组自动启动 FastAPI + Vite）
( cd frontend && npm run test:e2e )

# === 无变更验证 ===

# V-20. DSL Schema 未变更
git diff --exit-code -- contracts/dsl/v0.1/schema.json

# V-21. Patch Schema 未变更
git diff --exit-code -- contracts/patch/v0.1/schema.json

# V-22. Gold Case 未变更
git diff --exit-code -- examples/dsl/coffee-shop-landing.json

# V-23. backend/** 未变更
git diff --exit-code -- backend/

# V-24. Renderer 源码未修改
git diff --exit-code -- frontend/src/dsl/

# V-25. 现有前端测试文件未修改
git diff --exit-code -- frontend/src/test/renderer.test.tsx frontend/src/test/selection.test.tsx frontend/src/test/style.test.ts

# === 整体检查 ===

# V-26. 空白与行尾问题检查
git diff --check

# V-27. 仓库状态与变更规模
git status --short && git diff --stat
```

补充说明：

- V-19 依赖 `frontend/package.json` 新增脚本 `"test:e2e": "playwright test"`。
- 后端命令使用 `.venv/bin/python`：系统 `python3` **未安装** uvicorn，后端依赖仅存在于 `backend/.venv`。
- 不使用 `grep -c` 统计测试符号数量；测试计数以 V-04 / V-17 的测试框架原生汇总输出为准。

## 审批闸门 (Approval Gates)

| # | 审批项 | 内容 |
|---|--------|------|
| 1 | M3-02 产品范围 | 本 Spec "目标" 章节所列 10 项目标（含「仅确定性指令，自由自然语言留到 M4」） |
| 2 | 状态模型与原子提交语义 | "状态提交规则" 章节：`useReducer` 复合 state + 6 项 action 清单 + **10 步**原子提交过程 + **8 条**禁止与保证 |
| 3 | API Client 公开边界 | `refineNode(request, fetcher?)` 签名，返回 `RefineClientResult` discriminated union（DD-21） |
| 4 | 最小运行时响应检查 | "最小运行时响应检查" 章节 C-1 ~ C-8 全表，含 HTTP/envelope 一致性矩阵（DD-2 / DD-5） |
| 5 | Vite proxy 与端口策略 | `/api` → `http://127.0.0.1:8000`；`port: 5173` + `strictPort: true`（DD-10 / DD-25） |
| 6 | 单请求并发与快照策略 | 只允许一个 in-flight 请求；旧响应按快照丢弃（DD-8 / DD-22 / DD-23） |
| 7 | UI 布局与交互行为 | "UI 布局与交互" 章节 **12 项**交互确定答案（含 textarea + Ctrl/Cmd+Enter） |
| 8 | Allowed Files | "允许的文件" 章节完整清单（边界与上一版一致，未扩大） |
| 9 | Acceptance Criteria | AC-01 ~ AC-92 完整列表，每条对应一个可独立触发的测试分支 |
| 10 | 新增 `@playwright/test` 开发依赖 | 本轮**唯一**新增依赖，仅 devDependency；需 `npx playwright install chromium` |
| 11 | E2E 启动方式（OD-1 已拍板） | `playwright.config.ts` 的 `webServer` **数组**同时启动 FastAPI（`.venv/bin/python -m uvicorn`）与 Vite（`npm run dev`），timeout 120s，`reuseExistingServer: !process.env.CI`，不引入 docker-compose |
| 12 | E2E 覆盖连续两轮 | "E2E 方案" 章节 12 步场景与 Gold Case 节点表（`hero.title` → `hero.primary-button`） |
| 13 | 真实 API Smoke Test | `httpx.ASGITransport` 内嵌调用真实后端（DD-24 / V-18），不启端口、不新增 `backend/**` 文件 |
| 14 | 验证命令清单 | V-01 ~ V-27 全部使用仓库相对路径 |

## 开放决策 (Open Decisions)

None。

原 OD-1（E2E 后端启动方式）与 OD-2（instruction 输入控件形态）已在本版拍板：

- **OD-1 → 已拍板**：`playwright.config.ts` 使用 `webServer` 数组统一管理 FastAPI 与 Vite，命令从仓库现有入口推导，timeout 120s，本地 `reuseExistingServer: !process.env.CI`（CI 不复用），Chromium 由 `npx playwright install chromium` 安装，不引入 docker-compose。详见 DD-19 与 "E2E 方案" 章节。
- **OD-2 → 已拍板**：instruction 使用 `<textarea>`，`Enter` 输入换行，`Ctrl+Enter` / `Cmd+Enter` 提交；loading、无选中节点、instruction 空白或超过 1000 字符时快捷键一律不提交。详见 DD-16 与 AC-60 ~ AC-67。

实现过程中如出现本 Spec 未覆盖的新决策点，必须暂停并上报，不得自行拍板。

## 完成报告格式 (Completion Report Format)

按 AGENTS.md §10 固定格式输出，包含以下小节：

```text
## Result
## Repository State
## Files Created
## Files Modified
## Key Decisions Recorded
## Acceptance Criteria     （逐条 AC-01 ~ AC-92 标记 PASS / FAIL，附证据）
## Verification            （实际运行的 V-01 ~ V-27 命令与真实输出；未运行的写明"未运行"及原因）
## Scope Check             （是否安装未授权依赖/触碰范围外文件/删除文件）
## Open Decisions          （需所有者决定的问题；没有则写 None）
## Git Summary             （git status --short 与 git diff --stat）
## Recommended Next Task   （只提一个建议，不执行）
```

报告必须如实。没做的、没运行的，就直说。隐瞒失败的报告本身就是失败。
