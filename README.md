# GenUI 受控原型

一句话介绍：用户用自然语言生成并多轮精修网页的受控 GenUI 原型——页面由受控 JSON DSL 驱动，模型只能通过结构化 Patch 修改用户选中的控件，其余部分零漂移。

**当前状态**：M4-01 完成（一句话生成网页初稿纵向切片）。顶部输入一句自然语言需求 → `POST /api/v1/dsl/generate` 经确定性 Mock Generation Provider 产出候选 DSL → 通过完整 Schema 与业务规则校验后返回初稿 → 前端原子替换渲染，随后可直接进入 M3-02 局部精修闭环（选中节点 → `set_text:` 指令 → `POST /api/v1/dsl/refine` → 完整性检查通过后整文档替换，非目标区域零变更）。前端永不本地拼装或修改 DSL，也永不应用 `response.patch`（Patch 仅用于结果展示）。Playwright E2E 覆盖真实前后端「生成 → 选择 → 精修」全链路。

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
| [specs/006-frontend-refinement-loop.md](specs/006-frontend-refinement-loop.md) | M3-02 前端局部精修闭环 |
| [specs/007-initial-dsl-generation.md](specs/007-initial-dsl-generation.md) | M4-01 一句话生成网页初稿纵向切片 |

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
| POST | /api/v1/dsl/generate | 一句话生成初稿（Mock Generation Provider） |
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

自由自然语言理解（生成侧当前为确定性关键词映射，精修侧仅支持 `set_text:` 前缀指令）、真实模型接入、SP/UP 提示词策略、多类 Patch、多轮对话上下文、模板推荐与自进化、指标面板、Undo/Redo——全部待后续 Spec 驱动开发。

## 里程碑路线

| 里程碑 | 最新定义 |
|--------|----------|
| M4 | 完成 PDF 任务一：一句话生成初稿、真实模型接入、SP/UP（系统提示词/用户提示词）策略、自然语言局部精修、多类 Patch、多轮上下文 |
| M5 | 完成 PDF 任务二：模板推荐、自进化、指标、个性化、冷启动 |
| M6 | 完整面试交付：覆盖矩阵、设计文档、架构图、Demo 脚本、追问题库、降级预案 |

M4 已交付的纵向切片：**M4-01 一句话生成网页初稿纵向切片**（本轮）。里程碑细节详见 [docs/ARCHITECTURE.md §17](docs/ARCHITECTURE.md)。
