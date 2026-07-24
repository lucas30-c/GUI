# Spec 005 — Refinement Pipeline、Mock Provider 与 Refine API

## 目标 (Goal)

实现第一个后端局部精修闭环：当前 DSL Document + selectedNodeId + 自然语言指令 → Model Provider 生成候选 Patch → 确定性校验与应用 → 返回已验证的新 DSL Document。本轮仅使用 Mock Provider，不引入真实模型调用。

## 背景 (Context)

- 前置：Spec 001（DSL v0.1 契约与校验核心）已交付。
  - `validate_dsl_document(data: dict) -> DslDocument`
  - DslDocument: version="0.1", root=PageNode, metadata=Optional[DslMetadata]
  - 9 种节点类型的 Discriminated Union
- 前置：Spec 003（Controlled Patch v0.1 契约与确定性应用核心）已交付。
  - `apply_patch(document: dict, patch: dict) -> DslDocument`
  - PatchDocument: version="0.1", operations=[UpdatePropsOperation]
  - PatchError(code, message, issues: List[PatchIssue])
  - 5 类错误码：invalid_patch_structure, invalid_source_document, patch_target_not_found, invalid_patched_document, internal_patch_error
- 前置：Spec 004（前端 DSL Renderer 与单节点选中）已交付。
  - 前端可选中节点并获取 selectedNodeId
- 后端 213 个 pytest 全部通过。
- 里程碑：M3 — 局部精修闭环（Mock Provider）。
- 架构依据：[ARCHITECTURE.md](../docs/ARCHITECTURE.md)

## 范围内 (In Scope)

1. `RefinementProvider` Protocol 定义（`typing.Protocol`）
2. `RefinementContext` 数据类（传递给 Provider 的受控上下文）
3. `RefinementResult` 数据类（Pipeline 成功返回值）
4. `MockProvider` 实现（确定性映射，无网络、无随机）
5. 可注入的反向测试 Provider（BrokenStructureProvider、WrongTargetProvider、MultiTargetProvider、InvalidResultProvider）
6. `refine()` 无状态异步编排函数（Refinement Pipeline 核心）
7. Pipeline 10 步确定性执行流程
8. `verify_non_target_unchanged()` 深比较验证算法
9. `POST /api/v1/dsl/refine` HTTP 端点
10. Refine 请求/响应 Pydantic 模型（schemas）
11. Provider 通过 FastAPI Depends 注入
12. 12 个错误码定义与错误响应结构
13. `candidate_boundary_violation` 校验（所有操作仅指向 selectedNodeId）
14. `non_target_mutation_detected` 校验（深比较非目标节点）
15. MockProvider 单元测试（正向 + 反向）
16. Pipeline 单元测试（正向 + 反向）
17. API 集成测试（正向 + 反向）
18. 回归验证（现有 213 个测试无破坏）
19. 最小文档更新（README、ARCHITECTURE、GLOSSARY）

## 范围外 (Out of Scope)

- 前端 API 调用（前端不调用 /api/v1/dsl/refine）
- Chat UI / 对话界面
- 多轮会话 / 上下文记忆
- 服务端持久化 / 数据库
- 初稿 DSL 生成（Generate from scratch）
- 真实模型 Provider（OpenAI / Claude / 本地模型）
- API Key 配置 / 环境变量密钥读取
- Prompt 模板系统
- Trace 持久化 / 日志存储
- 模板推荐
- Undo / Redo
- Patch / DSL Schema 修改
- 节点增删移动操作（add/remove/move）
- 新依赖引入

## 允许的文件 (Allowed Files)

新建：

- `specs/005-refinement-pipeline-mock-provider-api.md`（本文件）
- `backend/src/genui_api/provider/__init__.py`
- `backend/src/genui_api/provider/base.py`（Provider Protocol）
- `backend/src/genui_api/provider/mock.py`（Mock Provider）
- `backend/src/genui_api/refinement/__init__.py`
- `backend/src/genui_api/refinement/pipeline.py`（Refinement Pipeline）
- `backend/tests/provider/__init__.py`
- `backend/tests/provider/test_mock_provider.py`
- `backend/tests/refinement/__init__.py`
- `backend/tests/refinement/test_pipeline.py`
- `backend/tests/api/test_refine_api.py`

最小修改：

- `backend/src/genui_api/api/routes.py`（添加 refine 端点）
- `backend/src/genui_api/api/schemas.py`（添加 refine 请求/响应模型）
- `backend/src/genui_api/main.py`（Provider 注入，仅在确有必要时）
- `README.md`（M3 状态更新）
- `docs/ARCHITECTURE.md`（M3 模块、里程碑）
- `docs/GLOSSARY.md`（新术语）

禁止修改：

- `frontend/**`
- `contracts/**`
- `examples/**`
- `AGENTS.md`
- `specs/000-004`
- `backend/src/genui_api/contracts/**`（DSL 核心语义）
- `backend/src/genui_api/patch/**`（Patch 核心语义）
- `backend/tests/contracts/**`（现有测试）

## 禁止的变更 (Forbidden Changes)

