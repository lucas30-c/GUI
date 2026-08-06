# Spec 007 — 一句话生成网页初稿纵向切片（M4-01）

## 元信息

| 字段 | 值 |
|------|------|
| Spec 编号 | 007 |
| 标题 | 一句话生成网页初稿纵向切片（M4-01） |
| 前置 Spec | 005（Refinement Pipeline + Mock Provider + API）、006（前端局部精修闭环） |
| 前置条件 | M3-02 实现完成并已提交；后端 310 测试、前端 207 测试、E2E 1 条全部通过；基线 HEAD = `fc720e9` |

## 背景与路线图纠正 (Context & Roadmap Correction)

### 背景

- M1 已交付 DSL v0.1 契约与校验（Spec 001/002）、受控 Patch 核心（Spec 003）。
- M2 已交付前端 DSL Renderer 与节点选中（Spec 004）。
- M3 已交付后端精修管线 + Mock Provider + `POST /api/v1/dsl/refine`（Spec 005），以及前端局部精修闭环 + E2E（Spec 006）。
- 目前前端的 `currentDocument` 初始值**硬编码为 Gold Case**（`examples/dsl/coffee-shop-landing.json`），用户无法从一句自然语言需求得到初稿。PRODUCT.md 的 F1（一句话生成网页初稿）尚未有任何实现。
- 本轮（M4-01）建立"**一句话 → 初稿 DSL → 渲染 → 继续局部精修**"的最小完整纵向切片：新增初稿生成 API 与确定性 Mock Generation Provider，前端新增生成入口并与既有 M3-02 精修闭环无缝衔接。

### 路线图纠正（实施本 Spec 时必须同步落地）

`README.md` 与 `docs/ARCHITECTURE.md` §17 当前的里程碑表写的是「M4 = 多轮会话与指标、M5 = 模板推荐与自进化、M6 = 真实模型接入 + 演示打磨」，与最新路线不一致。本 Spec 记录最新路线如下，并规定：**实施本轮时必须同步修正上述两处里程碑表**（属于 Allowed Files 中的允许修改项）：

| 里程碑 | 最新定义 |
|--------|----------|
| M4 | 完成 PDF 任务一：一句话生成初稿、真实模型接入、SP/UP（系统提示词/用户提示词）策略、自然语言局部精修、多类 Patch、多轮上下文 |
| M5 | 完成 PDF 任务二：模板推荐、自进化、指标、个性化、冷启动 |
| M6 | 完整面试交付：覆盖矩阵、设计文档、架构图、Demo 脚本、追问题库、降级预案 |

M4-01 在两处文档中统一标记为「**一句话生成网页初稿纵向切片**」。

## 目标 (Goal)

M4-01 的目标链路，共 12 点：

1. 前端提供 prompt 输入区，用户输入**一句自然语言需求**（如"我要一个咖啡店的落地页"）。
2. 前端调用新的初稿生成 API：`POST /api/v1/dsl/generate`，请求体仅含 `{ prompt }`。
3. 后端经统一的 **Generation Provider 抽象**（`generation/base.py` 的 Protocol）生成候选 DSL；Provider 输出一律视为**不可信候选**。
4. M4-01 使用**确定性 Mock Generation Provider**：基于关键词映射到三套独立内置模板（咖啡店落地页 / 活动报名表单页 / 产品介绍落地页），无法识别时返回明确安全失败，不静默兜底。
5. 候选 DSL 必须通过现有 DSL Schema 校验 + 业务规则校验：Generation Pipeline 直接调用 `genui_api.contracts.validation.validate_dsl_document(data: dict) -> DslDocument`（含 Pydantic 结构校验与业务规则：ID 全局唯一、root 必须 Page、嵌套矩阵），**不复制任何校验规则**。
6. 校验通过后才返回完整 `DslDocument`（`model_dump(mode="json")` 序列化）；校验失败映射为明确错误码与 HTTP 状态。
7. 前端**只接受后端确认后的 `document`**：生成 API Client 在响应边界以 `unknown` 起步、类型守卫收窄；前端不本地拼装、不本地修改 DSL。
8. 生成成功后新初稿**原子替换** `currentDocument`，同时清空旧 `selectedNodeId` 及与旧 document 绑定的 `lastPatch` / `lastIntegrity` / `lastSuccess` / `error`，并清空 `instruction` / `prompt` / `generateError`（单次 dispatch 原子设置 9 项，见 DD-18）。
9. 生成失败时保留当前页面：`currentDocument` 与全部精修成功状态不被污染，仅更新生成侧的 loading / error。
10. 生成期间与精修期间的并发互斥有确定性规则（生成中禁精修提交、精修中禁生成提交），事实来源是 `generateInFlightRef` 与既有 `inFlightRef` 组成的**双同步 in-flight 守卫**，防止同一同步窗口内交叉提交。
11. 生成成功后 **M3-02 精修闭环继续完整可用**：对新初稿中的节点选中并精修，链路与 Spec 006 行为一致（集成测试 + E2E 断言）。
12. 新增 Playwright E2E 验证"**生成初稿 → 选择节点 → 局部精修**"全链路串联；既有 E2E 不修改且继续通过。

## 范围外 / 非目标 (Out of Scope)

以下内容**明确不属于**本轮范围：

- 不接入真实模型（OpenAI / Anthropic / 任何 LLM API）；
- 不保存、不读取、不传输任何真实 API Key；
- 不实现完整 SP/UP（系统提示词 / 用户提示词）策略；
- 不实现自然语言 Patch（自由自然语言精修仍留在 M4 后续切片）；
- 不扩展 Patch v0.2（不新增 `add` / `remove` / `move` 操作）；
- 不实现模板推荐（属 M5）；
- 不实现指标 / 埋点 / 评估体系（属 M5）；
- 不引入数据库 / 持久化；
- 不引入 embedding / 向量检索；
- 不实现任意 HTML / React / JavaScript 代码生成（DSL 是唯一生成产物）；
- 不实现多轮生成上下文 / 会话历史；
- 不修改 DSL v0.1 / Patch v0.1 契约与 Schema；
- 不修改既有精修链路（`refinement/**`、`provider/**`、`/api/v1/dsl/refine` 行为）。

## 已拍板的设计决策 (Design Decisions)

