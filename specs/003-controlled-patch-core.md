# Spec 003 — Controlled Patch v0.1 契约与确定性应用核心

## 目标 (Goal)

定义 Patch v0.1 数据契约（Pydantic 模型 + 结构校验），实现确定性的 Patch 校验与应用核心，为后续 Patch HTTP 接口和模型集成提供可靠的局部更新基础设施。

## 背景 (Context)

- 前置：M1-01 已交付（见 [001-dsl-contract-and-validation.md](001-dsl-contract-and-validation.md)）。
  - DSL v0.1 Pydantic 模型（9 种组件 + DslDocument）
  - 校验入口：`validate_dsl_document(data: dict) -> DslDocument`
  - 异常体系：`DslValidationError(errors: List[DslError])`、`DslJsonParseError(message: str)`
  - `DslError`：`@dataclass` with fields `path: str`, `code: str`, `message: str`
  - 错误码：`schema_error`、`duplicate_id`、`invalid_nesting`、`invalid_root`
  - 所有模型 `model_config = ConfigDict(extra="forbid")`
  - NodeId 格式：`^[a-z][a-z0-9]*(?:[.\-][a-z0-9]+)*$`，最大 128 字符
  - JSON Schema：`contracts/dsl/v0.1/schema.json`
  - Gold Case：`examples/dsl/coffee-shop-landing.json`
- 前置：M1-02 已交付（见 [002-dsl-validation-api.md](002-dsl-validation-api.md)）。
  - FastAPI 应用 + DSL 校验 HTTP 端点
  - 统一错误响应结构（`valid`/`error`/`issues`）
- 架构依据：[ARCHITECTURE.md](../docs/ARCHITECTURE.md) §4 共享契约、§12 错误处理原则、§13 测试策略。
- 本轮在 M1-01 校验核心之上建立 Patch 契约与应用层，不引入 HTTP 接口。

## 范围内 (In Scope)

1. Patch v0.1 数据模型（Pydantic v2 严格模型，`extra="forbid"`）
2. Patch 自校验（结构合法性、字段约束）
3. Patch 应用核心：节点定位 + props 浅合并 + 多操作顺序执行
4. 原始文档不可变性保证（深拷贝）
5. 原子性语义：全部成功或全部失败
6. 应用后 DSL 校验（复用 M1-01 `validate_dsl_document`）
7. 5 类稳定错误码与结构化错误响应
8. Patch JSON Schema 确定性导出
9. ≥55 个 pytest 覆盖正向/反向/回归场景
10. Gold Case 上的 Patch 应用正向验证

## 范围外 (Out of Scope)

- Patch HTTP API（不建立任何路由/端点）
- React/Vite 前端与 DSL Renderer
- 模型 Provider / Mock Provider / 真实模型调用
- RFC 6902 JSON Patch 兼容
- 节点增删移操作（`add`/`remove`/`move`）——v0.1 仅支持 `update_props`
- 数据库 / 持久化
- Docker / CI/CD
- TypeScript 类型生成
- 模板推荐
- 深合并（deep merge）语义

## 允许的文件 (Allowed Files)

新建：

- `specs/003-controlled-patch-core.md`（本文件）
- `backend/src/genui_api/patch/__init__.py`
- `backend/src/genui_api/patch/models.py`
- `backend/src/genui_api/patch/apply.py`
- `backend/src/genui_api/patch/schema_export.py`
- `backend/tests/contracts/test_patch_models.py`
- `backend/tests/contracts/test_patch_apply.py`
- `backend/tests/contracts/test_patch_schema.py`
- `contracts/patch/v0.1/schema.json`