- 引入新依赖（pydantic、pytest、httpx 之外）
- 修改 DSL v0.1 Schema（`contracts/dsl/v0.1/schema.json`）
- 修改 Patch v0.1 Schema（`contracts/patch/v0.1/schema.json`）
- 修改现有 API 端点行为（`/health`、`/api/v1/dsl/validate`）
- 删除或弱化现有测试
- 读取 API Key 或环境变量中的密钥
- 生成或执行任意代码（`eval`/`exec`/`pickle`）
- 在错误消息中泄露 traceback、文件路径、环境变量
- 删除文件
- 为"未来可能需要"建立复杂抽象
- 在实现过程中擅自降低本 Spec 的验收标准

## 设计决策 (Design Decisions)

| # | 决策 | 理由 |
|---|------|------|
| DD-1 | Provider 使用 `typing.Protocol`（非 ABC） | 结构化子类型，无需继承，更 Pythonic；测试更灵活 |
| DD-2 | Provider 接口为 `async def generate_patch(context: RefinementContext) -> dict` | async 兼容未来网络调用；返回 dict 因为候选是不可信数据 |
| DD-3 | Provider 通过 `get_provider` 依赖 + `create_app(refinement_provider)` 注入，见"Provider 注入"章节精确代码 | 可测试；无全局可变单例；多 app 实例不污染；测试灵活 |
| DD-4 | non-target zero-change 使用规范化 dict 深等比较（移除目标节点 props 后全量对比） | 确定性；覆盖 metadata/version/root/所有节点；不依赖 Provider 自声明 |
| DD-5 | Refinement Pipeline 为无状态异步编排函数 `async def refine(...)` | 不持有状态；不修改输入；可独立测试 |
| DD-6 | Refine 响应使用独立 success envelope，内部错误详情结构（code/message/issues[]）与现有 API 保持一致 | Validate 使用 valid envelope，Refine 业务语义不同需独立响应模型；错误详情结构复用减少学习成本 |
| DD-7 | 路由接收原始 Request + openapi_extra 声明 requestBody schema | 保持手动处理 Content-Type/空 body/JSON 解析的控制力；openapi_extra 让 OpenAPI 文档精确描述请求结构 |

## Provider Interface

```python
from typing import Protocol
from dataclasses import dataclass


@dataclass
class RefinementContext:
    """传递给 Provider 的受控上下文。"""
    instruction: str                  # 用户自然语言指令
    selected_node_id: str             # 选中节点 ID
    selected_node_type: str           # 选中节点类型
    selected_node_props: dict         # 选中节点当前 props（深拷贝）
    document_version: str             # DSL 版本
    # 注意：不传递完整文档给 Provider（最小权限原则）
    # 未来可选扩展：siblings context、parent context


class RefinementProvider(Protocol):
    async def generate_patch(self, context: RefinementContext) -> dict:
        """返回候选 Patch dict（不可信，需校验）。"""
        ...
```

关键设计：

- `RefinementContext` 仅暴露选中节点相关信息，不传递完整文档（最小权限原则）。
- `selected_node_props` 必须是深拷贝，Provider 对其修改不得影响原始 document。
- 返回 `dict` 而非 `PatchDocument`——候选数据来自外部不可信源，必须经过完整校验管线。
- Protocol 定义使任何具有匹配签名的类自动满足接口，无需显式继承。

## Provider 注入

唯一实现方式：

```python
def get_provider() -> RefinementProvider:
    """默认 Provider 工厂，返回无状态 MockProvider。"""
    return MockProvider()

def create_app(
    refinement_provider: RefinementProvider | None = None,
) -> FastAPI:
    application = FastAPI(...)

    if refinement_provider is not None:
        application.dependency_overrides[get_provider] = (
            lambda: refinement_provider
        )

    application.include_router(router)
    return application
```

约束：

- `get_provider` 每次调用返回新建的无状态 MockProvider，不保存全局可变实例。
- 默认模块级 `app = create_app()`。
- `create_app(custom_provider)` 的 override 只属于该 app 实例。
- 测试还可对单个 app 使用 `app.dependency_overrides[get_provider] = lambda: test_provider`。
- 两个 app 实例的 Provider 不得互相污染（各自的 `dependency_overrides` 独立）。
- `routes.py` 中 refine 路由只能通过 `Depends(get_provider)` 获取 Provider，不得直接导入或实例化。

## Refinement Pipeline

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class RefinementResult:
    """Pipeline 成功时的返回值。"""
    success: bool                     # 始终为 True
    patch: dict                       # 已验证的候选 Patch
    document: dict                    # 已验证的新 DSL Document（序列化为 dict）
    integrity: dict                   # 完整性信息


async def refine(
    document: dict,
    selected_node_id: str,
    instruction: str,
    provider: RefinementProvider,
) -> RefinementResult:
    """
    Refinement Pipeline 核心。无状态、不修改输入的异步编排函数。
    调用外部 Provider 生成候选 Patch，经确定性校验后返回结果。
    失败时抛出 RefinementError。
    """
    ...