| # | 决策 | 理由 |
|---|------|------|
| DD-1 | 新端点 `POST /api/v1/dsl/generate`，复用 refine 端点的**手动请求处理模式**：接收原始 `Request`、Content-Type 前缀检查（`application/json`，忽略大小写）、手动 JSON 解析、`GenerateRequest.model_validate`、`openapi_extra` 声明 requestBody | 与 `/api/v1/dsl/refine` 的既有实现模式完全一致，415/400 分类行为可预测且已被测试验证 |
| DD-2 | 请求模型 `GenerateRequest`：仅 `prompt: str` 一个字段，`model_config = ConfigDict(extra="forbid")` | 未知字段必须被拒绝（延续全仓库 extra=forbid 纪律）；prompt 无驼峰/下划线差异，不需要 alias |
| DD-3 | 响应 envelope 与 refine 一致：成功 `{success: true, document}`；失败 `{success: false, error: {code, message, issues}}`（复用 `api/schemas.py` 现有 `ValidationErrorDetail` / `ValidationIssue`）。生成响应**不含** `patch` / `integrity` 字段 | 初稿生成是整文档产出，不存在"局部修改的完整性证明"语义；envelope 风格统一降低前端处理成本 |
| DD-4 | HTTP 状态码映射见"错误分类映射"表；生成侧新增错误码 `invalid_prompt` / `unrecognized_intent` / `invalid_generated_document`，复用既有命名 `unsupported_media_type` / `invalid_json` / `invalid_request_structure` / `provider_error` / `internal_error`；在 `routes.py` 中新增独立映射常量 `_GENERATION_ERROR_HTTP_MAP`，**不修改**既有 `_ERROR_HTTP_MAP` | 生成与精修的错误码集合不同；独立常量避免精修链路回归 |
| DD-5 | prompt 规则：`trim` 后长度 ≥ 1 且 ≤ 500 字符（`MAX_PROMPT_LENGTH = 500`，前后端同值）。结构问题（缺字段 / 非字符串 / 多余字段）由 Pydantic 拒绝 → `invalid_request_structure`；trim 后为空或超长由 Pipeline 拒绝 → `invalid_prompt`。**后端是最终事实来源**；前端按钮 disabled 仅为体验优化 | 结构错误与业务规则错误分离，错误码语义清晰；与 instruction 的前后端分工模式（DD-7@006）一致 |
| DD-6 | `GenerationProvider` Protocol 定义于 `backend/src/genui_api/generation/base.py`：`async def generate_draft(self, prompt: str) -> dict`；返回值为**不可信候选 dict** | 与 `provider/base.py` 的 `RefinementProvider.generate_patch(context) -> dict` 既有风格一致：Protocol + async + 返回原始 dict，由管线负责全部校验 |
| DD-7 | `UnrecognizedIntentError` 异常定义于 `generation/base.py`，属共享生成契约：任何 Provider 均可抛出以显式表达"无法把 prompt 映射为初稿"；Pipeline 将其映射为 422 `unrecognized_intent`；Provider 抛出的**其他任何异常**一律映射为 502 `provider_error`（固定净化文案） | "无法识别"是用户输入问题（4xx），Provider 崩溃是上游问题（5xx）；类型化异常使二者可确定性区分 |
| DD-8 | Generation Pipeline 位于 `backend/src/genui_api/generation/pipeline.py`：`async def generate_document(prompt, provider) -> DslDocument`，按固定 6 步顺序执行（见"Generation Pipeline"章节）；错误以 `GenerationError(code, message, issues)` 抛出（与 `refinement/pipeline.py` 的 `RefinementError` 模式一致）；候选必须经 `validate_dsl_document` 才能返回 | 单一事实来源；prompt 校验先于 Provider 调用，非法输入不触达 Provider |
| DD-9 | Mock 意图映射：对 prompt 做 `strip()` + `lower()` 预处理后**子串匹配**，三组关键词按**固定优先级**（咖啡店 > 活动报名 > 产品介绍）逐组检查，组内任一关键词命中即选定该组模板并停止；全部未命中 → 抛 `UnrecognizedIntentError`，**不静默兜底** | 子串 + 固定优先级 = 完全确定性、可穷举测试；静默兜底会掩盖意图理解缺陷并让用户拿到货不对板的页面 |
| DD-10 | 三套模板为**独立内置定义**：`generation/templates.py` 中的模块级 dict 常量 `TEMPLATE_COFFEE_SHOP` / `TEMPLATE_EVENT_SIGNUP` / `TEMPLATE_PRODUCT_INTRO`；与 Gold Case 结构同风格但**内容独立**，不得直接返回或复制 Gold Case 的文案内容 | 模板须证明生成链路产出的是"新文档"而非现有示例的搬运；三套模板同时给意图映射提供可区分的断言锚点 |
| DD-11 | 节点 ID 策略：模板自带**语义化静态 ID**（`hero.title` 风格，满足 NodeId 正则 `^[a-z][a-z0-9]*(?:[.\-][a-z0-9]+)*$`），同一模板每次生成 ID 完全相同。**不使用随机 ID**：ID 唯一性约束仅在单文档内生效，无跨文档随机化需求；随机 ID 会破坏确定性（测试不可复现、E2E 无法定位节点、diff 不稳定），且对精修定位没有任何收益 | 确定性优先（AGENTS.md 纪律）；静态 ID 让"生成 → 选择 → 精修"链路可用稳定选择器断言 |
| DD-12 | 模板克隆：`generate_draft` 每次调用返回 `copy.deepcopy(模板常量)`，禁止直接返回模块级常量或其浅拷贝 | 候选 dict 会进入校验与序列化流程，共享可变对象会导致跨请求污染；配正反测试（返回值独立 + 污染返回值后再次生成仍与首次一致） |
| DD-13 | Provider 注入：`get_generation_provider() -> GenerationProvider` 定义于 `api/routes.py`（默认返回 `MockGenerationProvider()`）；`main.py` 的 `create_app` 增加可选参数 `generation_provider`，通过 `dependency_overrides[get_generation_provider]` 注入 | 与既有 `get_provider` / `refinement_provider` 完全同模式，测试可注入恶意 Provider 验证信任边界 |
| DD-14 | 前端生成 API Client **新建** `frontend/src/api/generate.ts`；类型增量写入既有 `frontend/src/api/types.ts`；复用 `refine.ts` 已导出的 `isRecord` / `isDslDocumentShape` 守卫与 `types.ts` 的 `RefineLocalErrorCode`（三类本地错误码语义完全相同），**不修改** `frontend/src/api/refine.ts` | 守卫已是导出函数，直接 import 即可；避免重复实现导致两套守卫漂移 |
| DD-15 | 生成 Client 净化模式与 M3-02 相同：响应一律 `unknown` 起步、守卫收窄、HTTP 状态与 `success` discriminant 一致性检查、三类本地错误（`network_error` / `invalid_json` / `invalid_response`）、丢弃响应中的额外字段、禁止 `any` 与 `as` 类型断言绕过 | 边界安全纪律延续；生成响应同样是不可信网络数据 |
| DD-16 | 前端**永不**本地拼装或修改 DSL：`currentDocument` 的新值只能来自 refine / generate 两个 API 的、通过运行时检查的 `document` | 后端是 DSL 合法性的唯一事实来源（DD-2@006 延续） |
| DD-17 | 前端状态迁移：`RefinementState` 新增 `prompt: string`、`generateLoading: boolean`、`generateError: GenerateServerError \| GenerateLocalError \| null` 三个字段；新增 5 个 action（`SET_PROMPT` / `GENERATE_START` / `GENERATE_SUCCESS` / `GENERATE_FAILURE` / `GENERATE_END`）与既有 6 个精修 action 并存。生成与精修的 loading / error **分离**（不复用 `loading` / `error` 字段） | 两条链路状态互不串扰：生成失败不得污染精修错误面板，反之亦然；单 reducer 保持原子提交能力 |
| DD-18 | `GENERATE_SUCCESS` 由**单次 dispatch** 原子设置 9 项：`currentDocument` = 响应 document、`selectedNodeId` = null、`lastPatch` = null、`lastIntegrity` = null、`lastSuccess` = null、`error` = null、`instruction` = ''、`prompt` = ''、`generateError` = null。**instruction 拍板清空**：旧 instruction 针对旧文档的选中节点撰写，换文档后保留无意义且有误提交风险；`prompt` 清空：本轮 prompt 已被消费（类比 DD-14@006）；`generateError` 显式置 null：`GENERATE_SUCCESS` 本身必须保证完整成功状态，不能隐含依赖 `GENERATE_START` 已清空 `generateError` | 旧成功状态（patch / integrity / lastSuccess）均与旧 document 绑定，新初稿下全部失效；原子清空防止 UI 展示与新文档矛盾的陈旧信息 |
| DD-19 | `GENERATE_SUCCESS` dispatch 之前，在**同一同步代码路径**中先执行 `latestSelectedNodeIdRef.current = null`，再 dispatch（与 `handleSelect` 中"先写 ref 再 dispatch"的既有模式一致） | ref 是精修链路旧响应竞态检查的事实来源（DD-23@006），必须与 state 中的 `selectedNodeId = null` 同步重置，否则换文档后精修快照校验会引用旧文档的节点 ID |
| DD-20 | 并发互斥拍板：**生成进行中禁用精修提交**（按钮 disabled + 快捷键拦截），**不禁用节点选择**；**精修进行中禁用生成提交**。互斥的**事实来源是双同步 in-flight ref**：新增 `generateInFlightRef` 负责生成侧同步在途状态，既有 `inFlightRef` 负责精修侧同步在途状态。生成提交 handler 必须同步检查 `generateInFlightRef.current`、`inFlightRef.current` 与 prompt 合法性条件；精修提交 handler 必须同步检查 `inFlightRef.current`、`generateInFlightRef.current` 与既有提交条件。`loading` / `generateLoading` 继续用于 reducer 状态、按钮 disabled 与 loading UI，但 React state 更新在事件处理器内不同步生效，**不能**作为互斥事实来源 | 两个请求都可能整文档替换 `currentDocument`，并行会产生不可确定的覆盖顺序；仅靠 state 存在同一同步事件循环窗口内交叉提交的可能，双 ref 同步守卫可确定性消除该窗口；节点选择是纯本地操作，无需禁用 |
| DD-21 | 生成请求并发模型拍板：M4-01 **不允许两个生成请求并发存在**。`generateInFlightRef` 同步阻止重复生成提交，`inFlightRef` 与 `generateInFlightRef` 共同阻止生成与精修交叉并发。因此系统中任意时刻至多存在一个在途生成请求，**不存在"旧生成响应覆盖新生成响应"的合法状态**，无需请求序号或响应丢弃机制；本轮不引入 latest-wins、取消请求或可抢占生成语义 | 单请求互斥是最简单、可测试、可回滚的并发模型（AGENTS.md 约束 20）；为不可达的并发场景引入序号机制会产生真实流程中无法触达的死代码与不可达测试分支 |
| DD-22 | UI：页面**顶部新增生成区**——单行 `<input type="text">`（prompt 上限 500 字符，单行足够）+「生成初稿」按钮；`Enter` 直接提交（与精修 textarea 的 `Ctrl/Cmd+Enter` 语义区分，二者控件形态不同不会混淆）；生成错误显示在生成区下方独立错误面板 | 布局最小改动：右侧 320px 面板继续归精修；生成是全局操作放顶部符合直觉 |
| DD-23 | **零新增依赖**（前后端均不引入任何新依赖）；不修改 `frontend/vite.config.ts`（proxy 已覆盖 `/api` 全前缀）、`frontend/playwright.config.ts`（`testDir` 已覆盖 `e2e/` 新增文件、webServer 已就绪）、`frontend/package.json` / `package-lock.json`、`backend/pyproject.toml` | 现有基础设施完全够用；依赖与配置零变更使回归面最小 |
| DD-24 | 里程碑表修正（README.md + docs/ARCHITECTURE.md §17）随本轮实施一并落地，按"背景与路线图纠正"章节的表格执行 | 文档与实际路线不一致会误导后续 Spec；修正属于本轮 Allowed Files 内的最小文档变更 |

