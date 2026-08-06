# ARCHITECTURE.md — GenUI 受控原型架构文档

本文档只定义架构方案与边界，不包含实现代码。实现细节由后续 Spec 逐份驱动。术语统一定义见 [GLOSSARY.md](GLOSSARY.md)。

## 1. 系统上下文 (System Context)

单用户本地运行的原型系统：

```text
Browser (React SPA)
   │  HTTP/JSON
   ▼
Backend (FastAPI)
   ├── Model Provider 接口（Mock Provider / 真实模型，同接口可替换）
   ├── DSL 校验与 Patch 应用引擎（确定性代码）
   ├── 模板推荐与自进化模块（规则 / 简单聚类 / embedding 检索）
   └── 本地 JSON 存储（页面状态、Trace、模板库、模拟历史对话）
```

核心数据流（每一轮精修都走同一条管线）：

```text
User Intent
→ Model Provider
→ Structured Candidate Output
→ Schema Validation
→ Business Rule Validation
→ Patch Boundary Validation
→ Apply Patch to a copy
→ Verify non-target nodes unchanged
→ Commit new document state
→ Record trace
```

原则：**模型只提出候选修改，确定性代码决定是否接受。** 管线的任何一环失败，状态都不变。

## 2. 前端职责 (Frontend Responsibilities)

- 把 DSL Document 渲染为页面（React UI 只负责渲染 DSL，不保存另一套独立页面结构）。
- 管理选中交互：点击/框选 → 记录 `selectedNodeId`，渲染选中态视觉反馈。
- 维护编辑会话：对话历史、当前 `selectedNodeId`、当前文档版本标识。
- 发起请求：把 `{本轮指令, 选中控件上下文, 当前页面状态或版本}` 发给后端。
- 应用返回：接收后端确认后的新 DSL Document（或已应用 Patch 的结果），只更新对应子树的渲染，不重绘整页。
- 展示指标与 Trace 摘要（对话轮次、校验结果、零变更证明）。

前端**不**承担：Patch 合法性判断、DSL Schema 校验的最终裁决——前端校验只做体验优化，后端校验才是事实来源。

## 3. 后端职责 (Backend Responsibilities)

- 持有 DSL Document 的服务端事实来源（会话内状态 + 本地 JSON 持久化）。
- 组装 Prompt（SP/UP 分层，见 §11 与后续 Prompt Spec）并调用 Model Provider。
- 执行完整校验管线：Schema → 业务规则 → Patch 边界。
- 应用 Patch 到副本、执行非目标子树完整性校验、提交新状态。
- 记录 Trace：每轮的输入、候选输出、校验结果、应用结果、指标数据点。
- 模板推荐与自进化：沉淀模板、匹配新意图、更新模板库。
- 拒绝一切非法请求：未注册组件类型、越界 Patch、ID 变更企图等。

## 4. API 层 (API Layer) — M1-02 新增

### 应用入口

FastAPI 应用由 `genui_api.main:app` 导出，内部通过 `create_app()` 工厂函数创建。

### 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /api/v1/dsl/validate | DSL 文档校验 |
| POST | /api/v1/dsl/generate | 一句话生成初稿（Generation Pipeline + Generation Provider） |
| POST | /api/v1/dsl/refine | 局部精修（Refinement Pipeline + Provider） |

### 职责边界

API 层只作为底层校验层（`contracts/` 模块）的 HTTP 适配器：接收请求、调用已有校验逻辑、格式化响应。API 不复制也不重新实现校验规则。

## 4.1 Patch 核心模块 (Patch Core) — M1-03 新增

### 模块位置

`backend/src/genui_api/patch/`

### 职责

Patch 核心负责将结构化 Patch 应用于 DSL 文档。当前仅支持 `update_props` 操作类型。

### 关键设计

- **深拷贝**：对源文档执行 `copy.deepcopy()`，保护原始对象不可变。
- **顺序执行**：多个操作按 operations 数组顺序依次执行。
- **原子性**：所有操作成功且后校验通过才返回结果；任一步骤失败则整体失败，不产生部分修改。
- **后校验**：Patch 应用后对整个 Patched Document 调用 `contracts.validation.validate_dsl_document()` 执行完整 DSL 校验。

### 依赖