```

### Pipeline 执行步骤（严格顺序）

| 步骤 | 操作 | 失败错误码 |
|------|------|-----------|
| 1 | 校验 instruction 非空且不超 1000 字符 | `invalid_instruction` |
| 2 | 调用 `validate_dsl_document(document)` | `invalid_source_document` |
| 3 | 在已验证文档中查找 selected_node_id | `target_node_not_found` |
| 4 | 构造 RefinementContext（selected_node_props 深拷贝，保存原始 selected_node_id 的可信副本） | — |
| 5 | 调用 `provider.generate_patch(context)` | `provider_error` |
| 6 | 使用 `PatchDocument.model_validate(candidate)` 校验结构 | `invalid_candidate_structure` |
| 7 | 验证所有 `operations[].targetNodeId == selected_node_id`（使用步骤 3 保存的可信值） | `candidate_boundary_violation` |
| 8 | 调用 `apply_patch(document, candidate)` | `patch_application_failed` 或 `internal_error` |
| 9 | 深比较：验证非目标节点完整性（规范化 dict 对比） | `non_target_mutation_detected` |
| 10 | 构造并返回 RefinementResult | — |

关键语义：

- 步骤 2 复用 M1-01 的 `validate_dsl_document`，不重复实现校验规则。
- 步骤 6 复用 M1-03 的 `PatchDocument` 模型，不重复实现 Patch 结构校验。
- 步骤 8 复用 M1-03 的 `apply_patch`，不重复实现 Patch 应用逻辑。
- 步骤 7 是本轮新增的安全边界：确保 Provider 不越权修改非选中节点。
- 步骤 9 是本轮新增的完整性校验：即使步骤 7 通过，仍验证实际结果（防御深层 bug）。
- `refine()` 不修改传入的 document 和 instruction 参数（输入不可变性）。

### Pipeline 安全保证（恶意 Provider 防护）

- Pipeline 从已验证文档中构造独立的 RefinementContext。
- `selected_node_props` 必须是深拷贝——Provider 对其修改不得改变原始 document。
- Provider 对 context 或 `selected_node_props` 的任何修改不得改变原始 document。
- Provider 修改 `context.selected_node_id` 后，不得改变 Pipeline 使用的可信 selected_node_id。
- 候选边界检查（步骤 7）必须始终使用 `refine()` 的原始 `selected_node_id`，而不是 Provider 可能修改后的 context。
- Provider 修改 context 后生成的候选仍必须经过结构校验、边界校验、apply_patch 和完整性校验。

对应测试 Provider 行为：

1. 修改 `context.selected_node_props`
2. 尝试修改 `context.selected_node_id`
3. 返回候选 Patch
4. 断言原始 document 未变
5. 断言越界候选仍被拒绝
6. 不笼统断言"Pipeline 行为完全不受影响"

### PatchError 映射表

`apply_patch` 抛出 `PatchError` 时，Pipeline 按以下规则映射：

| PatchError.code | HTTP | Refine error code |
|---|---|---|
| invalid_patched_document | 502 | patch_application_failed |
| patch_target_not_found | 502 | patch_application_failed |
| invalid_patch_structure | 502 | patch_application_failed |
| internal_patch_error | 500 | internal_error |
| 未识别的 PatchError.code | 500 | internal_error |

约束：`internal_error` 响应不得直接暴露 PatchError.message 或 issues 中的内部原文。

## Request Model

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Any

class RefineRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    document: dict[str, Any]
    selected_node_id: str = Field(
        alias="selectedNodeId",
        min_length=1,
    )
    instruction: str
```

关键语义说明：

- `document` 保持 `dict[str, Any]`，不直接声明为 DslDocument。否则非法源 DSL 会在请求模型阶段变成 `invalid_request_structure`，无法进入 Pipeline 返回 `invalid_source_document`。
- `instruction` 的空白/长度上限由 Pipeline 处理（稳定映射 `invalid_instruction`），RefineRequest 只要求字段存在。
- `selectedNodeId` 通过 alias 和 `populate_by_name=True` 同时支持驼峰和下划线。
- `extra="forbid"` 拒绝额外字段——额外字段触发 422 `invalid_request_structure`。

## Response Models

```python
from pydantic import BaseModel, Field
from typing import Literal

class RefinementIntegrity(BaseModel):
    selected_node_id: str = Field(alias="selectedNodeId")
    non_target_nodes_unchanged: Literal[True] = Field(alias="nonTargetNodesUnchanged")

class RefineSuccess(BaseModel):
    success: Literal[True]
    patch: PatchDocument          # 复用现有 PatchDocument 模型
    document: DslDocument         # 复用现有 DslDocument 模型
    integrity: RefinementIntegrity

class RefineFailure(BaseModel):
    success: Literal[False]
    error: ValidationErrorDetail  # 复用现有 ValidationErrorDetail（code, message, issues: List[ValidationIssue]）
```

关键约束：