## 后端 API 契约 (Backend API Contract)

### 端点

`POST /api/v1/dsl/generate`

### 请求模型（`api/schemas.py` 新增）

```python
class GenerateRequest(BaseModel):
    """初稿生成请求。"""
    model_config = ConfigDict(extra="forbid")

    prompt: str
```

- prompt 的 trim 非空与长度上限检查在 Pipeline 层执行（DD-5），Pydantic 只负责结构（字段存在、为字符串、无未知字段）。

### 响应模型（`api/schemas.py` 新增）

```python
class GenerateSuccess(BaseModel):
    """初稿生成成功响应。"""
    success: Literal[True]
    document: dict          # DslDocument.model_dump(mode="json")


class GenerateFailure(BaseModel):
    """初稿生成失败响应。"""
    success: Literal[False]
    error: ValidationErrorDetail   # 复用既有模型：code / message / issues
```

### 错误分类映射

| 场景 | HTTP 状态码 | error.code |
|------|-------------|-----------|
| Content-Type 非 JSON（含缺失） | 415 | `unsupported_media_type` |
| 空 body / JSON 语法错误 | 400 | `invalid_json` |
| 请求结构非法（缺 `prompt` / 非字符串 / 未知字段） | 422 | `invalid_request_structure` |
| prompt trim 后为空，或 trim 后长度 > 500 | 422 | `invalid_prompt` |
| Provider 抛 `UnrecognizedIntentError`（意图无法识别） | 422 | `unrecognized_intent` |
| Provider 抛出其他任何异常 | 502 | `provider_error` |
| Provider 候选非 dict，或未通过 `validate_dsl_document`（结构 / duplicate_id / invalid_nesting / invalid_root） | 502 | `invalid_generated_document` |
| 未预期内部错误（安全兜底） | 500 | `internal_error` |

映射常量：`routes.py` 新增 `_GENERATION_ERROR_HTTP_MAP`（独立于既有 `_ERROR_HTTP_MAP`，后者不修改）。

### 安全要求

- 错误响应不含 traceback、文件路径、环境变量；
- 错误响应不回显完整 prompt 原文与完整候选文档内容（`issues` 仅含净化后的 `path` / `code` / `message`）；
- 500 / 502 `provider_error` 的 message 为固定通用文案。

## Generation Provider 契约 (Generation Provider Contract)

文件：`backend/src/genui_api/generation/base.py`

```python
class UnrecognizedIntentError(Exception):
    """Provider 无法把 prompt 映射为任何初稿意图时抛出（映射为 422 unrecognized_intent）。"""


class GenerationProvider(Protocol):
    """初稿生成 Provider 抽象。返回值一律视为不可信候选。"""

    async def generate_draft(self, prompt: str) -> dict:
        """根据一句自然语言需求生成候选 DSL 文档（原始 dict，未经任何校验）。"""
        ...
```

约束：

- Provider 输出**永远不可信**：Pipeline 必须对候选执行完整 Schema + 业务校验后才能进入响应；
- 禁止在路由或 Pipeline 中对候选做类型断言或选择性信任；
- 注入方式与精修 Provider 完全一致：`get_generation_provider()` 定义于 `api/routes.py`，`create_app(refinement_provider=None, generation_provider=None)` 通过 `dependency_overrides` 覆盖（DD-13）。

## Generation Pipeline

文件：`backend/src/genui_api/generation/pipeline.py`

入口：`async def generate_document(prompt: str, provider: GenerationProvider) -> DslDocument`

失败以 `GenerationError(code, message, issues)` 抛出（结构与 `refinement/pipeline.py` 的 `RefinementError` 一致），路由层查 `_GENERATION_ERROR_HTTP_MAP` 转 HTTP 响应。

固定 6 步执行顺序：

| 步 | 动作 | 失败错误码（HTTP） |
|----|------|--------------------|
| 1 | `trimmed = prompt.strip()`；若为空 → 拒绝 | `invalid_prompt`（422） |
| 2 | 若 `len(trimmed) > 500`（`MAX_PROMPT_LENGTH`）→ 拒绝；恰好 500 字符合法 | `invalid_prompt`（422） |
| 3 | `candidate = await provider.generate_draft(trimmed)`（传入 **trim 后**的 prompt）；捕获 `UnrecognizedIntentError` → 拒绝 | `unrecognized_intent`（422） |
| 4 | 步 3 中 Provider 抛出**其他任何异常** → 拒绝（固定净化文案，不含异常原文） | `provider_error`（502） |
| 5 | `candidate` 非 dict → 拒绝 | `invalid_generated_document`（502） |
| 6 | `validate_dsl_document(candidate)`；`DslValidationError` → 拒绝（issues 保留校验器返回的 `path` / `code` / `message` 明细）；通过则返回 `DslDocument` | `invalid_generated_document`（502） |

保证：

- 步 1/2 失败时 Provider **不被调用**（正反测试验证）；
- Pipeline 不复制任何 DSL 校验规则，唯一校验入口是 `validate_dsl_document`；
- 路由层用 `DslDocument.model_dump(mode="json")` 序列化成功响应的 `document`。

## Mock Generation Provider

文件：`backend/src/genui_api/generation/mock.py`（`MockGenerationProvider`），模板常量位于 `backend/src/genui_api/generation/templates.py`。

### 意图映射规则（确定性，写死）

预处理：`normalized = prompt.strip().lower()`（大小写不敏感；中文关键词不受 lower 影响）。

按下表**优先级顺序**逐组检查，组内任一关键词是 `normalized` 的**子串**即命中该组并停止：