最小修改：

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/GLOSSARY.md`

## 禁止的变更 (Forbidden Changes)

- 引入 pydantic(v2) 与 pytest 之外的任何新依赖
- 实现 Patch HTTP 路由 / HTTP 入口 / 前端 / Renderer / Provider / 数据库
- 修改 `contracts/dsl.py` 的现有模型定义
- 修改 `contracts/dsl/v0.1/schema.json`
- 删减 M1-01/M1-02 测试
- 改变 DSL v0.1 合法输入范围
- 使用 `eval`/`exec`/`pickle`/动态代码执行
- 在错误消息中泄露 traceback、文件路径、环境变量
- 在错误消息中包含完整原始文档或 Patch 内容
- 删除文件
- 为"未来可能需要"建立复杂抽象
- 在实现过程中擅自降低本 Spec 的验收标准

## 功能需求 (Functional Requirements)

### FR-1: Patch v0.1 数据结构

Patch 文档顶层结构：

```json
{
  "version": "0.1",
  "operations": [
    {
      "op": "update_props",
      "targetNodeId": "hero-title",
      "props": { "text": "新的标题" }
    }
  ]
}
```

- `version`：固定字符串 `"0.1"`
- `operations`：非空数组，每个元素为一个操作对象
- 操作对象字段：`op`（操作类型）、`targetNodeId`（目标节点 ID）、`props`（待合并属性）

### FR-2: Patch 操作语义

- `version` 必须精确等于 `"0.1"`
- `operations` 必须为非空数组（空数组拒绝）
- v0.1 仅支持 `op = "update_props"`，其他值拒绝
- `targetNodeId` 必须为非空有效字符串（拒绝空串、纯空白字符串）
- `props` 必须为非空 JSON 对象（拒绝空对象 `{}`、非对象值）
- 浅合并语义：`new_props = {**old_props, **patch_props}`
- 未出现在 patch 中的字段保持不变
- 无删除语义；`null` 是合法 JSON 值（其合法性由目标组件的 props 模型在后续 DSL 校验中决定）
- 不执行递归深合并

### FR-3: 节点定位规则

- 从 `Document.root` 开始递归遍历整棵树
- 按 `node.id` 精确匹配 `targetNodeId`
- 必须能定位任意有效深度的节点
- 未找到目标节点 → 返回稳定错误（`patch_target_not_found`）
- 不做模糊匹配
- 不做基于类型的猜测
- 不做基于数组下标的定位

### FR-4: Props 合并语义

- 浅字段合并：仅合并顶层 key
- 不执行嵌套对象的深合并
- 示例：若原始 props 为 `{"text": "Hello", "variant": "primary"}`，patch props 为 `{"text": "World"}`，结果为 `{"text": "World", "variant": "primary"}`

### FR-5: 多操作执行顺序

- 操作按 `operations` 数组顺序逐一执行
- 同一节点可出现在多个操作中
- 后续操作对同一字段的修改确定性覆盖前一次结果（last writer wins）
- 不并行执行
- 不使用集合/无序 map 遍历

### FR-6: 冲突处理

- 确定性策略：顺序执行中后写者获胜（last writer wins）
- 无需额外冲突检测或合并逻辑

### FR-7: 原始文档不可变性

- Patch 应用在原始文档的深拷贝上执行
- 无论成功或失败，原始文档对象保持不变
- 禁止使用 `model_copy(deep=False)`（浅拷贝不满足不可变性）
- 禁止使用 JSON 字符串序列化/反序列化作为**唯一**深拷贝机制（性能与精度问题）
- 推荐：`model_copy(deep=True)` 或等效确定性深拷贝方式

### FR-8: 原子性

- 全部操作成功 **且** 最终 DSL 校验通过 → 返回新文档
- 任何步骤失败 → 整个 Patch 失败，不返回部分结果
- 不存在"部分应用"的中间状态对外暴露

### FR-9: Patch 自校验

- 使用 Pydantic v2 模型，配置 `model_config = ConfigDict(extra="forbid")`
- 拒绝未知顶层字段
- 拒绝未知操作字段
- 拒绝未知 `op` 值（v0.1 仅允许 `"update_props"`）
- 拒绝空 `operations` 数组
- 拒绝空字符串或纯空白字符串的 `targetNodeId`
- 拒绝空 `props`（空对象 `{}`）
- 拒绝 `props` 中的非 JSON 兼容值

### FR-10: Patch 应用错误体系

5 类顶层错误码：

| 错误码 | 含义 |
|--------|------|
| `invalid_patch_structure` | Patch 自身结构非法（FR-9 校验失败） |
| `invalid_source_document` | 输入的 DSL 源文档未通过 M1-01 校验 |
| `patch_target_not_found` | `targetNodeId` 在文档中不存在 |
| `invalid_patched_document` | Patch 已应用但结果未通过 DSL 校验 |
| `internal_patch_error` | 非预期运行时错误（安全兜底） |

每个错误包含：
- `code`：顶层错误码（上表之一）
- `message`：人类可读摘要
- `issues`：明细列表，每条含 `code`、`path`、`message`

### FR-11: 应用后 DSL 校验

- Patch 应用完成后，**必须**调用 M1-01 的 `validate_dsl_document()` 对结果文档进行完整校验
- Patch 层**不**复制任何 DSL 校验规则
- 若后校验失败 → 返回 `invalid_patched_document` 错误，issues 中保留 DSL 校验返回的原始错误信息

### FR-12: 错误分类与稳定 issue.code

- 顶层 `code` 为 FR-10 定义的 5 类之一
- `invalid_patch_structure` 内的 `issue.code`：提供具体子码（如 `empty_operations`、`invalid_op`、`empty_target_node_id`、`empty_props`、`unknown_field` 等）
- Patch 错误的 `issue.path` 格式：`operations[N].fieldName`（如 `operations[0].targetNodeId`、`operations[1].props`）
- 后校验 DSL 错误的 `issue.path`：原样保留 DSL 校验格式（如 `root.children[0].props.text`）
- 必须区分"输入文档本身非法"（`invalid_source_document`）与"Patch 后文档非法"（`invalid_patched_document`）

### FR-13: JSON Schema 导出

- 从 Pydantic Patch 模型自动生成
- 存储位置：`contracts/patch/v0.1/schema.json`
- 确定性导出：`sort_keys=True`、`indent=2`、末尾换行
- 必须包含 `x-patch-version: "0.1"` 元数据
- 测试验证：当前模型导出与已提交 schema 逐字节一致

### FR-14: 安全边界

- 不使用 `eval`/`exec`/`pickle`
- 错误消息不泄露 traceback 或文件路径
- 错误消息不包含完整文档或完整 Patch 内容
- 所有模型输出视为不受信任的输入（Patch 来自外部，必须经过完整校验）

### FR-15: 测试策略

至少 55 个测试，分类覆盖：

| 分类 | 最少数量 | 覆盖重点 |
|------|----------|---------|
| Patch 模型正向 | 5+ | 合法 Patch 结构解析、多操作、边界值 |
| Patch 模型反向 | 17+ | 未知字段、非法 op、空 operations、空 targetNodeId、空 props、非法 version 等 |
| Patch 应用正向 | 12+ | 单操作/多操作/同节点多操作/深层节点/Gold Case Patch |
| Patch 应用反向 | 14+ | 目标不存在、源文档非法、Patch 后文档非法、各类边界 |
| 回归测试 | 7+ | 原始文档不可变性、原子性、执行顺序确定性、后校验集成 |

所有测试使用真实 DSL 模型和 Gold Case，不 mock 核心校验逻辑。

## 设计决策 (Design Decisions)

| # | 决策 | 理由 |
|---|------|------|
| DD-1 | v0.1 仅支持 `update_props`，不支持 `add`/`remove`/`move` | 最小可行范围；结构变更复杂度高，留待后续版本 |
| DD-2 | 浅合并而非深合并 | 确定性、可预测性优先；深合并语义在嵌套场景下歧义大 |
| DD-3 | last writer wins，无冲突检测 | 顺序执行天然确定性；复杂冲突策略属过度设计 |
| DD-4 | 深拷贝保证不可变性 | Pydantic `model_copy(deep=True)` 已提供可靠机制 |
| DD-5 | 后校验复用 `validate_dsl_document` | 单一事实来源；Patch 层不重复实现 DSL 规则 |
| DD-6 | 错误体系设 5 类顶层码 + issues 明细 | 与 M1-02 错误响应结构对齐，便于后续 HTTP 层直接映射 |
| DD-7 | `null` 在 props 中为合法 JSON 值 | 是否被目标组件接受由 DSL 模型决定，Patch 层不预判 |

## 验收标准 (Acceptance Criteria)

| # | 标准 |
|---|------|
| AC-01 | 本 Spec 完整存在且与 AGENTS.md / ARCHITECTURE.md 一致 |
| AC-02 | Patch v0.1 Pydantic 模型存在，配置 `extra="forbid"` |
| AC-03 | Patch 模型仅接受 `version = "0.1"` |
| AC-04 | Patch 模型仅接受 `op = "update_props"` |
| AC-05 | Patch 模型拒绝空 `operations` 数组 |
| AC-06 | Patch 模型拒绝空字符串/纯空白 `targetNodeId` |
| AC-07 | Patch 模型拒绝空 `props`（`{}`） |
| AC-08 | Patch 模型拒绝未知顶层字段 |
| AC-09 | Patch 模型拒绝未知操作字段 |
| AC-10 | Patch 模型拒绝非法 `op` 值 |
| AC-11 | Patch 应用正确定位 root 直接子节点 |
| AC-12 | Patch 应用正确定位任意深度嵌套节点 |
| AC-13 | Patch 应用执行浅合并（仅顶层 key） |
| AC-14 | Patch 应用不执行深合并 |
| AC-15 | 未出现在 patch 中的 props 字段保持不变 |
| AC-16 | 多操作按数组顺序执行 |
| AC-17 | 同一节点多操作后写者覆盖前写者 |
| AC-18 | 原始文档在 Patch 成功后未被修改 |
| AC-19 | 原始文档在 Patch 失败后未被修改 |
| AC-20 | Patch 全部操作成功且后校验通过才返回新文档 |
| AC-21 | 任一操作失败则整个 Patch 失败，无部分结果 |
| AC-22 | 后校验失败则整个 Patch 失败，无部分结果 |
| AC-23 | 后校验调用 M1-01 的 `validate_dsl_document()` |
| AC-24 | Patch 层不重复实现任何 DSL 校验规则 |
| AC-25 | `patch_target_not_found` 错误码在节点不存在时返回 |
| AC-26 | `invalid_patch_structure` 错误码在 Patch 结构非法时返回 |
| AC-27 | `invalid_source_document` 错误码在源文档非法时返回 |
| AC-28 | `invalid_patched_document` 错误码在后校验失败时返回 |
| AC-29 | `internal_patch_error` 作为安全兜底存在 |
| AC-30 | 错误包含 `code`、`message`、`issues` 三个字段 |
| AC-31 | `issues` 中每条含 `code`、`path`、`message` |
| AC-32 | Patch 错误的 `issue.path` 使用 `operations[N].fieldName` 格式 |
| AC-33 | 后校验错误的 `issue.path` 保留 DSL 校验原始格式 |
| AC-34 | 可区分"源文档非法"与"Patch 后文档非法" |
| AC-35 | `null` 在 props 中被接受（合法性由后校验决定） |
| AC-36 | 不使用 `model_copy(deep=False)` |
| AC-37 | 不使用 JSON 字符串往返作为唯一深拷贝机制 |
| AC-38 | Patch JSON Schema 由 Pydantic 模型导出 |
| AC-39 | Schema 存储于 `contracts/patch/v0.1/schema.json` |
| AC-40 | Schema 导出确定性（sort_keys + indent=2 + 末尾换行） |
| AC-41 | Schema 包含 `x-patch-version: "0.1"` |
| AC-42 | 测试验证导出 schema 与已提交文件一致 |
| AC-43 | 不使用 `eval`/`exec`/`pickle` |
| AC-44 | 错误消息不泄露 traceback/文件路径 |
| AC-45 | 错误消息不包含完整文档/Patch 内容 |
| AC-46 | ≥55 个测试覆盖全部分类 |
| AC-47 | 测试使用真实 DSL 模型和 Gold Case |
| AC-48 | M1-01 / M1-02 全部测试继续通过（无回归） |
| AC-49 | 未引入未授权依赖 |
| AC-50 | 未实现本轮范围外功能（HTTP API/前端/Renderer/Provider/数据库） |
| AC-51 | 未删除或覆盖已有内容 |

## 验证命令 (Verification Commands)

```bash
# 进入后端目录并激活虚拟环境
cd backend && source .venv/bin/activate