- `patch` 和 `document` 字段必须使用已有的 Pydantic 模型（`PatchDocument`、`DslDocument`），不得写成宽泛 dict。
- `error` 使用现有 `ValidationErrorDetail`（定义于 `genui_api.api.schemas`，字段：code, message, issues: List[ValidationIssue]），保持 API 内部一致性。
- `RefinementIntegrity.non_target_nodes_unchanged` 类型为 `Literal[True]`：成功响应中此字段只允许 `true`；若为 `false` 则走失败路径（`non_target_mutation_detected`），不会出现在成功响应中。
- 响应使用 `success` envelope（区别于 `/api/v1/dsl/validate` 的 `valid` envelope）。

## API Endpoint

### 路由手动处理与 OpenAPI 声明

refine 端点的路由函数采用手动处理模式（与现有 validate 端点一致）：

1. 路由函数接收原始 `Request`（非 Pydantic body 参数）
2. 路由函数手动检查 Content-Type header
3. 路由函数手动读取 body 并尝试 JSON 解析
4. 路由函数手动调用 `RefineRequest.model_validate(data)`
5. **不得**添加全局异常处理器（exception_handler）影响现有 `/health` 和 `/api/v1/dsl/validate` 端点
6. **不得**添加全局 `RequestValidationError` handler

OpenAPI requestBody 声明方式：

- 由于路由只接收原始 `Request` 参数，FastAPI 不会自动生成 requestBody schema
- 通过路由 decorator 的 `openapi_extra` 显式提供 requestBody schema
- requestBody schema 使用 `RefineRequest.model_json_schema(by_alias=True)` 生成，不允许手写重复 schema
- 示例：`@router.post("/api/v1/dsl/refine", openapi_extra={"requestBody": ...})`

### 请求

```
POST /api/v1/dsl/refine
Content-Type: application/json
```

请求体：

```json
{
  "document": { "version": "0.1", "root": { "id": "page-1", "type": "Page", "props": { "title": "Demo" }, "children": [...] } },
  "selectedNodeId": "node-123",
  "instruction": "把按钮文案改成「立即购买」"
}
```

字段约束：

| 字段 | 类型 | 约束 |
|------|------|------|
| `document` | object | 必填；合法 DSL Document |
| `selectedNodeId` | string | 必填；非空（min_length=1） |
| `instruction` | string | 必填；非空且不超 1000 字符（Pipeline 校验） |

### 成功响应 (200)

```json
{
  "success": true,
  "patch": {
    "version": "0.1",
    "operations": [
      { "op": "update_props", "targetNodeId": "node-123", "props": { "text": "立即购买" } }
    ]
  },
  "document": { "version": "0.1", "root": { "id": "page-1", "type": "Page", "props": { "title": "Demo" }, "children": [...] } },
  "integrity": {
    "selectedNodeId": "node-123",
    "nonTargetNodesUnchanged": true
  }
}
```

### 错误响应

```json
{
  "success": false,
  "error": {
    "code": "target_node_not_found",
    "message": "Node not found in document",
    "issues": [
      { "path": "selectedNodeId", "code": "target_node_not_found", "message": "Node not found in document" }
    ]
  }
}
```

## Error Codes

| HTTP | code | 触发条件 |
|------|------|---------|
| 415 | `unsupported_media_type` | Content-Type 非 application/json |
| 400 | `invalid_json` | JSON 解析失败或空 body |
| 422 | `invalid_request_structure` | 缺少必填字段、类型错误或存在额外字段 |
| 422 | `invalid_instruction` | instruction 为空/纯空白/超 1000 字符 |
| 422 | `invalid_source_document` | 输入 DSL 文档未通过校验 |
| 422 | `target_node_not_found` | selectedNodeId 在文档中不存在 |
| 502 | `provider_error` | Provider 调用异常 |
| 502 | `invalid_candidate_structure` | Provider 返回的候选 Patch 结构非法 |
| 502 | `candidate_boundary_violation` | 候选 Patch 包含非 selectedNodeId 的操作 |
| 502 | `patch_application_failed` | apply_patch 因候选内容问题执行失败（如 invalid_patched_document、patch_target_not_found 等可归因于候选的错误） |
| 500 | `non_target_mutation_detected` | 应用后非目标节点发生变化 |
| 500 | `internal_error` | 未预期内部错误（含 apply_patch 内部不可归因于候选内容的故障） |

状态码逻辑：

- 请求问题（客户端可修复）→ 422
- Provider/候选问题（上游服务问题，含候选导致的 apply_patch 失败）→ 502
- 完整性破坏和不可归因于候选的内部错误 → 500

## Provider 错误消息脱敏

Provider 相关错误（`provider_error`、`invalid_candidate_structure`、`candidate_boundary_violation`、`patch_application_failed`）的 error.message 必须脱敏：

- 不得返回：Provider 异常原文、instruction 内容、完整 document、完整候选 Patch
- 只返回类型化错误码和通用描述（如 `"Provider failed to generate a valid candidate"`）
- 在 `issues[]` 中可包含结构性定位信息（如 `"operations[0].targetNodeId"`），但不含值
- 目的：防止内部实现细节和用户数据通过错误响应泄露
- `internal_error` 响应同样不得直接暴露异常原文或本地路径