| 优先级 | 意图 | 关键词（子串匹配） | 模板常量 |
|--------|------|--------------------|----------|
| 1 | 咖啡店落地页 | `咖啡`、`coffee` | `TEMPLATE_COFFEE_SHOP` |
| 2 | 活动报名表单页 | `报名`、`表单`、`活动`、`signup`、`form`、`event` | `TEMPLATE_EVENT_SIGNUP` |
| 3 | 产品介绍落地页 | `产品`、`介绍`、`落地页`、`product`、`landing` | `TEMPLATE_PRODUCT_INTRO` |

- 多组同时命中按优先级取先者：如「咖啡产品介绍页」命中优先级 1，返回咖啡店模板；
- 全部未命中：抛 `UnrecognizedIntentError` → 422 `unrecognized_intent`（DD-9，不静默兜底、不返回任何默认模板）；
- 每次命中后返回 `copy.deepcopy(模板常量)`（DD-12）。

### 模板定义要求（三套均须满足）

通用要求：

- 每套模板是完整合法的 DSL v0.1 文档 dict（`version: "0.1"`、root 为 Page、通过 `validate_dsl_document`）；
- 节点 ID 语义化、静态、文档内全局唯一，满足 NodeId 正则（DD-11）；root 节点 `id` 统一为 `page`；
- **内容独立于 Gold Case**：不得整体复制 `examples/dsl/coffee-shop-landing.json`；与 Gold Case 同 ID 的节点（如 `hero.title`）文案必须不同；
- 每套模板含 ≥ 1 个可精修文本节点（Heading / Text / Button），供"生成 → 精修"串联；
- 仅使用九种既有组件，遵守嵌套矩阵（Input 必须在 Form 内；Form 子节点仅 Input / Button / Text / Heading）。

各模板最小结构（实现可在此之上补充内容，但下列锚点节点必须存在）：

| 模板 | 必含锚点节点（id → type） | 结构要求 |
|------|---------------------------|----------|
| `TEMPLATE_COFFEE_SHOP` | `hero.title` → Heading、`hero.subtitle` → Text | ≥ 2 个 Section（hero + 菜单/联系区）；`hero.title` 文案与 Gold Case 的 `hero.title` 不同 |
| `TEMPLATE_EVENT_SIGNUP` | `intro.title` → Heading、`signup.form` → Form、`signup.form.name` → Input、`signup.form.email` → Input、`signup.form.submit` → Button | Form 内 ≥ 2 个 Input + 1 个提交 Button，全部 Input 位于 Form 内 |
| `TEMPLATE_PRODUCT_INTRO` | `hero.title` → Heading、`hero.tagline` → Text | ≥ 2 个 Section（hero + 特性区，特性区含 ≥ 2 个 Card） |

确定性保证：同一 prompt 多次生成，返回文档逐字段相等；不引入时间戳、随机数、计数器。

## 前端 API 契约 (Frontend API Contract)

### 类型增量（写入既有 `frontend/src/api/types.ts`）

```typescript
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
```

### API Client（新建 `frontend/src/api/generate.ts`）

- 导出 `GENERATE_ENDPOINT = '/api/v1/dsl/generate'`、`generateDraft(request: GenerateRequest, fetcher: Fetcher = fetch): Promise<GenerateClientResult>`；
- 复用 `refine.ts` 已导出的 `isRecord` / `isDslDocumentShape` 与 `Fetcher` 类型（DD-14）；本地错误文案为 generate 侧自有固定文案常量（不复用 refine 的 `LOCAL_ERROR_MESSAGES` 文案对象，避免语义混淆，但错误码类型复用）；
- 函数**不抛异常**，一切失败以返回值表达。

最小运行时响应检查（G-1 ~ G-7，全部在 API Client 层）：

| # | 检查 | 失败结果 |
|---|------|----------|
| G-1 | `fetcher` 抛出异常（网络失败） | `{ kind: "local", code: "network_error" }` |
| G-2 | 响应体 JSON 解析失败 | `{ kind: "local", code: "invalid_json" }` |
| G-3 | 响应体非对象，或 `success` 字段非 boolean | `{ kind: "local", code: "invalid_response" }` |
| G-4 | HTTP 状态与 envelope 不一致：`res.ok && success !== true`，或 `!res.ok && success !== false` | `{ kind: "local", code: "invalid_response" }` |
| G-5 | `success === true` 但 `document` 未通过 `isDslDocumentShape` | `{ kind: "local", code: "invalid_response" }` |
| G-6 | `success === true` 且 G-3 ~ G-5 通过 → 仅提取 `document`，丢弃其余字段 | `{ kind: "success", document }` |
| G-7 | `success === false` → 净化提取 `error.code` / `error.message`（非法时用固定文案）/ `error.issues`（缺失或非法时 `[]`），丢弃其余字段 | `{ kind: "server", code, message, issues }` |

禁止：`any`、`as GenerateSuccess` 等类型断言绕过、把响应原文写入错误 message。

## 前端状态迁移与竞态 (Frontend State & Race Protection)

### 状态增量（`frontend/src/App.tsx`）

`RefinementState` 在既有 8 个字段之上新增：

```typescript
prompt: string;                // 生成输入框内容，初始 ''
generateLoading: boolean;      // 生成请求进行中，初始 false
generateError: GenerateServerError | GenerateLocalError | null;   // 初始 null
```

新增常量 `export const MAX_PROMPT_LENGTH = 500`（与后端 `MAX_PROMPT_LENGTH` 同值，与既有 `MAX_INSTRUCTION_LENGTH` 并列）。

### 新增 action（与既有 6 个并存，既有分支语义不变）

| action | 语义 |
|--------|------|
| `SET_PROMPT` | 更新 `prompt`（受控输入） |
| `GENERATE_START` | `generateLoading = true`，清空 `generateError` |
| `GENERATE_SUCCESS` | **单次 dispatch 原子设置 9 项**：`currentDocument` = 响应 document、`selectedNodeId` = null、`lastPatch` = null、`lastIntegrity` = null、`lastSuccess` = null、`error` = null、`instruction` = ''、`prompt` = ''、`generateError` = null（DD-18） |
| `GENERATE_FAILURE` | 仅更新 `generateError`；`currentDocument` / `selectedNodeId` / `lastPatch` / `lastIntegrity` / `lastSuccess` / `error` / `instruction` / `prompt` 全部不变 |
| `GENERATE_END` | `generateLoading = false` |

### 生成提交过程（固定 7 步）

1. 同步守卫（在同一同步代码路径中检查，事实来源为 ref 而非 state，DD-20）：`generateInFlightRef.current === true`、或精修 `inFlightRef.current === true`、或 `prompt.trim()` 为空、或 `prompt.trim().length > MAX_PROMPT_LENGTH` → 直接返回，不发请求；
2. `generateInFlightRef.current = true`（先设置 in-flight ref）；
3. `dispatch({ type: 'GENERATE_START' })`（后 dispatch START）；
4. `const result = await generateDraft({ prompt: prompt.trim() })`（发送 trim 后的 prompt）；
5. `result.kind === 'success'` → **同一同步路径中先** `latestSelectedNodeIdRef.current = null`（DD-19），**再** `dispatch({ type: 'GENERATE_SUCCESS', document: result.document })`；
6. `result.kind === 'server' | 'local'` → `dispatch({ type: 'GENERATE_FAILURE', error: result })`；
7. finally：`generateInFlightRef.current = false`（释放 in-flight ref）；`dispatch({ type: 'GENERATE_END' })`。

### 精修提交过程的增量约束

既有 `submitRefinement`（M3-02 固定 10 步）仅新增一项同步守卫，其余步骤不变：步骤 1 的同步守卫在既有 `inFlightRef.current` 检查之外，**必须同步检查 `generateInFlightRef.current === true` → 直接返回**（与既有快照、`selectedNodeId`、instruction 合法性等提交条件并列）。精修侧其余既有守卫（快照、`latestSelectedNodeIdRef`）行为不变。

### 并发与互斥（DD-20）

