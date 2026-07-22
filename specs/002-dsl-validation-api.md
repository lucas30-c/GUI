# Spec 002 — DSL 校验 HTTP 接口（最小 FastAPI 应用）

## 目标 (Goal)

在 M1-01 已完成的 DSL v0.1 校验核心之上，建立一个最小、可测试、可运行的 FastAPI 应用，暴露稳定的 DSL 校验 HTTP 接口。

## 背景 (Context)

- 前置：M1-01 已交付（见 [001-dsl-contract-and-validation.md](001-dsl-contract-and-validation.md)）。
  - DSL v0.1 Pydantic 模型（9 种组件 + DslDocument）
  - 校验入口：`validate_dsl_json`（JSON 字符串 → DslDocument）、`validate_dsl_document`（dict → DslDocument）
  - 异常体系：`DslValidationError`（含 `errors: List[DslError]`，每条含 `path`/`code`/`message`）、`DslJsonParseError`、`DslError`
  - 99 个 pytest 全部通过
  - JSON Schema（`contracts/dsl/v0.1/schema.json`）
  - Gold Case（`examples/dsl/coffee-shop-landing.json`）
- 现有校验入口已能区分 JSON 解析失败（`DslJsonParseError`）与 DSL 校验失败（`DslValidationError`），且 `DslValidationError.errors` 中的 `code` 字段可进一步区分 `schema_error`（Pydantic 结构错误）和业务规则错误（`duplicate_id`/`invalid_nesting`/`invalid_root`）。
- 架构依据：[ARCHITECTURE.md](../docs/ARCHITECTURE.md) §3 后端职责、§12 错误处理原则、§13 测试策略。
- 本轮在 M1-01 之上建立 HTTP 薄适配层，不引入新的业务逻辑。

## 范围内 (In Scope)

1. 创建最小 FastAPI 应用（`create_app()` 工厂 + 模块级 `app`）
2. `GET /health` 健康检查端点
3. `POST /api/v1/dsl/validate` DSL 校验端点
4. 复用 M1-01 的 `validate_dsl_json` 作为校验核心
5. 确定性错误映射：区分 415、400、422(structure)、422(business)、500
6. 统一错误响应结构（`valid`/`error`/`issues`）
7. API 正向与反向测试
8. `pyproject.toml` 增加 `fastapi`/`uvicorn`/`httpx` 依赖
9. 最小文档更新

## 范围外 (Out of Scope)

- Patch Schema / Patch 应用
- Renderer / 前端
- 模型 Provider / Mock Provider
- 数据库 / 持久化
- 鉴权 / CORS / 限流
- WebSocket / SSE / 文件上传
- Docker / CI/CD
- 通用异常框架 / 日志框架 / 配置系统

## 允许的文件 (Allowed Files)

新建：

- `specs/002-dsl-validation-api.md`（本文件）
- `backend/src/genui_api/main.py`
- `backend/src/genui_api/api/__init__.py`
- `backend/src/genui_api/api/routes.py`
- `backend/src/genui_api/api/schemas.py`
- `backend/tests/api/__init__.py`
- `backend/tests/api/test_health.py`
- `backend/tests/api/test_dsl_validation_api.py`

修改：

- `backend/pyproject.toml`（最小增量添加依赖）
- `backend/src/genui_api/__init__.py`（如需要）
- `README.md`（最小更新）
- `docs/ARCHITECTURE.md`（最小更新）
- `docs/GLOSSARY.md`（如需新术语）
- `.gitignore`（如需新排除项）

## 禁止的变更 (Forbidden Changes)

- 不得修改 `contracts/dsl.py` 的模型定义
- 不得修改 `contracts/dsl/v0.1/schema.json`
- 不得删减 M1-01 测试（`tests/contracts/` 下的全部测试）
- 不得改变 DSL v0.1 合法输入范围
- 不得创建前端、数据库、模型 Provider
- 不得添加 `CORS allow_origins=["*"]`
- 不得引入未授权依赖（仅授权：fastapi、uvicorn、httpx）
- 不得在导入时访问外部资源（网络、数据库、文件系统 I/O）
- 不得使用 `eval`/`exec`/动态代码执行
- 不得删除文件

## 功能需求 (Functional Requirements)

### FR-1: FastAPI 应用入口

- `create_app() -> FastAPI` 工厂函数，位于 `backend/src/genui_api/main.py`
- 模块级 `app = create_app()`
- `genui_api.main:app` 可被 Uvicorn 导入并启动
- 不在导入时访问外部资源（网络、数据库、文件系统 I/O）
- 使用 APIRouter 组织路由，工厂内部 include

### FR-2: GET /health

- 返回 200 `{"status": "ok", "service": "genui-api"}`
- 有明确 Pydantic 响应模型（`HealthResponse`）
- 不返回系统信息（IP、版本号、环境变量、运行时细节）