## Mock Provider 定义

```python
class MockProvider:
    """确定性 Mock，无网络、无随机。"""

    async def generate_patch(self, context: RefinementContext) -> dict:
        """
        确定性映射规则：
        - 根据 context.selected_node_type 选择合法文案字段
        - 如果 instruction 以 "set_text:" 开头，value = instruction[9:]
        - 否则 value = instruction
        """
        ...
```

### Mock Provider 确定性规则

根据 `selected_node_type` 选择返回的 props 字段：

| selected_node_type | 返回的 props 字段 |
|---|---|
| Heading | `{ "text": value }` |
| Text | `{ "text": value }` |
| Button | `{ "text": value }` |
| Page | `{ "title": value }` |
| Card | `{ "title": value }` |
| Section | `{ "ariaLabel": value }` |
| Image | `{ "alt": value }` |
| Form | `{ "name": value }` |
| Input | `{ "label": value }` |

value 计算规则：

- 如果 `instruction.startswith("set_text:")` → `value = instruction[9:]`
- 否则 → `value = instruction`

所有情况下，返回的 Patch 结构为：

```json
{
  "version": "0.1",
  "operations": [
    { "op": "update_props", "targetNodeId": "<context.selected_node_id>", "props": { "<field>": "<value>" } }
  ]
}
```

### 可注入的反向测试 Provider

| Provider | 行为 | 预期触发错误 |
|----------|------|-------------|
| `BrokenStructureProvider` | 返回非法 dict（缺少 version/operations） | `invalid_candidate_structure` |
| `WrongTargetProvider` | 返回指向其他节点 ID 的单个操作 | `candidate_boundary_violation` |
| `MultiTargetProvider` | 多 operation 中混入非选中节点 | `candidate_boundary_violation` |
| `InvalidResultProvider` | 返回会导致 DSL 非法的 props（如 level=99） | `patch_application_failed`（预期 HTTP 502） |

这些 Provider 仅用于测试，不随生产代码部署。可直接定义在测试文件中。

## Non-Target Zero-Change Verification Algorithm

```python
def verify_non_target_unchanged(
    original_doc: DslDocument,
    patched_doc: DslDocument,
    selected_node_id: str,
) -> bool:
    """
    完整性验证算法：
    1. 将 original_doc 和 patched_doc 各自序列化为规范化 dict
       （使用 model_dump(mode="json", by_alias=True)）
    2. 在两份 dict 中，找到 selectedNodeId 对应节点，仅移除其 `props` 字段
    3. 对两份处理后的完整 dict 做深等比较（==）
    4. 如果不等 → 返回 False

    覆盖范围：
    - metadata 不变
    - version 不变
    - root 结构不变
    - 目标节点的 id/type/style/children 不变（仅 props 允许变化）
    - 所有非目标节点的全部内容不变
    - 节点不能被增删
    """
    ...
```

算法复杂度：O(n)，其中 n 为序列化后 dict 的总大小。

关键语义：

- 使用 Pydantic model 的 `model_dump(mode="json", by_alias=True)` 序列化为规范化 dict。
- 仅移除目标节点的 `props` 字段，其余所有内容必须完全相等。
- 保证 metadata、version、root 结构、所有非目标节点全部字段均不变。
- 保证目标节点的 id、type、style、children 不变（仅 props 允许变化）。
- 节点总数必须相同（不允许增删节点）。

## 验收标准 (Acceptance Criteria)

### Provider 接口

| # | 标准 |
|---|------|
| AC-01 | `RefinementProvider` 使用 `typing.Protocol` 定义 |
| AC-02 | `RefinementProvider` 定义 `async def generate_patch(self, context: RefinementContext) -> dict` |
| AC-03 | `RefinementContext` 包含 instruction、selected_node_id、selected_node_type、selected_node_props、document_version |
| AC-04 | `RefinementContext` 不包含完整文档（最小权限） |
| AC-05 | 任何具有匹配签名的类自动满足 Protocol（无需显式继承） |

### Mock Provider

| # | 标准 |
|---|------|
| AC-06 | `MockProvider` 满足 `RefinementProvider` Protocol |
| AC-07 | `MockProvider` 为确定性：相同输入始终相同输出 |
| AC-08 | `MockProvider` 正确处理 "set_text:" 前缀 |
| AC-09 | `MockProvider` 根据 selected_node_type 选择正确的 props 字段 |
| AC-10 | `MockProvider` 默认行为使用 instruction 作为 value |

### Pipeline 正向

| # | 标准 |
|---|------|
| AC-11 | `refine()` 为无状态异步编排函数 |
| AC-12 | 正向流程：合法输入 → 返回 RefinementResult(success=True) |
| AC-13 | 返回的 patch 字段为已验证的候选 Patch dict |
| AC-14 | 返回的 document 字段为已验证的新 DSL Document dict |
| AC-15 | 返回的 integrity 字段包含 selectedNodeId 和 nonTargetNodesUnchanged=True（类型为 Literal[True]） |

### Pipeline 反向