- 互斥的**事实来源是双同步 ref**：`generateInFlightRef`（生成侧）+ `inFlightRef`（精修侧）。两个提交 handler 都在同步窗口内检查两个 ref，保证同一同步事件循环窗口内先触发的一侧胜出、后触发的一侧被直接拦截；
- `generateLoading === true` 期间：生成按钮 disabled、`Enter` 提交被拦截；**精修提交按钮 disabled、精修 `Ctrl/Cmd+Enter` 被拦截**；节点选择**不禁用**；
- 精修 `loading === true` 期间：生成按钮 disabled、`Enter` 提交被拦截；
- `loading` / `generateLoading` 仅用于按钮 disabled 与 loading UI 展示，不承担互斥职责（state 更新不同步生效）；
- 精修侧既有守卫（`inFlightRef`、快照、`latestSelectedNodeIdRef`）行为不变。

## UI 布局与交互

1. 页面顶部新增生成区：单行 `<input type="text">`（placeholder 提示输入一句需求）+「生成初稿」按钮；
2. `prompt.trim()` 为空或超过 500 字符 → 生成按钮 disabled，`Enter` 不提交；
3. 生成请求进行中 → 生成按钮 disabled 且显示 loading 指示；
4. 生成成功 → 页面渲染新模板内容、无任何节点处于选中态、右侧精修面板回到"未选中"状态、结果面板不再显示旧的 `lastPatch` / `lastIntegrity` / `lastSuccess`、生成区错误面板清空（`generateError` = null，DD-18 的 9 项原子设置）；
5. 生成失败 → 生成区下方错误面板显示净化后的 `code` / `message` / `issues`；页面 DOM 保持原文档；三类本地错误文案可区分；
6. 生成成功后用户可立即点击选中新文档节点并执行 M3-02 精修闭环，交互与 Spec 006 完全一致。

## 测试矩阵 (Test Matrix)

| 层 | 文件（新建） | 最少数量 | 覆盖重点 |
|----|--------------|----------|----------|
| 后端 Provider 单元 | `backend/tests/generation/test_mock_generation_provider.py` | 14+ | 三组关键词正向映射、大小写不敏感、优先级顺序（多组同时命中）、无命中抛 `UnrecognizedIntentError`、同 prompt 确定性、深拷贝隔离正反（返回值独立对象；污染返回值后再次生成仍与首次一致）、三套模板逐一通过 `validate_dsl_document`、模板锚点节点存在、咖啡模板 `hero.title` 文案 ≠ Gold Case |
| 后端 Pipeline 单元 | `backend/tests/generation/test_generation_pipeline.py` | 12+ | prompt 空 / 纯空白 / 超 500 / 恰 500、步 1/2 失败时 Provider 未被调用、`UnrecognizedIntentError` → `unrecognized_intent`、Provider 抛其他异常 → `provider_error`、候选非 dict / 重复 ID / 未知类型 / 未知字段 → `invalid_generated_document`、成功返回 `DslDocument` |
| 后端 API | `backend/tests/api/test_generate_api.py` | 15+ | 三类模板成功（200 envelope 完整）、415 / 400 / 422（结构、空白、超长、unrecognized）、恶意 Provider 注入（非 dict、非法文档 → 502）、Provider 崩溃 → 502、错误响应净化（无 traceback / 路径 / prompt 原文）、OpenAPI 含新端点、refine 端点行为无回归 |
| 前端 API Client | `frontend/src/test/generate-api.test.ts` | 15+ | G-1 ~ G-7 全部分支正反、额外字段丢弃、本地错误固定文案、请求体仅含 prompt |
| 前端集成 | `frontend/src/test/generation-loop.test.tsx` | 12+ | `GENERATE_SUCCESS` 原子设置 9 项、失败隔离（状态与 DOM 不变）、重复提交守卫、生成中禁精修提交 / 不禁选择、精修中禁生成、**同一同步窗口跨链路互斥双向断言**（先精修后生成 / 先生成后精修，用 deferred Promise 挂起在途请求，**直接触发 handler / 快捷键路径**而非仅依赖按钮 disabled，断言仅先触发方的请求发出）、生成后精修闭环串联（生成 → 选择 → 精修成功） |
| E2E | `frontend/e2e/generation-loop.spec.ts` | 1+ | 输入咖啡店 prompt → 生成 → 页面出现模板文案 → 点击 `hero.title` → 提交 `set_text:` 精修 → 文案更新且见证节点 `hero.subtitle` 不变 |

既有测试（后端 310、前端 207、E2E `refinement-loop.spec.ts`）**一律不修改、不削弱、不删除**，且必须全绿。

## 允许的文件 (Allowed Files)

新建：

- `specs/007-initial-dsl-generation.md`（本文件）
- `backend/src/genui_api/generation/__init__.py`
- `backend/src/genui_api/generation/base.py`
- `backend/src/genui_api/generation/templates.py`
- `backend/src/genui_api/generation/mock.py`
- `backend/src/genui_api/generation/pipeline.py`
- `backend/tests/generation/__init__.py`
- `backend/tests/generation/test_mock_generation_provider.py`
- `backend/tests/generation/test_generation_pipeline.py`
- `backend/tests/api/test_generate_api.py`
- `frontend/src/api/generate.ts`
- `frontend/src/test/generate-api.test.ts`
- `frontend/src/test/generation-loop.test.tsx`
- `frontend/e2e/generation-loop.spec.ts`

允许修改（最小增量）：

- `backend/src/genui_api/api/routes.py`（新增 generate 路由、`get_generation_provider`、`_GENERATION_ERROR_HTTP_MAP`；不改既有路由与 `_ERROR_HTTP_MAP`）
- `backend/src/genui_api/api/schemas.py`（新增 `GenerateRequest` / `GenerateSuccess` / `GenerateFailure`；不改既有模型）
- `backend/src/genui_api/main.py`（`create_app` 新增 `generation_provider` 可选参数与 override）
- `frontend/src/api/types.ts`（追加生成相关类型；不改既有类型）
- `frontend/src/App.tsx`（生成区 UI + 状态迁移 + 竞态守卫）
- `frontend/src/app.css`（如需最小样式）
- `README.md`（里程碑表修正 + M4-01 状态更新）
- `docs/ARCHITECTURE.md`（§17 里程碑表修正 + 生成链路最小架构说明）
- `docs/GLOSSARY.md`（如需新术语，如"初稿生成"、"意图映射"）

禁止修改：

- `contracts/**`（DSL / Patch Schema）
- `examples/**`（Gold Case）
- 既有 `specs/000` ~ `specs/006`、`AGENTS.md`、`docs/PRODUCT.md`
- `frontend/src/dsl/**`（Renderer 契约）
- `frontend/src/api/refine.ts`（守卫已导出，直接复用，无需改动）
- 既有测试文件：`backend/tests/contracts/**`、`backend/tests/provider/**`、`backend/tests/refinement/**`、`backend/tests/api/test_health.py`、`backend/tests/api/test_dsl_validation_api.py`、`backend/tests/api/test_refine_api.py`、`frontend/src/test/refine-api.test.ts`、`frontend/src/test/refinement-loop.test.tsx`、`frontend/src/test/renderer.test.tsx`、`frontend/src/test/selection.test.tsx`、`frontend/src/test/style.test.ts`、`frontend/e2e/refinement-loop.spec.ts`
- `backend/src/genui_api/contracts/**`、`backend/src/genui_api/patch/**`、`backend/src/genui_api/provider/**`、`backend/src/genui_api/refinement/**`
- `frontend/vite.config.ts`、`frontend/playwright.config.ts`、`frontend/package.json`、`frontend/package-lock.json`、`backend/pyproject.toml`（**零新增依赖**，DD-23）
- 不删除任何文件；不使用 `eval` / `exec` / 动态代码执行

## 验收标准 (Acceptance Criteria)

### A. 文档与路线图（AC-01 ~ AC-05）