Patch 模块依赖 `genui_api.contracts.validation.validate_dsl_document()` 进行源文档校验和后校验。

### 当前状态

M1-03 完成。**Patch HTTP API 尚未实现**——当前仅可通过 Python 函数 `apply_patch(document, patch)` 调用。

### 错误分类

| HTTP 状态码 | 错误类型 | 触发条件 |
|-------------|----------|----------|
| 415 | Unsupported Media Type | Content-Type 非 `application/json` |
| 400 | Bad Request | JSON 解析失败 |
| 422 | `invalid_dsl_structure` | Pydantic 结构校验错误 |
| 422 | `invalid_dsl_business_rule` | 业务规则校验错误 |
| 500 | Internal Server Error | 未预期内部异常（兜底） |

## 4.3 Provider 模块 (Provider Module) — M3 新增

### 模块位置

`backend/src/genui_api/provider/`

### 职责

定义 RefinementProvider Protocol 和具体实现（当前为 MockProvider）。Provider 接收 RefinementContext（选中节点信息 + 指令），返回候选 Patch dict（不可信，需校验）。

### 关键设计

- **Protocol 定义**：使用 `typing.Protocol`，任何具有匹配签名的类自动满足接口。
- **最小权限**：RefinementContext 仅暴露选中节点相关信息，不传递完整文档。
- **MockProvider**：确定性映射，无网络、无随机、无密钥。根据 `selected_node_type` 选择合法文案字段。
- **依赖注入**：通过 FastAPI Depends + `create_app(refinement_provider)` 注入，可测试。

## 4.4 Refinement 模块 (Refinement Module) — M3 新增

### 模块位置

`backend/src/genui_api/refinement/`

### 职责

无状态异步编排函数 `refine()`，实现 10 步 Refinement Pipeline：校验指令 → 校验源文档 → 查找节点 → 构造上下文 → 调用 Provider → 校验候选结构 → 边界检查 → 应用 Patch → 完整性验证 → 返回结果。

### 关键设计

- **不可变输入**：不修改传入的 document 和 instruction。
- **可信 ID**：使用原始 selected_node_id 做边界检查，不受 Provider 修改 context 影响。
- **深拷贝 props**：传给 Provider 的 selected_node_props 是深拷贝，Provider 修改不影响原始文档。
- **完整性验证**：使用 `model_dump(mode="json", by_alias=True)` 序列化后移除目标 props 再做全量深等比较。

## 4.5 Generation 模块 (Generation Module) — M4-01 新增

### 模块位置

`backend/src/genui_api/generation/`

### 职责

一句话需求 → 初稿 DSL Document 的最小生成链路：`base.py` 定义 GenerationProvider Protocol 与 UnrecognizedIntentError，`mock.py` 为确定性 Mock 实现，`templates.py` 存放三套独立内置初稿模板，`pipeline.py` 提供无状态异步编排函数 `generate_document()`。

### 关键设计

- **Protocol 定义**：`async def generate_draft(self, prompt: str) -> dict`，与 RefinementProvider 同构，可替换为真实模型实现。
- **不可信候选**：Provider 输出一律视为不可信候选，必须经 `contracts/validation.py` 的 `validate_dsl_document()` 这一唯一校验入口，生成侧不复制任何校验规则。
- **Pipeline 六步**：校验 prompt → 调用 Provider → 捕获 UnrecognizedIntentError → 捕获 Provider 异常 → 校验候选文档 → 返回结果。
- **确定性 Mock 映射**：`strip()` + `lower()` 子串匹配，固定优先级 咖啡店 > 活动报名 > 产品介绍；无匹配抛出 UnrecognizedIntentError，不做静默兜底。
- **模板隔离**：每次返回 `copy.deepcopy(模板常量)`，避免跨请求污染。
- **错误分类**：`invalid_prompt` → 400、`unrecognized_intent` → 422、`invalid_generated_document` / `provider_error` → 502，由 API 层独立的 `_GENERATION_ERROR_HTTP_MAP` 映射，不影响精修侧映射表。

## 4.2 前端模块 (Frontend Module) — M2 新增

### 模块位置

`frontend/`

### 技术栈

React + TypeScript + Vite

### 关键架构点