| # | 标准 |
|---|------|
| AC-16 | 空 instruction → `invalid_instruction` |
| AC-17 | 纯空白 instruction → `invalid_instruction` |
| AC-18 | 超 1000 字符 instruction → `invalid_instruction` |
| AC-19 | 非法源文档 → `invalid_source_document` |
| AC-20 | selectedNodeId 不存在 → `target_node_not_found` |
| AC-21 | Provider 抛出异常 → `provider_error` |
| AC-22 | Provider 返回非法结构 → `invalid_candidate_structure` |
| AC-23 | 候选 Patch 指向其他节点 → `candidate_boundary_violation` |
| AC-24 | 多操作中混入非选中节点 → `candidate_boundary_violation` |
| AC-25 | apply_patch 因候选内容问题失败 → `patch_application_failed` |
| AC-26 | 非目标节点发生变化 → `non_target_mutation_detected` |

### Gold Case 与节点覆盖

| # | 标准 |
|---|------|
| AC-27 | Gold Case：使用 `examples/dsl/coffee-shop-landing.json` 的单节点文案精修端到端成功 |
| AC-28 | 根 Page 节点精修（title 修改）成功 |
| AC-29 | 深层叶子节点精修成功 |
| AC-30 | 9 种节点类型（Page/Section/Heading/Text/Button/Image/Card/Form/Input）的 Mock 字段映射各有至少一个正向测试 |

### API 正向

| # | 标准 |
|---|------|
| AC-31 | `POST /api/v1/dsl/refine` 端点存在且可访问 |
| AC-32 | 合法请求返回 HTTP 200 + `{ success: true, patch, document, integrity }` |
| AC-33 | 响应中 document 通过 `validate_dsl_document` 校验 |
| AC-34 | 响应中 patch 通过 `PatchDocument.model_validate` 校验 |
| AC-35 | integrity.nonTargetNodesUnchanged 为 true（schema 类型为 Literal[True]，即常量约束） |

### API 反向

| # | 标准 |
|---|------|
| AC-36 | Content-Type 非 JSON → 415 + `unsupported_media_type` |
| AC-37 | 空 body → 400 + `invalid_json` |
| AC-38 | 非法 JSON body（语法错误）→ 400 + `invalid_json` |
| AC-39 | 缺少必填字段 → 422 + `invalid_request_structure` |
| AC-40 | RefineRequest 拒绝额外字段 → 422 + `invalid_request_structure` |
| AC-41 | RefineRequest 正确解析 selectedNodeId alias（驼峰和下划线均可） |
| AC-42 | 空 instruction → 422 + `invalid_instruction` |
| AC-43 | 超长 instruction（>1000 字符）→ 422 + `invalid_instruction` |
| AC-44 | 非法源文档 → 422 + `invalid_source_document` |
| AC-45 | 节点不存在 → 422 + `target_node_not_found` |
| AC-46 | Provider 异常 → 502 + `provider_error` |
| AC-47 | `invalid_candidate_structure` → 502（BrokenStructureProvider 触发） |
| AC-48 | 候选越界（WrongTargetProvider）→ 502 + `candidate_boundary_violation` |
| AC-49 | MultiTargetProvider → 502 + `candidate_boundary_violation` |
| AC-50 | apply_patch 因候选问题失败 → 502 + `patch_application_failed` |
| AC-51 | `non_target_mutation_detected` → HTTP 500 |
| AC-52 | `internal_patch_error` → HTTP 500 + `internal_error` |
| AC-53 | 未预期异常 → HTTP 500 + `internal_error` |
| AC-54 | 错误响应格式为 `{ success: false, error: { code, message, issues[] } }` |
| AC-55 | 所有错误码与 Error Codes 表格一致（含 HTTP 状态码） |

### 输入不可变性

| # | 标准 |
|---|------|
| AC-56 | Pipeline 成功时原始 document 不变（深等于调用前的值） |
| AC-57 | Pipeline 失败时原始 document 不变（深等于调用前的值） |
| AC-58 | refine() 调用前后，传入的 instruction str 必须不变 |

### 恶意 Provider 防护

| # | 标准 |
|---|------|
| AC-59 | Provider 修改 `context.selected_node_props` 后原始 document 不变 |
| AC-60 | Pipeline 使用原始 selected_node_id 做边界检查，即使 Provider 修改了 `context.selected_node_id` |
| AC-61 | Provider 修改 context 后返回越界候选仍被 `candidate_boundary_violation` 拒绝 |

### Provider 注入

| # | 标准 |
|---|------|
| AC-62 | 默认 `app = create_app()` 使用 MockProvider |
| AC-63 | `create_app(custom_provider)` 使用指定 Provider |
| AC-64 | app A 的 `dependency_overrides` 不影响 app B |
| AC-65 | 清理一个 app 的 overrides 不影响其他实例 |

### 脱敏验证

| # | 标准 |
|---|------|
| AC-66 | Provider 错误响应不得包含 instruction 内容 |
| AC-67 | Provider 错误响应不得包含完整 document |
| AC-68 | Provider 错误响应不得包含候选 Patch |
| AC-69 | Provider 错误响应不得包含异常原文或本地路径 |