| # | 标准 |
|---|------|
| AC-01 | 本 Spec 完整存在且与 AGENTS.md / PRODUCT.md / ARCHITECTURE.md 一致 |
| AC-02 | `README.md` 里程碑表已按"背景与路线图纠正"章节修正（M4 = PDF 任务一、M5 = PDF 任务二、M6 = 完整面试交付） |
| AC-03 | `docs/ARCHITECTURE.md` §17 里程碑表已同步修正为相同内容 |
| AC-04 | 两处文档中 M4-01 均标记为「一句话生成网页初稿纵向切片」 |
| AC-05 | README / ARCHITECTURE / GLOSSARY 除里程碑修正与生成链路最小说明外无其他无关改动 |

### B. 后端契约与 Provider 抽象（AC-06 ~ AC-14）

| # | 标准 |
|---|------|
| AC-06 | `GenerateRequest` 存在于 `api/schemas.py`，仅 `prompt: str` 一个字段，`extra="forbid"` |
| AC-07 | `GenerateSuccess` / `GenerateFailure` envelope 与本 Spec 一致，失败侧复用既有 `ValidationErrorDetail` / `ValidationIssue`，成功响应不含 `patch` / `integrity` |
| AC-08 | `GenerationProvider` Protocol 存在于 `generation/base.py`，签名为 `async def generate_draft(self, prompt: str) -> dict` |
| AC-09 | `UnrecognizedIntentError` 定义于 `generation/base.py` |
| AC-10 | `get_generation_provider()` 定义于 `api/routes.py`，默认返回 `MockGenerationProvider()` |
| AC-11 | `create_app` 支持 `generation_provider` 可选参数并通过 `dependency_overrides[get_generation_provider]` 注入（测试中实际使用） |
| AC-12 | `_GENERATION_ERROR_HTTP_MAP` 为独立常量；既有 `_ERROR_HTTP_MAP` 与既有路由代码未修改 |
| AC-13 | generate 端点使用与 refine 一致的手动请求处理模式（原始 `Request` + Content-Type 前缀检查 + 手动 JSON 解析 + `model_validate` + `openapi_extra`） |
| AC-14 | OpenAPI 文档（`app.openapi()`）包含 `/api/v1/dsl/generate` 端点 |

### C. Generation Pipeline 与信任边界（AC-15 ~ AC-24）

| # | 标准 |
|---|------|
| AC-15 | `generate_document(prompt, provider)` 按本 Spec 固定 6 步顺序执行，失败以 `GenerationError(code, message, issues)` 抛出 |
| AC-16 | prompt 为空串或纯空白 → 422 `invalid_prompt`，且 Provider **未被调用**（mock 计数断言） |
| AC-17 | prompt trim 后 501 字符 → 422 `invalid_prompt` 且 Provider 未被调用；恰好 500 字符合法（走后续流程） |
| AC-18 | Provider 抛 `UnrecognizedIntentError` → 422 `unrecognized_intent` |
| AC-19 | Provider 抛出其他任意异常 → 502 `provider_error`，message 为固定净化文案（不含异常原文） |
| AC-20 | Provider 候选非 dict（如 `None` / 字符串 / list）→ 502 `invalid_generated_document` |
| AC-21 | Provider 候选含重复 ID / 非法嵌套（Form 外 Input）/ 未知组件类型 / 未知字段 → 502 `invalid_generated_document`，`issues` 含校验器返回的 `path` / `code` / `message` 明细 |
| AC-22 | Pipeline 校验唯一入口为 `validate_dsl_document`，未复制任何 DSL 校验规则；源码中无对候选的类型断言或选择性信任 |
| AC-23 | 成功响应 `document` 来自 `DslDocument.model_dump(mode="json")` |
| AC-24 | 全部错误响应不含 traceback、文件路径、环境变量、prompt 原文、完整候选文档内容 |

### D. Mock Provider 与模板（AC-25 ~ AC-35）

| # | 标准 |
|---|------|
| AC-25 | 含 `咖啡` 或 `coffee` 的 prompt → 返回 `TEMPLATE_COFFEE_SHOP` 的深拷贝 |
| AC-26 | 含 `报名` / `表单` / `活动` / `signup` / `form` / `event` 的 prompt → 返回 `TEMPLATE_EVENT_SIGNUP` 的深拷贝 |
| AC-27 | 含 `产品` / `介绍` / `落地页` / `product` / `landing` 的 prompt → 返回 `TEMPLATE_PRODUCT_INTRO` 的深拷贝 |
| AC-28 | 关键词匹配大小写不敏感（如 `COFFEE`、`Signup Form` 均命中） |
| AC-29 | 多组同时命中按优先级取先者：如「咖啡产品介绍」返回咖啡店模板（优先级 1 > 3） |
| AC-30 | 无任何关键词命中的 prompt → `MockGenerationProvider` 抛 `UnrecognizedIntentError`，API 层返回 422 `unrecognized_intent`，无任何默认模板兜底 |
| AC-31 | 三套模板逐一通过 `validate_dsl_document`，且本 Spec"模板定义要求"表中的锚点节点（id → type）全部存在 |
| AC-32 | 模板内容独立于 Gold Case：`TEMPLATE_COFFEE_SHOP` 的 `hero.title` 文案与 Gold Case 的 `hero.title` 文案不同（测试断言两者字符串不等） |
| AC-33 | `generate_draft` 返回值不是模板常量对象本身（`is not` 断言，含嵌套子对象独立） |
| AC-34 | 克隆隔离反向测试：篡改上一次返回值后再次生成，结果仍与首次逐字段相等（跨请求无污染） |
| AC-35 | 同一 prompt 连续多次生成，返回文档逐字段相等（确定性，无时间戳 / 随机值 / 计数器） |

### E. 后端 API 行为（AC-36 ~ AC-42）

| # | 标准 |
|---|------|
| AC-36 | 三类意图 prompt 各自 POST 后返回 200 `{success: true, document}`，document 通过响应侧结构断言（root 为 Page、锚点节点存在） |
| AC-37 | Content-Type 非 JSON → 415 `unsupported_media_type`；空 body / JSON 语法错误 → 400 `invalid_json` |
| AC-38 | 缺 `prompt` / `prompt` 非字符串 / 携带未知字段 → 422 `invalid_request_structure` |
| AC-39 | 注入恶意 Provider（返回非 dict）→ 502 `invalid_generated_document` |
| AC-40 | 注入恶意 Provider（返回重复 ID 或非法嵌套的文档）→ 502 `invalid_generated_document`，响应不含该候选文档内容 |
| AC-41 | 注入抛任意异常的 Provider → 502 `provider_error` |
| AC-42 | `/api/v1/dsl/refine` 与 `/api/v1/dsl/validate`、`/health` 的全部既有测试无回归 |

### F. 前端 API Client（AC-43 ~ AC-51）

| # | 标准 |
|---|------|
| AC-43 | `generateDraft(request, fetcher?)` 不抛异常，一切结果以 `GenerateClientResult` discriminated union 返回；请求为 POST `/api/v1/dsl/generate`，body 仅含 `prompt` |
| AC-44 | fetcher 抛异常（网络失败）→ `{kind: "local", code: "network_error"}`（G-1） |
| AC-45 | 响应体 JSON 解析失败 → `{kind: "local", code: "invalid_json"}`（G-2） |
| AC-46 | 响应体非对象或 `success` 非 boolean（如字符串 `"true"`）→ `invalid_response`（G-3） |
| AC-47 | HTTP 状态与 envelope 不一致（200 + `success: false`，或 422 + `success: true`）→ `invalid_response`（G-4） |
| AC-48 | `success === true` 但 `document` 缺失 / 非对象 / 缺 `version` / `root` 非法 → `invalid_response`（G-5，使用 `isDslDocumentShape`） |
| AC-49 | 成功结果仅含 `document`，响应中的额外字段（如 `debug`、`patch`）不出现在返回值中（G-6） |
| AC-50 | 失败结果净化提取 `code` / `message` / `issues`（`issues` 缺失或非法时为 `[]`），失败响应额外携带的 `document` 被丢弃（G-7） |
| AC-51 | `generate.ts` 复用 `refine.ts` 导出的 `isRecord` / `isDslDocumentShape`；`frontend/src/api/**` 与 App 生成状态代码中无 `any`、无 `as GenerateSuccess` / `as unknown as` 等类型断言绕过 |