- **DSL Types 为 Discriminated Union**：前端手写 TS 类型（D4 决策），JSON Schema 保持为契约事实来源。
- **递归 DslRenderer**：单一 React 组件根据节点 `type` 递归渲染整棵 DSL 树为语义 HTML。
- **Style 白名单映射器**：纯函数，将 DSL Style 对象转为 React CSSProperties，仅允许 11 个白名单字段。
- **selectedNodeId 存储于 React state**（D1 决策：useState，不引入外部状态库），永远不写入 DSL。
- **Gold Case 静态加载**：当前直接导入 `examples/dsl/coffee-shop-landing.json`，无后端请求。

### 当前状态

M2 完成。**尚未实现**：后端集成、Patch API 调用、模型接入、对话功能。

## 5. 共享契约 (Shared Contracts)

前后端共享的契约（第一版以文档 + JSON Schema 形式定义，双端各自维护类型）：

1. **DSL Document Schema**：节点结构、组件类型枚举、各组件允许的 props。
2. **Patch Schema**：操作类型、目标引用方式（仅允许稳定 ID）、允许修改的属性路径。
3. **API 契约**：生成初稿、局部精修、模板推荐、指标查询等端点的请求/响应形状。
4. **选中控件上下文契约**：`selectedNodeId` + 该节点的语义摘要（类型、当前 props、在页面结构中的路径），供模型理解"用户选中了谁"。

契约变更属于审批闸门（见 AGENTS.md §6），必须经项目所有者批准并记录 ADR。

## 6. DSL 文档模型 (DSL Document Model)

- 页面是一棵 DSL Node 树，根为 `Page` 节点。
- 每个节点：`id`（稳定、全局唯一）、`type`（注册组件类型之一）、`props`（受 Schema 约束）、`children`（仅容器类组件允许）。
- **Stable Node ID**：节点创建时由系统（非模型）分配，整个生命周期不变；Patch 不得创建、删除、覆盖或修改任何 ID。编辑操作的锚点只能是 ID。
- DSL Document 是页面状态的**唯一事实来源**。React 渲染结果、模型对页面的理解，都只是它的投影。
- 文档版本：每次提交产生新版本标识，用于并发/漂移检测与 Trace 关联。

## 7. 组件注册表 (Component Registry)

- 组件注册表是前后端共享的固定清单：`Page / Section / Heading / Text / Button / Image / Card / Form / Input`。
- 注册表定义每种组件：允许的 props 及类型、允许 children 与否、各 prop 是否可被 Patch 修改。
- **未注册的组件类型必须被拒绝**——无论出现在 DSL 还是 Patch 中。
- 第一版不为注册表做插件化扩展机制；新增组件 = 修改注册表 + 更新 Schema + 补测试，走审批闸门。

## 8. 选中状态 (Selection State)

- `selectedNodeId` 是**编辑上下文**，保存在会话状态中，**不属于** DSL 节点内容（DSL 里不写"被选中"标记，避免选中行为污染页面数据）。
- 同一时刻最多一个选中控件；切换选中控件即替换上下文。
- 选中控件上下文随每轮请求传给后端：节点 ID、类型、当前 props 快照、结构路径（如 `Page > Section[1] > Button`）。
- 若 Patch 管线失败或文档被外部替换，前端需重新校验 `selectedNodeId` 在新文档中仍然存在，否则清空选中态。

## 9. Patch 校验管线 (Patch Validation Pipeline)

Patch 是模型候选修改的唯一载体。校验管线（全部确定性代码，无模型参与）：

1. **Schema 校验**：Patch 结构合法；操作类型在允许集合内；目标引用是合法 ID 格式。
2. **业务规则校验**：
   - Patch 不创建/删除/修改任何节点 ID；
   - 目标节点在当前文档中存在；
   - 目标节点 == 当前 `selectedNodeId`（或其内部受允许属性，以 Spec 为准）；
   - 组件类型已注册；修改的 prop 在该组件的可编辑清单内；新值类型/取值合法。
3. **Patch 边界校验**：Patch 不引用目标之外的任何节点；不引入脚本、事件处理、任意 HTML。
4. **应用到副本**：应用到文档副本，得到候选新文档。
5. **完整性校验**：见 §10。
6. **提交**：候选新文档替换当前状态，版本号递增，写 Trace。

任一环节失败：整轮拒绝，状态不变，Trace 记录失败原因。

