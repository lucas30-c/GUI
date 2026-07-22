# GenUI 受控原型

一句话介绍：用户用自然语言生成并多轮精修网页的受控 GenUI 原型——页面由受控 JSON DSL 驱动，模型只能通过结构化 Patch 修改用户选中的控件，其余部分零漂移。

**当前状态**：M1-03 完成（Controlled Patch 核心已就绪；DSL 契约、校验核心、HTTP 校验端点、Patch 应用引擎均可用）。Patch HTTP API 尚未实现。

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

### 运行测试

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

前端应用、Patch HTTP API、模型接入、模板机制、指标面板——全部待后续 Spec 驱动开发。

## 下一里程碑

**M2 — 前端骨架 + 渲染 + 选中交互**：可渲染静态 DSL、可选中控件。详见 [docs/ARCHITECTURE.md §17](docs/ARCHITECTURE.md)。
