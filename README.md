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

### 模型配置（Mock / 真实模型）

系统同时支持**确定性 Mock**与**真实模型**两条 Provider 实现，两者满足同一个 Provider Protocol，走**同一条校验管线**：

| GENUI_MODEL_PROVIDER | 行为 |
|---|---|
| 未设置 / `mock`（默认） | Mock Provider：完全离线、确定性、无凭证、无网络请求 |
| `openai_compatible` | 真实模型：通过 OpenAI 兼容的 Chat Completions 协议调用 |

> `openai_compatible` 描述的是**传输协议**，不是厂商。Qwen / 阿里云百炼、Kimi、DeepSeek、GLM 都通过该协议接入，因此环境变量全部使用 provider-neutral 命名（`GENUI_LLM_*`），不出现任何厂商前缀。

配置读取方式：应用**只读取进程环境变量**。本项目**不引入 `python-dotenv`**，因此 `.env` 文件**不会被自动加载**——[`.env.example`](.env.example) 的角色是**配置模板与文档**（列出变量名、含义与占位符），不是运行时配置源。

启用真实模型时，需把变量**导出到运行进程的环境**中，例如：

```bash
# 方式一：在当前 shell 中 export 后启动（同一 shell 内后续命令均可见）
export GENUI_MODEL_PROVIDER=openai_compatible
export GENUI_LLM_API_KEY=<API_KEY>
export GENUI_LLM_BASE_URL=<BASE_URL>
export GENUI_GENERATION_MODEL=<MODEL>
# 可选：精修侧单独指定模型，不设置时继承生成侧
# export GENUI_REFINEMENT_MODEL=<MODEL>
uvicorn genui_api.main:app --reload

# 方式二：只对单条命令生效（不污染 shell）
env GENUI_MODEL_PROVIDER=openai_compatible GENUI_LLM_API_KEY=<API_KEY> \
    GENUI_LLM_BASE_URL=<BASE_URL> GENUI_GENERATION_MODEL=<MODEL> \
    uvicorn genui_api.main:app --reload
```

开发环境推荐做法：复制 `.env.example` 为本地的 `.env`（已被 `.gitignore` 忽略，切勿提交凭证），再用**外部工具**把它注入进程环境——手动 `set -a && source .env && set +a`，或使用 `direnv` 等工具自动完成。注入责任在 shell / 工具侧，应用侧不做隐式文件读取。

`openai_compatible` 模式下 Key / BaseURL / Model 三项全部必需且**无默认模型名**；缺任一项在应用启动阶段即失败（fail fast），不会留到首个请求才暴露。

**首次 Demo 推荐使用阿里云百炼（Qwen 系列）**：国内网络直连稳定、OpenAI 兼容端点开箱可用、JSON 输出稳定性足以支撑本项目的结构化契约。BaseURL 与模型名请以所选厂商官方文档为准，不要混用不同厂商的端点与模型名。

真实模型 smoke 测试默认跳过，需显式 opt-in（会产生真实调用与费用）：

```bash
GENUI_RUN_REAL_LLM=1 pytest tests/llm/test_real_smoke.py -v
```

裸 `pytest` 恒为零真实网络调用：即使 shell 中已存在真实凭证，测试夹具也会剥离模型环境变量并跳过所有 `real_llm` 用例。

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /api/v1/dsl/validate | DSL 文档校验 |
| POST | /api/v1/dsl/generate | 一句话生成初稿（Mock 或真实模型，由 GENUI_MODEL_PROVIDER 决定） |
| POST | /api/v1/dsl/refine | 局部精修（Mock 或真实模型，由 GENUI_MODEL_PROVIDER 决定） |

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

多类 Patch（当前仅 `update_props`）、通过 Patch 修改节点 `style`、多轮对话上下文、模板推荐与自进化、指标面板、Undo/Redo——全部待后续 Spec 驱动开发。

真实模型已接入（M4-02），但前端 UI 仍不提供模型切换入口：切换靠环境变量。Mock Provider 保留为离线基线，不被真实模型替代。

## 里程碑路线

| 里程碑 | 最新定义 |
|--------|----------|
| M4 | 完成 PDF 任务一：一句话生成初稿、真实模型接入、SP/UP（系统提示词/用户提示词）策略、自然语言局部精修、多类 Patch、多轮上下文 |
| M5 | 完成 PDF 任务二：模板推荐、自进化、指标、个性化、冷启动 |
| M6 | 完整面试交付：覆盖矩阵、设计文档、架构图、Demo 脚本、追问题库、降级预案 |

M4 已交付的纵向切片：**M4-01 一句话生成网页初稿纵向切片**、**M4-02 真实模型接入与 SP/UP 提示词策略**（本轮）。里程碑细节详见 [docs/ARCHITECTURE.md §17](docs/ARCHITECTURE.md)。