## 10. 非目标子树完整性校验 (Non-target Subtree Integrity Verification)

- 目标：**证明**一次 Patch 只改了目标节点，其余部分零变更。
- 方法：对非目标子树做**规范化序列化**（键序稳定、空白归一）+ 哈希（或等价深比较），Patch 前后逐段比对。
- 判定：非目标节点的哈希集合在 Patch 前后必须完全一致；目标节点的 ID 集合不得增删。
- 该校验在服务端执行、自动化测试覆盖（正向：合法 Patch 通过；反向：夹带非目标修改的 Patch 被拦截），结果写入 Trace 并可在前端展示。

## 11. 模型 Provider 边界 (Model Provider Boundary)

- 统一接口：`generate(candidateRequest) → candidateOutput`，输入为结构化的意图 + 上下文，输出为结构化候选（DSL 初稿或 Patch）。
- **Mock Provider 与真实模型使用相同接口**，通过环境变量切换；Mock 用确定性规则/预置响应，保证演示路径永远可跑。
- Provider 只做"翻译"（自然语言 → 候选结构），不做"裁决"：输出一律视为不可信候选，必须走 §9 管线。
- 模型不是系统状态的事实来源；它看不到也决定不了"什么是当前页面"，每轮所需的页面状态由系统注入。
- Prompt 的 SP/UP 分层设计（哪些固定、哪些随轮次变化、缓存与成本影响）在设计文档与后续 Prompt Spec 中细化，属于关键协议，需正反向测试。

## 12. 模板推荐边界 (Template Recommendation Boundary)

- **沉淀**：从 Trace / 历史对话中提取"意图特征 → DSL 初稿"的样本，转化为模板（含意图描述、结构骨架、使用统计）。
- **推荐**：新对话首句意图与模板库匹配（规则关键词 / 简单聚类 / embedding 检索其一，最简实现优先），命中则返回模板 DSL 作为初稿起点。
- **自进化**：模板库支持新增（无匹配且完成的新对话）、合并（相似模板收敛）、淘汰（长期未被采用或质量差）；触发条件与更新策略在模板机制 Spec 中定义并记录 ADR。
- 模块边界：推荐只产出"候选初稿"，仍走与模型生成完全相同的校验管线——模板不是免检通道。
- 数据假设：第一版使用构造的模拟历史对话数据，假设记录在该 Spec 中。

## 13. 错误处理原则 (Error Handling Principles)

- 校验失败 ≠ 系统异常：它是预期路径，返回结构化拒绝原因（哪个环节、哪条规则）。
- 对用户可理解的反馈：前端把拒绝原因翻译为"这次没改成，因为……"，而不是堆栈。
- 状态一致性优先：任何失败都保证文档状态不变（先副本后提交）。
- 模型调用失败：Mock 保底 + 明确错误提示；不得静默降级为整页重生成。

## 14. 测试策略 (Testing Strategy)

- **后端 pytest**：DSL Schema 校验、Patch 管线（正向/反向）、非目标完整性校验、Provider 边界（Mock）、模板机制（沉淀/推荐/更新）、API 端点。
- **前端单元测试**：DSL 渲染、选中交互、Patch 后局部更新（不重绘整页）。
- **Gold Case**：固定输入 → 固定期望输出的端到端用例集（如咖啡店演示流），作为防漂移回归。
- **后期 Playwright**：演示闭环的浏览器级回归。
- 所有关键协议必须有正向 + 反向测试（AGENTS.md 约束 19）。

## 15. 安全边界 (Security Boundaries)

- 模型输出是不可信输入：永远不能绕过 §9 管线。
- Patch 白名单制：只允许修改"选中节点 + Schema 允许属性"，其余一律拒绝（默认拒绝，而非默认允许）。
- 无任意代码执行：系统任何位置不 `eval`、不注入 HTML 脚本、不把模型输出当代码。
- 密钥走环境变量，仓库只提交脱敏示例；Mock/真实模型由环境切换。
- 本地原型不做多用户隔离；这是已声明的非目标，不是遗漏。

## 16. 建议的仓库结构 (Suggested Repository Structure)

规划结构（仅建议，随后续 Spec 逐步创建；本轮不创建代码目录）：

