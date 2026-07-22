# Spec 001 — DSL v0.1 契约与确定性校验核心

## 目标 (Goal)

建立可被确定性代码验证的 DSL v0.1 契约（Pydantic 模型 + 业务规则校验 + 可导出 JSON Schema），为后续 React Renderer、选中状态和局部 Patch 提供唯一数据基础。

## 背景 (Context)

- 前置：M0 已完成项目契约与文档（见 [000-project-foundation.md](000-project-foundation.md)）。
- 架构依据：[ARCHITECTURE.md](../docs/ARCHITECTURE.md) §4 共享契约、§5 DSL 文档模型、§6 组件注册表、§13 测试策略。
- 本轮只解决 DSL 契约和确定性校验，属于里程碑 M1 的第一步。
- 本轮不决定 TypeScript 类型生成方案（待决策项 D4 保持开放，仅确定"schema.json 由 Pydantic 模型导出、不做第二套手写事实来源"）。

## 范围内 (In Scope)

- DSL Document 与九种固定组件的 Pydantic v2 严格数据模型；
- 结构化 Schema 校验（Pydantic 负责）与跨节点业务规则校验（Python 负责：全局 ID 唯一性、组件嵌套矩阵）；
- 稳定节点 ID 的格式与唯一性校验；
- 受控 style 白名单模型；
- 咖啡店落地页 Gold Case；
- 从 Pydantic 模型确定性导出 JSON Schema；
- 正向 + 反向 pytest；
- 稳定校验入口 `validate_dsl_document` / `validate_dsl_json`。

## 范围外 (Out of Scope)

- React/Vite 前端与 DSL Renderer；
- 控件点击、框选与选中状态（selectedNodeId）；
- Patch Schema 与 Patch 应用逻辑、非目标节点哈希校验；
- FastAPI 路由与任何 HTTP 服务入口；
- 模型 Provider / Mock Provider / 真实模型调用；
- 模板推荐；
- 数据库、CI/CD、Docker；
- TypeScript 类型生成；
- 任意 HTML、JavaScript 或 React 代码生成。

## 允许的文件 (Allowed Files)

新建：

- `specs/001-dsl-contract-and-validation.md`（本文件）
- `backend/pyproject.toml`
- `backend/src/genui_api/__init__.py`
- `backend/src/genui_api/contracts/__init__.py`
- `backend/src/genui_api/contracts/dsl.py`
- `backend/src/genui_api/contracts/validation.py`
- `backend/src/genui_api/contracts/schema_export.py`
- `backend/tests/contracts/test_dsl_valid.py`
- `backend/tests/contracts/test_dsl_invalid.py`
- `backend/tests/contracts/test_schema_export.py`
- `contracts/dsl/v0.1/schema.json`
- `examples/dsl/coffee-shop-landing.json`
- `.gitignore`（最小：Python 虚拟环境与缓存）