### G. 前端状态迁移与竞态（AC-52 ~ AC-61）

| # | 标准 |
|---|------|
| AC-52 | 生成成功由**单个** `GENERATE_SUCCESS` dispatch 原子设置 9 项：`currentDocument` 替换为响应 document，`selectedNodeId` / `lastPatch` / `lastIntegrity` / `lastSuccess` / `error` / `generateError` 清空为 null、`instruction` 与 `prompt` 清空为 `''` |
| AC-53 | `GENERATE_SUCCESS` dispatch 之前，同一同步代码路径中已执行 `latestSelectedNodeIdRef.current = null`（先 ref 后 dispatch） |
| AC-54 | 生成失败（server / local）仅 `generateError` 与 `generateLoading` 变化；`currentDocument` / `selectedNodeId` / `lastPatch` / `lastIntegrity` / `lastSuccess` / `error` / `instruction` / `prompt` 全部保持提交前原值 |
| AC-55 | 生成失败后页面 DOM 与提交前完全一致（渲染仍为旧文档） |
| AC-56 | 生成请求在途期间再次触发生成提交不发起第二个请求（`fetcher` 调用次数仍为 1，`generateInFlightRef` 同步守卫；直接触发 handler 路径验证，不依赖按钮 disabled） |
| AC-57 | 生成进行中：精修提交按钮 disabled 且 `Ctrl/Cmd+Enter` 不触发精修请求；节点选择交互**不被禁用**（点击可正常改变选中态） |
| AC-58 | 精修 `loading` 期间：生成按钮 disabled 且 `Enter` 不触发生成请求 |
| AC-59 | 跨链路同步互斥（精修先行）：同一同步窗口内先触发精修提交、再立即触发生成提交 → 只有精修请求发出，生成 `fetcher` 未被调用；测试必须**直接触发 handler / 快捷键路径**（不得仅依赖按钮 disabled），证明 `generateInFlightRef` / `inFlightRef` 同步守卫生效 |
| AC-60 | 跨链路同步互斥（生成先行）：同一同步窗口内先触发生成提交、再立即触发精修提交 → 只有生成请求发出，精修 `fetcher` 未被调用；测试必须**直接触发 handler / 快捷键路径**（不得仅依赖按钮 disabled），证明同步守卫生效 |
| AC-61 | 无论成功或失败，生成请求结束后 `generateLoading` 均为 `false` |

### H. UI（AC-62 ~ AC-67）

| # | 标准 |
|---|------|
| AC-62 | 页面顶部存在生成区：单行 `<input type="text">` + 「生成初稿」按钮 |
| AC-63 | `prompt.trim()` 为空或超过 500 字符时生成按钮 disabled 且 `Enter` 不提交；prompt 合法时 `Enter` 在生成输入框中触发提交 |
| AC-64 | 生成请求进行中生成按钮 disabled 且 loading 指示可见 |
| AC-65 | 生成成功后：页面渲染新模板内容、无任何节点带 `data-selected`、精修面板显示"未选中"状态、旧的 Patch / integrity / 成功结果面板内容不再显示、生成区错误面板为空 |
| AC-66 | 生成失败后：生成区错误面板显示净化后的 `code` / `message` / `issues`；三类本地错误（`network_error` / `invalid_json` / `invalid_response`）文案可区分 |
| AC-67 | 集成测试断言"生成 → 选择 → 精修"串联：生成成功后选中新文档节点、提交 `set_text:` 精修指令、精修成功且 `currentDocument` 更新（M3-02 闭环在新文档上完整可用） |

### I. E2E（AC-68 ~ AC-72）

| # | 标准 |
|---|------|
| AC-68 | 新建 `frontend/e2e/generation-loop.spec.ts`，`npm run test:e2e` 单条命令同时运行既有与新增 E2E（`playwright.config.ts` 不修改） |
| AC-69 | E2E：输入含「咖啡」的 prompt 并提交后，页面出现咖啡店模板的 `hero.title` 文案（与 Gold Case 文案不同） |
| AC-70 | E2E：点击新文档的 `hero.title` 节点后精修面板显示其 ID 与 Type |
| AC-71 | E2E：提交 `set_text:` 精修指令后，页面该节点文案更新为新值 |
| AC-72 | E2E：精修后见证节点 `hero.subtitle` 文案保持模板原值不变；既有 `e2e/refinement-loop.spec.ts` 未修改且继续通过 |

### J. 回归与范围（AC-73 ~ AC-80）

| # | 标准 |
|---|------|
| AC-73 | 前端既有 207 个测试全部通过，且既有 5 个测试文件（`refine-api` / `refinement-loop` / `renderer` / `selection` / `style`）未被修改、削弱或删除 |
| AC-74 | 后端既有 310 个测试全部通过，且既有后端测试文件未被修改、削弱或删除 |
| AC-75 | `npm run typecheck` 与 `npm run build` 均通过 |
| AC-76 | 零新增依赖：`frontend/package.json`、`frontend/package-lock.json`、`backend/pyproject.toml` 无任何变更 |
| AC-77 | `contracts/**`、`examples/**`、`frontend/src/dsl/**`、`frontend/src/api/refine.ts`、`frontend/vite.config.ts`、`frontend/playwright.config.ts` 均无变更 |
| AC-78 | 前端源码（`frontend/src/api/**` + `frontend/src/App.tsx`）无 `any`、无类型断言绕过运行时检查 |
| AC-79 | 前后端源码无 `eval` / `exec` / `new Function` / `dangerouslySetInnerHTML` 等禁止内容 |
| AC-80 | 未删除任何文件；未触碰 Allowed Files 之外的文件；验证结果如实记录 |

## 验证命令 (Verification Commands)

共 24 条（V-01 ~ V-24）。全部使用**仓库相对路径**，均从仓库根目录执行；不得出现任何本机绝对路径。需切换目录的命令统一用子 shell `( cd … && … )` 包裹。

