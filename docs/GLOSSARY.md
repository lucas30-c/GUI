# GLOSSARY.md — 术语表

本项目全部文档、Spec、代码注释与演示话术统一使用以下定义。术语之间不得互相矛盾；如需修改某个定义，必须同步检查引用它的文档。

## 核心概念

| 术语 | 定义 |
|------|------|
| **GenUI** | Generative UI 的简称：由模型根据用户自然语言意图生成用户界面的交互形态。本项目中特指"受控生成"——模型产出结构化 DSL/Patch，而非代码。 |
| **DSL** | Domain-Specific Language。本项目中指描述页面的受控 JSON 结构：固定组件类型、受约束的 props、树形层级。模型只能产出 DSL 范围内的内容。 |
| **DSL Document** | 一棵完整的 DSL Node 树（根为 `Page`），是页面状态的**唯一事实来源**。每次提交产生新版本。 |
| **DSL Node** | DSL Document 中的单个节点，包含 `id`、`type`、`props`、`children`（仅容器类）。 |
| **Stable Node ID** | 节点的稳定、全局唯一标识。由系统（非模型）在节点创建时分配，生命周期内不变；Patch 不得创建、删除、覆盖或修改它；它是一切编辑操作的唯一锚点。 |
| **Component Registry** | 组件注册表：前后端共享的固定组件清单及各组件的 props 约束。第一版为 `Page / Section / Heading / Text / Button / Image / Card / Form / Input`。未注册类型一律被拒绝。 |

## 编辑与选中

| 术语 | 定义 |
|------|------|
| **Selected Node** | 用户当前在页面上选中的那个 DSL Node。以 `selectedNodeId` 形式保存在编辑会话中，属于编辑上下文，不属于 DSL 节点内容。 |
| **Patch** | 一次局部修改请求的结构化载体，由后端产出、经校验后应用。是模型表达修改意图的**唯一**方式。 |
| **Controlled Patch** | 一种结构化、确定性的 DSL 文档修改方式，仅允许更新已有节点的 props（不创建/删除节点、不修改 ID）。 |
| **Atomic Patch** | 具有原子性的 Patch：所有操作均成功且通过最终校验才生效；任一步骤失败则整体回滚，不产生部分修改。 |
| **Source Document** | Patch 应用前的输入 DSL 文档（原始文档），不会被 Patch 过程修改。 |
| **Patched Document** | Patch 成功应用后产生的新 DSL 文档，已通过完整校验。 |
| **Patch Operation** | Patch 中的单个操作（如修改某 prop 的值）。每个操作必须指向目标节点的受允许属性路径。 |
| **Target Node** | Patch 的作用对象，必须等于当前 Selected Node（或 Spec 明确允许的其内部属性）。 |
| **Non-target Node** | 文档中除 Target Node 之外的所有节点。Patch 前后它们的规范化哈希必须完全一致（零变更）。 |

## 模型与校验

| 术语 | 定义 |
|------|------|
| **Candidate Output** | Model Provider 返回的结构化候选结果（DSL 初稿或 Patch）。是不可信输入，只有通过全部校验后才能成为状态。 |
| **Validation Pipeline** | 校验管线：Schema Validation → Business Rule Validation → Patch Boundary Validation → 应用到副本 → Integrity Check → Commit。任一环节失败即整轮拒绝。 |
| **Integrity Check** | 非目标子树完整性校验：对非目标节点做规范化序列化 + 哈希（或等价深比较），证明 Patch 只改了 Target Node。 |
| **Model Provider** | 模型能力的统一接口：输入结构化意图与上下文，输出 Candidate Output。不负责裁决，只负责"翻译"。 |
| **RefinementProvider** | Model Provider 的精修专用 Protocol（`typing.Protocol`）。定义 `async def generate_patch(context: RefinementContext) -> dict`，返回候选 Patch dict。 |
| **RefinementContext** | 传递给 RefinementProvider 的受控上下文数据类。包含 instruction、selected_node_id、selected_node_type、selected_node_props（深拷贝）、document_version。不含完整文档（最小权限原则）。 |
| **Mock Provider** | Model Provider 的确定性实现：用规则/预置响应模拟模型行为，与真实模型同接口，保证无外部依赖的演示路径。 |
| **Refinement Pipeline** | 无状态异步编排函数 `refine()`，10 步确定性流程：校验指令 → 校验源文档 → 查找节点 → 构造上下文 → 调用 Provider → 校验候选结构 → 边界检查 → 应用 Patch → 完整性验证 → 返回结果。 |
| **Trace** | 一轮对话的完整记录：输入、候选输出、各环节校验结果、应用结果、指标数据点。用于排错、指标计算与模板沉淀。 |