### 完整性算法精确性

| # | 标准 |
|---|------|
| AC-70 | 完整性算法使用 `model_dump(mode="json", by_alias=True)` |
| AC-71 | 完整性算法能发现 metadata 变化 |
| AC-72 | 完整性算法能发现 version 变化 |
| AC-73 | 完整性算法能发现目标节点 style 变化 |
| AC-74 | 完整性算法能发现目标节点 children 变化 |
| AC-75 | 完整性算法能发现目标节点 id/type 变化 |
| AC-76 | 完整性算法能发现非目标节点变化 |

### OpenAPI

| # | 标准 |
|---|------|
| AC-77 | GET /openapi.json 包含 /api/v1/dsl/refine 端点定义 |
| AC-78 | requestBody 存在、`required=true`、application/json schema 与 `RefineRequest.model_json_schema(by_alias=True)` 关键字段一致（必须包含 document、selectedNodeId、instruction；selectedNodeId 和 instruction 在 required 中；additionalProperties 为 false） |
| AC-79 | 200 响应 schema 引用 RefineSuccess |
| AC-80 | 400、415、422、500、502 响应 schema 引用 RefineFailure |
| AC-81 | patch、document、integrity 在 OpenAPI schema 中不是无约束 object |
| AC-82 | integrity.nonTargetNodesUnchanged 在 OpenAPI schema 中被约束为常量 true |

### Schema 导出一致性

| # | 标准 |
|---|------|
| AC-83 | contracts/dsl/v0.1/schema.json 文件未修改（git diff --exit-code 确认） |
| AC-84 | contracts/patch/v0.1/schema.json 文件未修改（git diff --exit-code 确认） |
| AC-85 | 现有 DSL Schema 导出一致性测试通过（test_schema_export.py） |
| AC-86 | 现有 Patch Schema 导出一致性测试通过（test_patch_schema.py） |

### 文档完整性

| # | 标准 |
|---|------|
| AC-87 | README.md 更新 M3 状态 |
| AC-88 | docs/ARCHITECTURE.md 更新 M3 模块与里程碑 |

### 回归无破坏

| # | 标准 |
|---|------|
| AC-89 | 后端全部测试通过（包含现有 213 个 + 新增测试） |
| AC-90 | 现有 API 端点行为未改变（/health、/api/v1/dsl/validate） |
| AC-91 | DSL/Patch Schema 文件未修改 |

### Git 检查

| # | 标准 |
|---|------|
| AC-92 | git diff --check 无空白错误 |

## 验证命令 (Verification Commands)