```bash
# === 准备 ===

# V-01. 按锁文件确定性安装前端依赖（零新增，仅确保环境就绪）
( cd frontend && npm ci )

# V-02. 安装 Playwright Chromium 浏览器（E2E 前置，如已安装可跳过）
( cd frontend && npx playwright install chromium )

# === 前端验证 ===

# V-03. TypeScript 类型检查
( cd frontend && npm run typecheck )

# V-04. 全部前端单元测试（npm test 为 watch 模式，必须传 --run）
( cd frontend && npm test -- --run )

# V-05. 生成 API Client 专项测试
( cd frontend && npm test -- --run src/test/generate-api.test.ts )

# V-06. 生成闭环集成测试（状态迁移、竞态、失败隔离、生成后精修串联）
( cd frontend && npm test -- --run src/test/generation-loop.test.tsx )

# V-07. 既有前端测试无回归（5 个既有文件全绿）
( cd frontend && npm test -- --run src/test/refine-api.test.ts src/test/refinement-loop.test.tsx src/test/renderer.test.tsx src/test/selection.test.tsx src/test/style.test.ts )

# V-08. 生产构建成功
( cd frontend && npm run build )

# V-09. 依赖白名单检查（本轮零新增）
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

# V-10. 前端安全扫描（禁止内容不得出现）；排除测试目录（测试名字符串会误命中）
if grep -rn -E "dangerouslySetInnerHTML|eval\(|new Function\(|exec\(" --exclude-dir=test frontend/src/; then
  echo "FAIL: 存在禁止内容"
  exit 1
else
  echo "OK: clean"
fi

# V-11. 禁止类型断言绕过（含生成侧类型）
if grep -rn -E "as +(GenerateSuccess|GenerateFailure|GenerateClientResult|RefineResponse|RefineSuccess|RefineFailure)|as +unknown +as" frontend/src/api/ frontend/src/App.tsx; then
  echo "FAIL: 存在类型断言绕过"
  exit 1
else
  echo "OK: no assertion bypass"
fi

# V-12. 禁止 any
if grep -rn -E ":\s*any\b|<any>|as +any" frontend/src/api/ frontend/src/App.tsx; then
  echo "FAIL: 存在 any"
  exit 1
else
  echo "OK: no any"
fi

# === 后端验证 ===

# V-13. 后端全量测试通过（310 既有 + 本轮新增）
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest --tb=short -q )

# V-14. 生成模块专项测试（Provider 映射 / 克隆隔离 / Pipeline 正反）
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/generation/ --tb=short -q )

# V-15. API 专项测试（含新增 /api/v1/dsl/generate 与既有端点回归）
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/api/ --tb=short -q )

# V-16. 后端测试计数（≥ 310 + 新增数量，以框架原生汇总为准）
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest --collect-only -q )

# V-17. 三套模板逐一通过真实 DSL 校验
( cd backend && PYTHONPATH=src .venv/bin/python -c "
from genui_api.generation.templates import (
    TEMPLATE_COFFEE_SHOP, TEMPLATE_EVENT_SIGNUP, TEMPLATE_PRODUCT_INTRO)
from genui_api.contracts.validation import validate_dsl_document
for name, tpl in [('coffee', TEMPLATE_COFFEE_SHOP),
                  ('event', TEMPLATE_EVENT_SIGNUP),
                  ('product', TEMPLATE_PRODUCT_INTRO)]:
    validate_dsl_document(tpl)
    print(f'TEMPLATE {name} OK')
" )

# === 真实 API Smoke Test ===

# V-18. httpx.ASGITransport 内嵌调用真实应用：成功 + 不识别两条路径
( cd backend && PYTHONPATH=src .venv/bin/python - <<'PY'
import asyncio, httpx
from genui_api.main import app

async def call(payload):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:
        return await client.post("/api/v1/dsl/generate", json=payload)

# 路径 1：咖啡意图 → 200 成功
resp = asyncio.run(call({"prompt": "我要一个咖啡店的落地页"}))
assert resp.status_code == 200, f"FAIL status={resp.status_code} body={resp.text[:200]}"
body = resp.json()
assert body["success"] is True, f"FAIL success={body}"
assert body["document"]["version"] == "0.1"
assert body["document"]["root"]["type"] == "Page"

# 路径 2：无法识别 → 422 unrecognized_intent
resp2 = asyncio.run(call({"prompt": "随便来点什么"}))
assert resp2.status_code == 422, f"FAIL status={resp2.status_code}"
body2 = resp2.json()
assert body2["success"] is False
assert body2["error"]["code"] == "unrecognized_intent", f"FAIL code={body2['error']['code']}"

print("GENERATE SMOKE OK")
PY
)

# === E2E ===

# V-19. Playwright E2E（既有精修闭环 + 新增生成串联，webServer 自动启动前后端）
( cd frontend && npm run test:e2e )

# === 无变更验证 ===

# V-20. 契约与示例未变更
git diff HEAD --exit-code -- contracts/ examples/

# V-21. 前端受保护文件未变更（Renderer / refine.ts / 配置 / 依赖清单）
git diff HEAD --exit-code -- frontend/src/dsl/ frontend/src/api/refine.ts frontend/vite.config.ts frontend/playwright.config.ts frontend/package.json frontend/package-lock.json

# V-22. 后端受保护模块与依赖清单未变更
git diff HEAD --exit-code -- backend/src/genui_api/contracts/ backend/src/genui_api/patch/ backend/src/genui_api/provider/ backend/src/genui_api/refinement/ backend/pyproject.toml

# V-23. 既有测试文件未变更
git diff HEAD --exit-code -- backend/tests/contracts/ backend/tests/provider/ backend/tests/refinement/ backend/tests/api/test_health.py backend/tests/api/test_dsl_validation_api.py backend/tests/api/test_refine_api.py frontend/src/test/refine-api.test.ts frontend/src/test/refinement-loop.test.tsx frontend/src/test/renderer.test.tsx frontend/src/test/selection.test.tsx frontend/src/test/style.test.ts frontend/e2e/refinement-loop.spec.ts

# === 整体检查 ===

# V-24. 空白问题、仓库状态与变更规模
git diff HEAD --check && git status --short && git diff HEAD --stat
```

补充说明：

- 后端命令使用 `.venv/bin/python`：系统 `python3` 未安装 uvicorn / 后端依赖，后端依赖仅存在于 `backend/.venv`。
- 测试计数以 V-04 / V-16 的测试框架原生汇总输出为准，不使用 `grep -c` 统计。

## 审批闸门 (Approval Gates)

| # | 审批项 | 内容 |
|---|--------|------|
| 1 | M4-01 产品范围 | "目标"章节 12 点链路 + "范围外"章节全部排除项（不接真实模型、不实现自然语言 Patch 等） |
| 2 | 路线图修正 | "背景与路线图纠正"章节：实施时同步修正 `README.md` 与 `docs/ARCHITECTURE.md` 里程碑表（M4 / M5 / M6 最新定义） |
| 3 | 生成 API 契约 | `POST /api/v1/dsl/generate`、`GenerateRequest {prompt}`、success envelope 与 refine 一致、"错误分类映射"全表（DD-1 ~ DD-5） |
| 4 | Generation Provider 抽象 | `generation/base.py` 的 Protocol（`generate_draft(prompt) -> dict` 不可信候选）+ `UnrecognizedIntentError` + 注入模式（DD-6 / DD-7 / DD-13） |
| 5 | Mock 意图映射与模板 | 三组关键词固定优先级子串匹配、无命中 → `unrecognized_intent` 不兜底、三套独立模板 + 静态语义化 ID + `copy.deepcopy` 克隆（DD-9 ~ DD-12） |
| 6 | 信任边界 | 候选必须经 `validate_dsl_document` 全量校验后才进入响应；禁止类型断言、禁止前端本地拼装 DSL（DD-8 / DD-16 / Pipeline 6 步） |
| 7 | 前端状态迁移 | 新增 5 个 action、`GENERATE_SUCCESS` 原子设置 9 项清单（含 instruction / prompt / generateError）、`latestSelectedNodeIdRef` 同步重置（DD-17 ~ DD-19） |
| 8 | 并发与竞态 | 生成中禁精修提交不禁选择、精修中禁生成、`generateInFlightRef` + `inFlightRef` 双同步 in-flight 守卫作为互斥事实来源、单请求互斥模型（不允许生成请求并发，不引入序号 / latest-wins / 取消语义）（DD-20 / DD-21） |
| 9 | Allowed Files 与零依赖 | "允许的文件"三段完整清单；前后端**零新增依赖**、不改 vite / playwright / package 配置（DD-23） |
| 10 | Acceptance Criteria | AC-01 ~ AC-80 完整列表，每条可独立验收 |
| 11 | 验证命令清单 | V-01 ~ V-24 全部使用仓库相对路径 |

## 开放决策 (Open Decisions)

None。

本 Spec 已对任务书列出的全部设计点拍板完毕（API 形态、prompt 规则、Provider 接口、意图映射与无命中策略、节点 ID 策略、模板克隆机制、信任边界、前端状态迁移与 instruction 处理、并发与竞态机制、错误净化模块归属、回归基线、测试矩阵、Allowed Files 与零依赖、AC 与验证命令）。实现过程中如出现本 Spec 未覆盖的新决策点，必须暂停并上报，不得自行拍板。

## 完成报告格式 (Completion Report Format)

按 AGENTS.md §10 固定格式输出，包含以下小节：

```text
## Result
## Repository State
## Files Created
## Files Modified
## Key Decisions Recorded
## Acceptance Criteria     （逐条 AC-01 ~ AC-80 标记 PASS / FAIL，附证据）
## Verification            （实际运行的 V-01 ~ V-24 命令与真实输出；未运行的写明"未运行"及原因）
## Scope Check             （是否安装未授权依赖/触碰范围外文件/删除文件）
## Open Decisions          （需所有者决定的问题；没有则写 None）
## Git Summary             （git status --short 与 git diff --stat）
## Recommended Next Task   （只提一个建议，不执行）
```

报告必须如实。没做的、没运行的，就直说。隐瞒失败的报告本身就是失败。