最小修改（仅限：写入 DSL v0.1 已确定事实、更新里程碑状态、补充必要术语、更新导航）：

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/GLOSSARY.md`

结构说明：ARCHITECTURE.md §15 已约定后端目录为 `backend/`（任务书默认 `apps/api/`），本轮遵循既有约定采用 `backend/` + src 布局。

## 禁止的变更 (Forbidden Changes)

- 引入 pydantic(v2) 与 pytest 之外的任何依赖；
- 实现 FastAPI 路由 / HTTP 入口 / 前端 / Patch / Provider / 模板 / 数据库；
- 使用 `eval` / `exec` / 动态代码执行；
- 开放式 props（`dict[str, Any]`）或开放式 style；
- 修改 DSL version（固定 `"0.1"`）；
- 修改 specs/000-project-foundation.md 及任何 M0 文档的历史验收标准；
- 删除文件、Git init、Git 提交；
- 为"未来可能需要"建立复杂抽象；
- 在实现过程中擅自降低本 Spec 的验收标准。

## 功能需求 (Functional Requirements)

### 契约模型

- FR-1：DSL Document 顶层 = `version`（固定 `"0.1"`）+ `root`（必须 Page）+ 可选 `metadata`（仅允许显式定义字段，拒绝任意扩展）。不得包含数据库 ID、用户 ID、selectedNodeId、模型提示词、Trace、Patch 历史。
- FR-2：每个节点至少含 `id`、`type`、`props`；容器节点含 `children`；可选 `style`。所有模型拒绝未知字段（extra=forbid），不静默忽略。
- FR-3：九种组件各有独立严格 props 模型：
  - Page：可选 `title`；容器；
  - Section：可选 `ariaLabel`；容器；
  - Heading：必填 `text`、必填 `level`（1–6 整数）；叶子；
  - Text：必填 `text`；叶子；
  - Button：必填 `text`、可选 `variant`（枚举 `primary/secondary/ghost`）、可选 `disabled`；叶子；无 onClick/事件；
  - Image：必填 `src`、必填 `alt`；叶子；`src` 拒绝 `javascript:`/`vbscript:`（忽略大小写与首尾空白）；
  - Card：可选 `title`；容器；
  - Form：可选 `name`；容器；无真实提交行为；
  - Input：必填 `name`、必填 `label`、必填 `inputType`（枚举 `text/email/tel/number`）、可选 `placeholder`、可选 `required`；叶子。
- FR-4：文本类字段设合理长度上限（title/label/placeholder ≤ 200，text ≤ 2000，src ≤ 2048，name ≤ 128）。

### 稳定节点 ID

- FR-5：ID 格式 `^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$`，长度 1–128；非法 ID 直接拒绝，不自动修复。合法例：`page`、`hero`、`hero.title`、`hero.primary-button`、`coffee-menu.card-1`；非法例：`Hero`、`hero_primary_button`、`1hero`、`hero..button`、`hero primary`、空串。
- FR-6：ID 在整棵树全局唯一（业务校验，错误码 `DUPLICATE_NODE_ID`）。

### 受控 style

- FR-7：style 白名单字段（全部可选）：`color`、`backgroundColor`、`fontSize`、`fontWeight`、`textAlign`、`width`、`height`、`padding`、`margin`、`borderRadius`、`gap`。未定义字段必须被拒绝；不允许 style 字符串。
- FR-8：取值规则用白名单而非黑名单天然排除可执行内容：颜色 = `#` + 3–8 位 hex 或命名色白名单（`black/white/transparent`）；尺寸类（fontSize/width/height/padding/margin/borderRadius/gap）= `数字 + (px|rem|em|%)`；`fontWeight` ∈ `normal/medium/semibold/bold`；`textAlign` ∈ `left/center/right`。

### 嵌套矩阵（集中定义，业务校验）

- FR-9：集中定义的唯一嵌套矩阵：
  - root 必须是 Page（由 Document 模型结构保证）；
  - Page 不能出现在任何非根位置（矩阵中任何类型的子类型集合都不含 Page）；
  - 容器类型：`Page / Section / Card / Form`；叶子类型：`Heading / Text / Button / Image / Input`（叶子出现 children 即拒绝，由模型 extra=forbid 保证）；
  - `Page / Section / Card` 的子类型 ∈ {Section, Heading, Text, Button, Image, Card, Form}；
  - `Form` 的子类型 ∈ {Input, Button, Text, Heading}；
  - Input 的直接父节点必须是 Form；
  - 违反嵌套矩阵 → 错误码 `INVALID_NESTING`。
- FR-10：空容器规则（本轮明确决定）：**允许**。容器节点的 `children` 为必填字段、可为空数组——使每种节点的 JSON 形状按类型完全确定。

### 校验入口与错误

- FR-11：稳定入口 `validate_dsl_document(data) -> DSLDocument`、`validate_dsl_json(raw_json) -> DSLDocument`。
- FR-12：三类错误可区分：非法 JSON（`DslJsonError`）、结构非法（Pydantic `ValidationError`，自带字段路径）、业务规则非法（`DslValidationError`，含稳定错误码与节点路径）。错误信息不含密钥/环境信息；不"尽力修复"；不静默删字段。

### JSON Schema 导出

