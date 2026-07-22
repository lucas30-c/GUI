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
| **Mock Provider** | Model Provider 的确定性实现：用规则/预置响应模拟模型行为，与真实模型同接口，保证无外部依赖的演示路径。 |
| **Trace** | 一轮对话的完整记录：输入、候选输出、各环节校验结果、应用结果、指标数据点。用于排错、指标计算与模板沉淀。 |

## 模板与指标

| 术语 | 定义 |
|------|------|
| **Template** | 从历史对话/生成结果中沉淀的可复用单元：意图特征 + DSL 结构骨架 + 使用统计。作为新对话的候选初稿起点，仍需通过完整校验管线。 |
| **Template Adoption** | 模板被采纳：新对话以推荐模板为起点生成了初稿（区别于"被推荐但未采用"）。是计算模板推荐采用率的分子。 |
| **Conversation Round** | 一轮对话：用户一次输入（需求或精修指令）+ 系统一次响应。是北极星指标（中位对话轮次）的计数单位。 |
| **Gold Case** | 黄金用例：固定输入 → 固定期望输出的端到端测试用例（如咖啡店演示流），用于防漂移回归。 |