```text
/
├── AGENTS.md
├── README.md
├── docs/                  # 产品、架构、术语、ADR
├── specs/                 # 任务 Spec（每份一个小任务）
├── contracts/             # DSL/Patch JSON Schema 与示例（规划）
├── frontend/              # React + TS + Vite（规划）
├── backend/               # FastAPI + Pydantic（规划）
│   ├── app/               # API、管线、Provider、模板模块
│   └── tests/             # pytest
└── data/                  # 本地 JSON：模板库、Trace、模拟历史对话、Gold Case（规划）
```

## 17. 分阶段实施顺序 (Phased Implementation Order)

建议的里程碑顺序（每步由独立 Spec 驱动，本表不是承诺，可随验收调整）：

| 里程碑 | 内容 | 产出 | 状态 |
|--------|------|------|------|
| M0 | 项目契约与文档 | AGENTS / PRODUCT / ARCHITECTURE / GLOSSARY / specs 模板 | ✅ 完成 |
| M1-01 | DSL 契约 + 校验核心 | contracts/dsl/v0.1/schema.json、Pydantic 模型、校验逻辑、pytest 用例 | ✅ 完成 |
| M1-02 | DSL 校验 API | FastAPI 应用、/health、/api/v1/dsl/validate 端点、错误分类 | ✅ 完成 |
| M1-03 | Controlled Patch 核心 | Patch 数据模型、apply_patch 引擎、contracts/patch/v0.1/schema.json、pytest 用例 | ✅ 完成 |
| M2 | 前端骨架 + 渲染 + 选中交互 | DslRenderer、节点选中、Info Panel、Vitest 用例 | ✅ 完成 |
| M3-01 | Refinement Pipeline + Mock Provider + Refine API | 后端局部精修管线、Mock Provider、POST /api/v1/dsl/refine、零变更校验 | ✅ 完成 |
| M3-02 | 前后端局部精修闭环 | 前端 API Client、useReducer 原子提交、精修面板 UI、Vite dev proxy、Playwright E2E 两轮闭环 | ✅ 完成 |
| M4-01 | 一句话生成网页初稿纵向切片 | Generation Provider 抽象、确定性 Mock 初稿模板、Generation Pipeline、POST /api/v1/dsl/generate、前端生成入口与生成→精修串联 E2E | ✅ 完成 |
| M4 | 完成 PDF 任务一：一句话生成初稿、真实模型接入、SP/UP（系统提示词/用户提示词）策略、自然语言局部精修、多类 Patch、多轮上下文 | 真实 Provider、提示词策略、自然语言指令解析、多类 Patch 操作、多轮上下文 | 进行中（M4-01 已完成） |
| M5 | 完成 PDF 任务二：模板推荐、自进化、指标、个性化、冷启动 | 模板库、沉淀/推荐/更新闭环、指标采集与展示、个性化与冷启动策略 | 待启动 |
| M6 | 完整面试交付：覆盖矩阵、设计文档、架构图、Demo 脚本、追问题库、降级预案 | 需求覆盖矩阵、设计文档、架构图、Demo 脚本、追问题库、降级预案 | 待启动 |

## 待决策项 (Open Decisions)

以下为有意暂缓的决策，本轮不做决定：

| # | 待决策项 | 为什么暂不决定 | 最晚决定时点 | 决策人 |
|---|----------|----------------|--------------|--------|
| D1 | 前端状态管理库 | **已决策（M2）**：使用 React useState 管理 selectedNodeId，不引入外部状态库。理由：当前只有单一选中态，复杂度不足以证明引入第三方库 | — | 项目所有者 |
| D2 | 真实模型供应商与具体型号 | Mock 优先策略下不影响 M1–M5；且涉及密钥与成本 | M6 开始前 | 项目所有者 |
| D3 | 是否引入 SQLite | 本地 JSON 未暴露查询瓶颈；M5 模板库规模扩大后再评估 | M5 进行中评估，M6 前落定 | 项目所有者（依 Agent 建议） |
| D4 | 双端契约类型的维护方式 | **已决策（M2）**：手写 TS 类型，JSON Schema 保持为契约事实来源。理由：组件数量有限，手写类型可读性优于自动生成，且可利用 discriminated union | — | 项目所有者 |
| D5 | embedding 检索是否引入及其依赖 | 规则/关键词匹配可能已够用；引入新依赖需审批闸门 | M5 开始前 | 项目所有者 |