# 安装依赖
pip install -e ".[dev]"

# 1. 运行全部测试（M1-01 + M1-02 + Patch 测试）
pytest -v

# 2. 单独运行 M1-01 测试（确保无回归）
pytest tests/contracts/test_dsl_valid.py tests/contracts/test_dsl_invalid.py tests/contracts/test_schema_export.py -v

# 3. 单独运行 M1-02 API 测试（确保无回归）
pytest tests/api/ -v

# 4. 单独运行 Patch 测试
pytest tests/contracts/test_patch_models.py tests/contracts/test_patch_apply.py tests/contracts/test_patch_schema.py -v

# 5. 测试计数（确保 ≥55 个 Patch 测试）
pytest tests/contracts/test_patch_models.py tests/contracts/test_patch_apply.py tests/contracts/test_patch_schema.py --collect-only -q | tail -1

# 6. 验证 Patch 模型可导入
python -c "from genui_api.patch.models import PatchDocument, PatchOperation; print('PATCH MODELS OK')"

# 7. 验证 Patch 应用入口可导入
python -c "from genui_api.patch.apply import apply_patch; print('PATCH APPLY OK')"

# 8. 验证 Gold Case Patch 应用
python -c "
import json, pathlib
from genui_api.contracts.validation import validate_dsl_document
from genui_api.patch.apply import apply_patch

