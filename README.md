# GenUI 受控原型

一句话介绍：用户用自然语言生成并多轮精修网页的受控 GenUI 原型——页面由受控 JSON DSL 驱动，模型只能通过结构化 Patch 修改用户选中的控件，其余部分零漂移。

**当前状态**：M3-02 完成（前后端局部精修闭环）。前端已集成 `POST /api/v1/dsl/refine`：选中节点 → 输入 `set_text:` 指令 → 提交 → 完整性检查通过后整文档替换，非目标区域零变更。前端永不应用 `response.patch`（Patch 仅用于结果展示），完整性校验未通过的响应一律拒绝。Playwright E2E 覆盖真实前后端连续两轮精修。M4（多轮会话与指标）待启动。

## 核心原则

- DSL Document 是页面状态的唯一事实来源，模型只是候选修改的提案者；
- 一切模型输出必须经过确定性校验管线（Schema → 业务规则 → 边界 → 完整性）才能落地；
- Patch 只能作用于当前选中控件，非目标区域零变更且可证明；
- 没有 Spec 不动手；Spec 不放宽 AGENTS.md。

## 文档导航

| 文档 | 内容 |
|------|------|
| [AGENTS.md](AGENTS.md) | 项目长期契约：约束、审批闸门、执行协议（Agent 必读） |
| [docs/PRODUCT.md](docs/PRODUCT.md) | 产品边界：问题、用户、MVP 功能、指标、非目标 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构边界：数据流、校验管线、Provider/模板边界、里程碑 |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | 术语表 |
| [docs/adr/README.md](docs/adr/README.md) | 架构决策记录（ADR）规范 |
| [specs/README.md](specs/README.md) | 任务 Spec 规范 |
| [specs/000-project-foundation.md](specs/000-project-foundation.md) | M0 任务 Spec |
| [specs/001-dsl-contract-and-validation.md](specs/001-dsl-contract-and-validation.md) | M1-01 DSL 契约与校验核心 |
| [specs/002-dsl-validation-api.md](specs/002-dsl-validation-api.md) | M1-02 DSL 校验 API |
| [specs/003-controlled-patch-core.md](specs/003-controlled-patch-core.md) | M1-03 Controlled Patch 核心 |
| [specs/004-frontend-dsl-renderer-selection.md](specs/004-frontend-dsl-renderer-selection.md) | M2 前端 DSL 渲染器与选中交互 |
| [specs/005-refinement-pipeline-mock-provider-api.md](specs/005-refinement-pipeline-mock-provider-api.md) | M3-01 Refinement Pipeline + Mock Provider + Refine API |

## 计划中的技术栈

React + TypeScript + Vite（前端）· Python + FastAPI + Pydantic（后端）· 受控 JSON DSL + 结构化 Patch（协议）· 本地 JSON（存储）· Mock / 真实模型统一 Provider 接口（模型层）。

## 快速开始

### 后端安装

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 前端开发

```bash
cd frontend
npm install
npm run dev        # development server
npm run build      # production build
npm run typecheck  # TypeScript check
npm test           # run tests
```

M2 交付内容：渲染全部 9 种 DSL 组件（Page / Section / Heading / Text / Button / Image / Card / Form / Input）、点击/键盘节点选中、Info Panel 展示选中节点信息。

### 运行测试（后端）

```bash
cd backend
source .venv/bin/activate
pytest -v
```

#### Patch 核心测试

```bash
cd backend
python -m pytest tests/contracts/test_patch_models.py tests/contracts/test_patch_apply.py tests/contracts/test_patch_schema.py
```

### 本地启动

```bash
cd backend
source .venv/bin/activate
uvicorn genui_api.main:app --reload
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /api/v1/dsl/validate | DSL 文档校验 |
| POST | /api/v1/dsl/refine | 局部精修（Mock Provider） |

### Patch v0.1 最小示例

```json
{
  "version": "0.1",
  "operations": [
    {
      "op": "update_props",
      "targetNodeId": "node-btn-1",
      "props": { "text": "立即购买" }
    }
  ]
}
```

### Patch 核心 Python 调用示例

```python
from genui_api.patch.apply import apply_patch

source_doc = { ... }  # 合法的 DSL Document dict
patch = {
    "version": "0.1",
    "operations": [
        {"op": "update_props", "targetNodeId": "node-1", "props": {"text": "Hello"}}
    ]
}
patched = apply_patch(source_doc, patch)  # 返回校验通过的 DslDocument
```

> **注意**：Patch HTTP API 尚未实现。当前仅可通过 Python 函数调用 `apply_patch()`。

## 尚未实现

自由自然语言理解（当前仅支持 `set_text:` 前缀指令）、真实模型接入、多轮对话上下文、模板机制、指标面板、Undo/Redo——全部待后续 Spec 驱动开发。

## 下一里程碑

**M4 — 多轮会话与指标**：对话状态、Trace、指标采集与展示。详见 [docs/ARCHITECTURE.md §17](docs/ARCHITECTURE.md)。