## 模板与指标

| 术语 | 定义 |
|------|------|
| **Template** | 从历史对话/生成结果中沉淀的可复用单元：意图特征 + DSL 结构骨架 + 使用统计。作为新对话的候选初稿起点，仍需通过完整校验管线。 |
| **Template Adoption** | 模板被采纳：新对话以推荐模板为起点生成了初稿（区别于“被推荐但未采用”）。是计算模板推荐采用率的分子。 |
| **Conversation Round** | 一轮对话：用户一次输入（需求或精修指令）+ 系统一次响应。是北极星指标（中位对话轮次）的计数单位。 |
| **Gold Case** | 黄金用例：固定输入 → 固定期望输出的端到端测试用例（如咖啡店演示流），用于防漂移回归。 |

## 前端渲染

| 术语 | 定义 |
|------|------|
| **DslRenderer** | React 组件，根据节点 type 递归渲染整棵 DSL 树为语义 HTML。 |
| **selectedNodeId** | 前端状态，跟踪当前被选中的 DSL 节点；永远不写入 DSL。 |
| **Style Mapper** | 纯函数，将 DSL Style 对象转换为 React CSSProperties，仅允许白名单字段通过。 |
| **Info Panel** | 只读侧边栏，展示当前选中节点的 id、type 和 props。 |

## 精修 API

| 术语 | 定义 |
|------|------|
| **Refine Endpoint** | `POST /api/v1/dsl/refine`，局部精修 API。接收当前文档、selectedNodeId 和自然语言指令，通过 Refinement Pipeline 返回已验证的新文档和 Patch。 |
| **Candidate Boundary Violation** | 候选 Patch 中存在指向非 selectedNodeId 的操作，被边界检查拦截。 |
| **Non-target Mutation** | 应用 Patch 后，非目标节点发生了意外变化，被完整性校验发现。 |

## 前端精修闭环

| 术语 | 定义 |
|------|------|
| **API Client（refineNode）** | 前端唯一的精修请求函数。发出 `POST /api/v1/dsl/refine`，把网络 JSON 当作 `unknown`，只经类型守卫收窄，返回判别联合 `RefineClientResult`，任何路径都不向调用者抛异常。 |
| **RefineClientResult** | API Client 的返回联合类型，按 `kind` 判别：`success`（结构检查通过）、`server`（服务端业务失败，已净化）、`local`（前端侧失败）。 |
| **本地错误码（Local Error Code）** | 前端自行判定的三类失败：`network_error`（请求未发出或连接失败）、`invalid_json`（响应体不是合法 JSON）、`invalid_response`（响应结构或 HTTP 状态与 success 不一致）。消息为前端固定文案，不回显请求/响应内容与异常堆栈。 |
| **Envelope 一致性检查** | HTTP 状态与 `success` 字段必须一致：2xx 对应 `true`、非 2xx 对应 `false`；两者矛盾或 `success` 缺失/非 boolean 一律判为 `invalid_response`。 |
| **RefinementIntegrity** | 响应中的完整性声明：`selectedNodeId` + `nonTargetNodesUnchanged`。API Client 只校验其为 boolean；`false` 会被放行到提交层再拒绝。 |
| **VerifiedRefinementIntegrity** | `nonTargetNodesUnchanged` 已收窄为字面量 `true` 的完整性声明。只能通过真实条件检查获得，不得用类型断言伪造。 |
| **提交层完整性检查** | 提交前的三道额外校验：`nonTargetNodesUnchanged === true`、`integrity.selectedNodeId` 等于提交快照、返回文档中确实存在该节点。任一不通过即拒绝本轮结果。 |
| **原子提交（REFINE_SUCCESS）** | 唯一写入 `currentDocument` / `lastPatch` / `lastIntegrity` / `lastSuccess` 的 action。全部检查通过后一次 dispatch 完成，不存在"文档已更新但结果面板未更新"的中间态。 |
| **提交快照（Submit Snapshot）** | 发起请求时捕获的 `document` / `selectedNodeId` / `instruction`。响应校验与提交全程使用快照值，不使用响应到达时的当前 state。 |
| **旧响应丢弃（Stale Response Discard）** | 请求进行中用户切换了选中节点时，返回的旧响应被丢弃：不触发原子提交、不覆盖当前选择与上一轮结果，仅结束 loading。判定依据是与选择交互同步写入的最新选中节点引用。 |