### FR-3: POST /api/v1/dsl/validate 成功路径

- 接收 `application/json` 请求体
- 调用 `validate_dsl_json(raw_body)` 执行校验
- 成功返回 200：
  ```json
  {
    "valid": true,
    "document": { ... }
  }
  ```
- `document` 值来自 `DslDocument.model_dump(mode="json")`，确保确定性序列化

### FR-4: Content-Type 处理

- `application/json` 和 `application/json; charset=utf-8` 接受
- 检测逻辑：请求 `Content-Type` 头是否以 `"application/json"` 开头（忽略大小写）
- 其他媒体类型（如 `text/plain`、`multipart/form-data`、缺失 Content-Type）返回 415

### FR-5: 错误分类映射

| 场景 | HTTP 状态码 | error.code |
|------|-------------|-----------|
| Content-Type 非 JSON | 415 | `unsupported_media_type` |
| 空 body / JSON 语法错误 | 400 | `invalid_json` |
| Pydantic 结构校验失败 | 422 | `invalid_dsl_structure` |
| 业务规则校验失败 | 422 | `invalid_dsl_business_rule` |
| 未预期内部错误 | 500 | `internal_error` |

### FR-6: 错误响应结构

所有错误响应统一为以下结构：

```json
{
  "valid": false,
  "error": {
    "code": "<error_code>",
    "message": "<human-readable summary>",
    "issues": [
      {
        "path": "<node path>",
        "code": "<issue-level code>",
        "message": "<detail>"
      }
    ]
  }
}
```

- `error.code`：顶层错误分类（见 FR-5 表格）
- `error.message`：一句话人类可读摘要
- `error.issues`：错误明细列表；对 400/415/500 为空列表 `[]`
- `issues[].path`：保留 M1-01 已有的 path 格式（如 `"root.children[0].props.text"`）

### FR-7: 区分 schema_error 与业务错误

分类逻辑基于 `DslValidationError.errors` 中每条 `DslError.code`：

- 如果**全部** `code` 为 `"schema_error"` → HTTP 422，`error.code = "invalid_dsl_structure"`
- 如果含有 `"duplicate_id"` / `"invalid_nesting"` / `"invalid_root"` → HTTP 422，`error.code = "invalid_dsl_business_rule"`
- 混合场景（同时含 schema_error 与业务错误）：归为 `invalid_dsl_business_rule`（业务错误优先级更高，因为通常意味着结构已部分解析成功但语义非法）

实现说明：判断 `DslValidationError.errors` 中是否存在任一 `code ∉ {"schema_error"}` 的条目：
- 存在 → `invalid_dsl_business_rule`
- 不存在 → `invalid_dsl_structure`

### FR-8: 安全要求

- 错误响应不得返回 Python traceback
- 错误响应不得返回文件路径或环境变量
- 错误响应不得返回完整原始 input（请求体）
- 500 响应只作为安全兜底，message 固定为通用文案（如 "内部服务器错误"），不泄露具体异常信息

### FR-9: 空 body 处理

- 路由读取原始 body（`await request.body()`）
- body 为空（长度 0）时，返回 400 `invalid_json`，message 说明"请求体为空"
- 不依赖 FastAPI 默认的 body 解析行为（避免 422 由框架直接抛出）

## 设计决策 (Design Decisions)

以下决策在本 Spec 中明确记录，作为实现的约束：

| # | 决策 | 理由 |
|---|------|------|
| DD-1 | 错误分类边界：`DslValidationError.errors` 中 code 全为 `schema_error` → `invalid_dsl_structure`；含 `duplicate_id`/`invalid_nesting`/`invalid_root` → `invalid_dsl_business_rule` | M1-01 已在 `DslError.code` 中区分这两类，HTTP 层直接映射 |
| DD-2 | path 格式直接传递 M1-01 已有格式（如 `root.children[0].props.text`） | 避免引入转换逻辑；path 格式已在 99 个测试中稳定 |
| DD-3 | 成功响应序列化使用 `DslDocument.model_dump(mode="json")` | 确保确定性（Pydantic v2 mode="json" 保证 JSON 兼容序列化） |
| DD-4 | Content-Type 检测：检查请求头是否以 `"application/json"` 开头（忽略大小写） | 兼容 `application/json; charset=utf-8` 等合法变体 |
| DD-5 | 空 body 返回 400 `invalid_json`，不走 FastAPI 默认 body 解析 | 给用户明确的错误提示；与 JSON 语法错误归同类，因为本质都是"无法得到有效 JSON" |

## 验收标准 (Acceptance Criteria)