- FR-13：`contracts/dsl/v0.1/schema.json` 由 Pydantic 模型导出，含版本标记（`x-dsl-version: "0.1"`），序列化确定（`sort_keys` + 固定缩进 + 末尾换行），可重复执行且无意义 diff。
- FR-14：文档中明确说明：全局 ID 唯一性与嵌套矩阵超出 JSON Schema 表达能力，由业务校验负责。

### Gold Case

- FR-15：`examples/dsl/coffee-shop-landing.json`：version 0.1、root 为 Page、含标题/介绍文字/图片/菜单卡片/主按钮（id `hero.primary-button`）/简单表单，九种组件全部出现，ID 全局唯一，通过全部校验，无脚本/事件/raw HTML。

### 测试

- FR-16：≥15 个 pytest，覆盖任务书列出的 8 项正向与 17 项反向场景；反向测试必须断言拒绝原因（错误类型 + 错误码/路径关键词），不得只写宽泛 `raises Exception`。

## 验收标准 (Acceptance Criteria)

1. 本 Spec 完整存在且与 AGENTS.md / PRODUCT.md / ARCHITECTURE.md 一致；
2. DSL Document v0.1 有明确且严格的数据模型（全部 extra=forbid）；
3. 九种固定组件均有独立 props 契约；
4. 未知组件和未知字段被拒绝；
5. root 必须为 Page，Page 不能出现在非根位置；
6. 节点 ID 格式合法且全局唯一（非法 ID 与重复 ID 均被拒）；
7. 组件嵌套规则集中定义并被确定性校验；
8. Input 不能出现在 Form 之外；
9. style 使用有限白名单（未知字段/字符串形式被拒）；
10. 不存在任意脚本、事件代码或 raw HTML 入口；
11. 咖啡店 Gold Case 通过真实校验；
12. JSON Schema 可确定性导出（两次导出逐字节一致）；
13. schema.json 与当前 Pydantic 模型一致（测试验证）；
14. ≥15 个测试覆盖关键正向和反向场景；
15. 全部 pytest 通过；
16. 未实现任何本轮范围外功能；
17. 未删除或覆盖用户已有内容；
18. 未引入未授权依赖；
19. 文档与实现没有明显矛盾；
20. 所有实际执行的验证结果均被如实记录。

## 验证命令 (Verification Commands)

```bash
# 1. 创建局部虚拟环境并安装已授权依赖
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]"

# 2. 运行全部 pytest
.venv/bin/python -m pytest backend/tests -v

# 3. 单独验证 Gold Case
.venv/bin/python -c "import json,pathlib;from genui_api.contracts.validation import validate_dsl_document;validate_dsl_document(json.loads(pathlib.Path('examples/dsl/coffee-shop-landing.json').read_text()));print('GOLD CASE OK')"

# 4. 重新导出 JSON Schema 并检查确定性（两次导出 diff 为空）
.venv/bin/python -m genui_api.contracts.schema_export /tmp/schema_a.json
.venv/bin/python -m genui_api.contracts.schema_export /tmp/schema_b.json
diff /tmp/schema_a.json /tmp/schema_b.json && diff /tmp/schema_a.json contracts/dsl/v0.1/schema.json

# 5. 检查所有 JSON 文件合法
python3 -c "import json,glob;[json.load(open(f)) for f in glob.glob('**/*.json',recursive=True) if '.venv' not in f];print('ALL JSON OK')"

# 6. 危险/越界内容扫描（业务代码与示例，期望无命中）
grep -rn -E "eval\(|exec\(|javascript:|onClick|rawHtml|dangerouslySetInnerHTML" backend/src examples/ || echo "OK: clean"
```

## 审批闸门 (Approval Gates)

- 引入新依赖：pydantic(v2)、pytest —— 任务书已明确授权，仅限这两个。
- 修改 DSL Schema：本轮即"定义 DSL v0.1"，属任务书授权范围内；后续任何修改须重新走闸门。

## 完成报告 (Completion Report)

按 AGENTS.md §10 固定格式输出，并逐条对照本 Spec 的 20 项验收标准标记 PASS / FAIL 附证据。