```bash
# 进入后端目录
cd backend

# 实现前基线确认（必须在编码前运行）
PYTHONPATH=src python3 -m pytest --tb=short -q  # 确认 213 测试通过

# 1. 全部测试通过
PYTHONPATH=src python3 -m pytest --tb=short -q

# 2. Provider 专项测试
PYTHONPATH=src python3 -m pytest tests/provider/ --tb=short -q

# 3. Pipeline 专项测试
PYTHONPATH=src python3 -m pytest tests/refinement/ --tb=short -q

# 4. Refine API 专项测试
PYTHONPATH=src python3 -m pytest tests/api/test_refine_api.py --tb=short -q

# 5. 契约无回归
PYTHONPATH=src python3 -m pytest tests/contracts/ --tb=short -q

# 6. 现有 API 无回归
PYTHONPATH=src python3 -m pytest tests/api/test_health.py tests/api/test_dsl_validation_api.py --tb=short -q

# 7. 验证 Provider 模块可导入
PYTHONPATH=src python3 -c "from genui_api.provider.base import RefinementProvider, RefinementContext; print('PROVIDER OK')"

# 8. 验证 Mock Provider 可导入
PYTHONPATH=src python3 -c "from genui_api.provider.mock import MockProvider; print('MOCK OK')"

# 9. 验证 Pipeline 可导入
PYTHONPATH=src python3 -c "from genui_api.refinement.pipeline import refine; print('PIPELINE OK')"

# 10. OpenAPI 综合检查
PYTHONPATH=src python3 -c "
from genui_api.main import create_app
from genui_api.api.schemas import RefineRequest
spec = create_app().openapi()
refine_path = spec['paths']['/api/v1/dsl/refine']
assert 'post' in refine_path, 'Missing POST method'
post = refine_path['post']
# 验证 requestBody 存在且 required
rb = post['requestBody']
assert rb.get('required') == True, f'requestBody not required: {rb}'
req_schema = rb['content']['application/json']['schema']
# 验证 schema 结构与 RefineRequest 一致
expected = RefineRequest.model_json_schema(by_alias=True)
assert 'selectedNodeId' in req_schema.get('properties', {}), f'Missing selectedNodeId: {req_schema}'
assert 'instruction' in req_schema.get('properties', {}), f'Missing instruction: {req_schema}'
assert 'document' in req_schema.get('properties', {}), f'Missing document: {req_schema}'
req_required = req_schema.get('required', [])
assert 'selectedNodeId' in req_required, f'selectedNodeId not required: {req_required}'
assert 'instruction' in req_required, f'instruction not required: {req_required}'
assert req_schema.get('additionalProperties') == False, f'additionalProperties not false: {req_schema}'
# 验证 200 响应
resp_200 = post['responses']['200']['content']['application/json']['schema']
assert 'RefineSuccess' in str(resp_200), f'200 schema: {resp_200}'
# 验证错误响应
for code in ['400', '415', '422', '500', '502']:
    resp = post['responses'][code]['content']['application/json']['schema']
    assert 'RefineFailure' in str(resp), f'{code} schema: {resp}'
# 验证 integrity 不是无约束 object
schemas = spec.get('components', {}).get('schemas', {})
integrity_schema = schemas.get('RefinementIntegrity', {})
props = integrity_schema.get('properties', {})
ntnu = props.get('nonTargetNodesUnchanged', {})
assert ntnu.get('const') == True or ntnu.get('enum') == [True], f'nonTargetNodesUnchanged not constrained: {ntnu}'
print('OPENAPI: all assertions passed')
"

# 11. DSL Schema 文件未变更（从 backend/ 执行，用 -C .. 回到仓库根）
git -C .. diff --exit-code -- contracts/dsl/v0.1/schema.json

# 12. Patch Schema 文件未变更
git -C .. diff --exit-code -- contracts/patch/v0.1/schema.json

# 13. 现有测试未变更
git -C .. diff --stat -- backend/tests/contracts/

# 14. Schema 导出一致性：DSL
PYTHONPATH=src python3 -m pytest tests/contracts/test_schema_export.py --tb=short -q

# 15. Schema 导出一致性：Patch
PYTHONPATH=src python3 -m pytest tests/contracts/test_patch_schema.py --tb=short -q

# 16. Git 空白检查
git -C .. diff --check

# 17. git status
git -C .. status --short

# 18. git diff stat
git -C .. diff --stat

# 19. 安全扫描：扫描 src 和新增测试，逐项复核
echo "=== Security Scan ==="
# 19a. 真实密钥读取检查（不得存在）
grep -rn "os\.environ\|os\.getenv\|dotenv" src/ tests/ && echo "REVIEW: env access found" || echo "OK: no env access"
# 19b. 危险函数检查（不得存在）
grep -rn "eval(\|exec(\|pickle\.\|subprocess\." src/ tests/ && echo "FAIL: dangerous function found" || echo "OK: no dangerous functions"
# 19c. 密钥模式检查（记录命中，人工复核）
grep -rn -E "(API_KEY|SECRET|PASSWORD|TOKEN|PRIVATE_KEY)\s*=" src/ tests/ && echo "REVIEW: potential secrets" || echo "OK: no secret patterns"
echo "=== End Security Scan ==="
```

## 审批闸门 (Approval Gates)

以下 10 项决策需要项目所有者批准：

| # | 决策项 | 内容 |
|---|--------|------|
| 1 | API 路径 | `POST /api/v1/dsl/refine` |
| 2 | 请求/成功响应模型 | 见本 Spec "Request Model"、"Response Models" 与 "API Endpoint" 章节 |
| 3 | 错误码表 | 12 个错误码，含 HTTP 状态码分层（422/502/500）+ PatchError 映射表（见 "Error Codes" 与 "PatchError 映射表" 章节） |
| 4 | Provider 接口签名 | `async def generate_patch(self, context: RefinementContext) -> dict` |
| 5 | Provider 注入方式 | `get_provider` 依赖 + `create_app(refinement_provider)` 参数注入 + `dependency_overrides` 测试注入（见 "Provider 注入" 章节精确代码） |
| 6 | non-target zero-change 验证算法 | 规范化 dict 深等比较，使用 `model_dump(mode="json", by_alias=True)`，移除目标节点 props 后全量对比 |
| 7 | Mock Provider 确定性行为规则 | 按 selected_node_type 选择字段 + set_text: 前缀解析 |
| 8 | Allowed Files 清单 | 见本 Spec "允许的文件" 章节 |
| 9 | 是否新增依赖 | 否，不引入任何新依赖 |
| 10 | AC 列表与验证命令 | 92 项 AC + 19 条验证命令 |

## 开放决策 (Open Decisions)

无。本轮所有技术决策已在本 Spec 中明确。

## 完成报告格式 (Completion Report Format)

按 AGENTS.md §10 固定格式输出，包含以下小节：

```text
## Result
## Repository State
## Files Created
## Files Modified
## Key Decisions Recorded
## Acceptance Criteria     （逐条 AC-01 ~ AC-92 标记 PASS / FAIL，附证据）
## Verification            （实际运行的 19 条命令与真实输出；未运行的写明"未运行"及原因）
## Scope Check             （是否安装未授权依赖/触碰范围外文件/删除文件）
## Open Decisions          （需所有者决定的问题；没有则写 None）
## Git Summary             （git status --short 与 git diff --stat）
## Recommended Next Task   （只提一个建议，不执行）
```

报告必须如实。没做的、没运行的，就直说。隐瞒失败的报告本身就是失败。