| # | 标准 | 验证方式 |
|---|------|---------|
| AC-1 | 本 Spec 完整存在且与 AGENTS.md / ARCHITECTURE.md 一致 | 人工审查 |
| AC-2 | `create_app()` 可独立创建 FastAPI 应用实例 | 代码导入测试 |
| AC-3 | `genui_api.main:app` 可导入且为 FastAPI 实例 | `python -c "from genui_api.main import app; print(type(app))"` |
| AC-4 | `GET /health` 返回 200 固定响应 `{"status": "ok", "service": "genui-api"}` | pytest |
| AC-5 | `POST /api/v1/dsl/validate` 校验合法 DSL 返回 200 `{"valid": true, "document": {...}}` | pytest |
| AC-6 | Gold Case（coffee-shop-landing.json）通过 HTTP 接口真实校验 | pytest 读取文件并 POST |
| AC-7 | 成功响应中 `document` 来自 `model_dump(mode="json")`，结构完整 | pytest 断言字段 |
| AC-8 | Content-Type 非 JSON 返回 415 `unsupported_media_type` | pytest |
| AC-9 | 空 body / 非法 JSON 返回 400 `invalid_json` | pytest |
| AC-10 | Pydantic 结构错误返回 422 `invalid_dsl_structure` | pytest |
| AC-11 | 业务规则错误返回 422 `invalid_dsl_business_rule` | pytest |
| AC-12 | 重复 ID 场景保留 `duplicate_id` 问题码在 `issues[].code` 中 | pytest 断言 issues |
| AC-13 | 错误响应包含可定位 `path`（如 `root.children[0]`） | pytest 断言 issues[].path 非空 |
| AC-14 | 错误响应不含 traceback、系统路径、完整原始 input | pytest + grep 扫描 |
| AC-15 | API 未复制或绕过 M1-01 校验逻辑（直接调用 `validate_dsl_json`） | 代码审查 |
| AC-16 | OpenAPI 文档中存在 `/health` 和 `/api/v1/dsl/validate` 两个端点及响应模型 | pytest 检查 `app.openapi()` |
| AC-17 | API 测试充分覆盖关键边界（≥15 个测试用例） | `pytest tests/api/ -v` 计数 |
| AC-18 | M1-01 全部测试继续通过 | `pytest tests/contracts/ -v` 全绿 |
| AC-19 | `schema.json` 与模型一致（M1-01 导出测试通过） | `pytest tests/contracts/test_schema_export.py` |
| AC-20 | Gold Case 仍通过底层校验 | `pytest tests/contracts/test_dsl_valid.py` |
| AC-21 | 只引入授权依赖（fastapi、uvicorn、httpx） | 审查 pyproject.toml diff |
| AC-22 | 未实现 Patch/Renderer/模型/数据库/前端 | 代码审查 |
| AC-23 | 未删除或覆盖已有内容 | git diff 检查 |
| AC-24 | 未修改范围外文件 | git diff 检查 |
| AC-25 | README 启动命令与实际一致 | 手动验证 |
| AC-26 | 验证结果如实记录 | 完成报告 |

## 验证命令 (Verification Commands)

```bash
# 进入后端目录并激活虚拟环境
cd backend && source .venv/bin/activate

# 安装依赖（含新增的 fastapi/uvicorn/httpx）
pip install -e ".[dev]"

# 1. 运行全部测试（M1-01 + API 测试）
pytest -v

# 2. 单独运行 M1-01 测试（确保无回归）
pytest tests/contracts/ -v

# 3. 单独运行 API 测试
pytest tests/api/ -v

# 4. 验证 app 可导入
python -c "from genui_api.main import app; print(type(app))"

# 5. 验证 health 端点
python -c "
from genui_api.main import create_app
from fastapi.testclient import TestClient
client = TestClient(create_app())
r = client.get('/health')
assert r.status_code == 200
assert r.json() == {'status': 'ok', 'service': 'genui-api'}
print('HEALTH OK:', r.json())
"

# 6. 验证 Gold Case 通过 HTTP 接口
python -c "
import pathlib
from genui_api.main import create_app
from fastapi.testclient import TestClient
client = TestClient(create_app())
body = pathlib.Path('../examples/dsl/coffee-shop-landing.json').read_text()
r = client.post('/api/v1/dsl/validate', content=body, headers={'content-type': 'application/json'})
assert r.status_code == 200
assert r.json()['valid'] is True
print('GOLD CASE HTTP OK')
"

# 7. 测试计数（确保 ≥15 个 API 测试）
pytest tests/api/ --collect-only -q | tail -1

# 8. 危险/越界内容扫描
grep -rn -E "eval\(|exec\(|javascript:|allow_origins" backend/src/ || echo "OK: clean"
```

## 审批闸门 (Approval Gates)

- **引入新依赖**：fastapi、uvicorn、httpx —— 已获本轮任务书授权。
- **修改公开 API**：本轮首次暴露 HTTP 接口 —— 已获本轮任务书授权。

## 完成报告 (Completion Report)

按 AGENTS.md §10 固定格式输出，并逐条对照本 Spec 的 26 项验收标准标记 PASS / FAIL 附证据。