doc_data = json.loads(pathlib.Path('../examples/dsl/coffee-shop-landing.json').read_text())
patch_data = {
    'version': '0.1',
    'operations': [
        {'op': 'update_props', 'targetNodeId': 'hero-title', 'props': {'text': '新咖啡店'}}
    ]
}
result = apply_patch(doc_data, patch_data)
print('GOLD CASE PATCH OK')
"

# 9. 重新导出 Patch JSON Schema 并检查确定性
python -m genui_api.patch.schema_export /tmp/patch_schema_a.json
python -m genui_api.patch.schema_export /tmp/patch_schema_b.json
diff /tmp/patch_schema_a.json /tmp/patch_schema_b.json && diff /tmp/patch_schema_a.json ../contracts/patch/v0.1/schema.json

# 10. 危险/越界内容扫描
grep -rn -E "eval\(|exec\(|pickle|javascript:|onClick|rawHtml" backend/src/ || echo "OK: clean"
```

## 审批闸门 (Approval Gates)

- **无新依赖引入**：本轮仅使用已授权的 pydantic(v2) 与 pytest。
- **新建 Patch 子模块**：`backend/src/genui_api/patch/` —— 已获本轮任务书授权。
- **新建 Patch Schema**：`contracts/patch/v0.1/schema.json` —— 已获本轮任务书授权。

## 开放决策 (Open Decisions)

无。本轮所有技术决策已在本 Spec 中明确。

## 完成报告 (Completion Report)

按 AGENTS.md §10 固定格式输出，并逐条对照本 Spec 的 51 项验收标准标记 PASS / FAIL 附证据。
