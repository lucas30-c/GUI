# Spec 004 — 前端 DSL Renderer 与单节点选中

## 目标 (Goal)

交付一个最小的 React + TypeScript + Vite 前端，能够确定性渲染 DSL v0.1 文档，并支持单节点点击/键盘选中，含视觉反馈与只读信息面板。

## 背景 (Context)

- 前置：M1-01/M1-02/M1-03 已全部完成。
  - DSL v0.1 契约、校验核心、Gold Case（见 [001-dsl-contract-and-validation.md](001-dsl-contract-and-validation.md)）
  - DSL 校验 HTTP API（见 [002-dsl-validation-api.md](002-dsl-validation-api.md)）
  - Patch v0.1 契约与确定性应用核心（见 [003-controlled-patch-core.md](003-controlled-patch-core.md)）
  - 后端 213 个 pytest 通过
- 本轮进入 M2：前端骨架、DSL Renderer、单节点选中。
- 本轮不调用后端 API——仅静态导入 Gold Case JSON 进行渲染。
- 架构依据：[ARCHITECTURE.md](../docs/ARCHITECTURE.md) §7 前端渲染层、§8 选中状态。

## 范围内 (In Scope)

1. `frontend/` 项目初始化（React + TypeScript + Vite）
2. 9 种组件的确定性 Renderer
3. Style 白名单映射器（纯函数）
4. `selectedNodeId` 状态管理（React `useState`）
5. Click 选中与事件冒泡阻止
6. Keyboard 选中（Enter / Space）
7. 选中态视觉反馈（outline / box-shadow）
8. 只读信息面板（显示选中节点 id、type、props）
9. Gold Case 完整渲染验证
10. 前端单元测试（vitest + @testing-library/react）
11. TypeScript 类型检查通过
12. 生产构建成功

## 范围外 (Out of Scope)

- Patch HTTP API 调用
- 模型 Provider / Mock Provider / 真实模型调用
- Chat 对话界面
- 多轮对话会话
- 属性编辑器（本轮仅只读面板）
- 拖拽编辑
- Undo / Redo
- 持久化 / 数据库
- Auth / CORS
- Docker / CI
- UI 组件库（Material UI / Ant Design 等）
- CSS-in-JS（styled-components / emotion 等）
- Storybook

## 允许的文件 (Allowed Files)

新建：

- `specs/004-frontend-dsl-renderer-selection.md`（本文件）
- `frontend/**`（整个前端目录）

最小修改：

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/GLOSSARY.md`（如需补充前端术语）
- `.gitignore`（增加前端 build/cache 目录）

禁止修改：

- `backend/**`
- `contracts/**`
- `examples/**`
- `specs/000-003`
- `AGENTS.md`
- `docs/PRODUCT.md`

## 禁止的变更 (Forbidden Changes)

- 引入未经批准的依赖
- 修改 DSL v0.1 Schema（`contracts/dsl/v0.1/schema.json`）
- 修改 Patch v0.1 Schema（`contracts/patch/v0.1/schema.json`）
- 修改后端代码（`backend/**`）
- 修改 Gold Case（`examples/dsl/coffee-shop-landing.json`）
- 在前端目录复制 Gold Case（应直接引用 `../examples/` 中的原文件）
- 使用 `dangerouslySetInnerHTML`
- 使用 `eval` / `exec` / `Function` / 动态代码执行
- 从 DSL props 中提取并绑定事件处理器
- 实现 Patch 应用 / 模型调用 / Chat UI
- 安装 CSS-in-JS 库 / UI 组件库 / 状态管理库
- 实现拖拽 / Undo / Redo / 持久化
- 修改已有 Spec（001-003）的验收标准
- 删除文件
- 为"未来可能需要"建立复杂抽象

## 前端依赖决策 (Frontend Dependency Decision)

### 运行时依赖 (dependencies)

| 包名 | 理由 |
|------|------|
| `react` | UI 框架核心 |
| `react-dom` | React DOM 渲染 |

### 开发依赖 (devDependencies)

| 包名 | 理由 |
|------|------|
| `typescript` | 静态类型保证 |
| `vite` | 现代构建工具，快速 HMR |
| `@vitejs/plugin-react` | Vite React 集成 |
| `vitest` | Vite 原生测试框架 |
| `jsdom` | 测试环境 DOM 模拟 |
| `@testing-library/react` | 组件测试工具 |
| `@testing-library/jest-dom` | DOM 断言扩展 |
| `@testing-library/user-event` | 用户交互模拟 |
| `@types/react` | React 类型定义 |
| `@types/react-dom` | ReactDOM 类型定义 |

以上已全部获得项目所有者批准。不得引入任何超出此列表的依赖。

## D1: 状态管理 (State Management)

- **决策**：使用 React 内置 `useState` 管理 `selectedNodeId`。
- **不引入**：Zustand、Redux、Jotai、MobX 或任何外部状态库。
- **理由**：M2 阶段状态极其简单（一个 `string | null`），引入外部状态管理属过度设计。
- **重新评估条件**：当状态复杂度显著增长（如多选、历史栈）时重新决策。

## D4: TypeScript 类型维护 (TypeScript Type Maintenance)

- **决策**：手写 TypeScript discriminated union 类型，与 `contracts/dsl/v0.1/schema.json` 对齐。
- **不使用**：json-schema-to-typescript、quicktype 或任何自动代码生成工具。
- **事实来源**：JSON Schema（由后端 Pydantic 模型导出）仍为唯一事实来源。
- **维护方式**：手动保持 TS 类型与 JSON Schema 一致。
- **重新评估条件**：当手动同步成为负担（如组件数量显著增加）时引入自动化。

## DSL 输入源 (DSL Input Source)

- 静态导入 `examples/dsl/coffee-shop-landing.json`（Gold Case）。
- **不调用任何后端 API**。
- **不在 `frontend/` 目录中复制 Gold Case**——通过相对路径引用项目根目录的 `examples/` 文件。
- Vite 配置中需处理 JSON 导入路径（`resolve.alias` 或相对路径）。

## 九种组件渲染语义 (Nine Component Rendering Semantics)

| 组件 | DOM 元素 | 关键 Props 映射 | 容器/叶子 |
|------|----------|----------------|-----------|
| Page | `<main>` | `props.title` → `document.title` 或 `aria-label` | 容器 |
| Section | `<section>` | `props.ariaLabel` → `aria-label` | 容器 |
| Heading | `<h1>`–`<h6>` | `props.text` → textContent，`props.level` → 标签层级 | 叶子 |
| Text | `<p>` | `props.text` → textContent | 叶子 |
| Button | `<button>` | `props.text` → textContent，`props.variant` → CSS class，`props.disabled` → `aria-disabled` 属性 | 叶子 |
| Image | `<img>` | `props.src` → src，`props.alt` → alt | 叶子 |
| Card | `<article>` | `props.title` → `aria-label` 或内部 heading | 容器 |
| Form | `<form>` | `props.name` → name 属性，`onSubmit` = `preventDefault` | 容器 |
| Input | `<label>` + `<input>` | `props.name` → name，`props.label` → label textContent，`props.inputType` → type，`props.placeholder` → placeholder，`props.required` → required | 叶子 |

所有节点共通属性：

- `data-node-id={node.id}`
- `data-node-type={node.type}`
- `key={node.id}`（React reconciliation）

注：Button 的 `disabled` 语义通过 `aria-disabled` 表达（而非原生 `disabled` 属性），确保 disabled Button 在编辑器中保留选择能力（click / Enter / Space 均可触发选中）。

容器节点递归渲染 `children`。

## Style 映射规则 (Style Mapping Rules)

- **白名单属性**：`color`、`backgroundColor`、`fontSize`、`fontWeight`、`textAlign`、`width`、`height`、`padding`、`margin`、`borderRadius`、`gap`
- 实现为**纯函数**：接收 DSL `style` 对象，返回 `React.CSSProperties`
- 仅映射白名单中的属性，忽略任何未知属性
- **禁止**：`dangerouslySetInnerHTML`、`eval`、内联 `<style>` 标签从 DSL 生成
- **禁止**：从 DSL style 值中执行任何代码
- 白名单属性名与 React `CSSProperties` 键名一致（camelCase），可直接透传

## selectedNodeId 状态语义 (selectedNodeId State Semantics)

- **类型**：`string | null`
- **初始值**：`null`（无选中）
- **存储位置**：React 组件 state（`useState`）
- **永不写入 DSL**：选中状态是 UI 层概念，不污染数据层
- **设置时机**：节点 click / keyboard 交互
- **清除**：点击空白区域或按 Escape（可选增强）

## Click 选中规则 (Click Selection Rules)

- 点击节点 → `setSelectedNodeId(node.id)`
- `event.stopPropagation()` 阻止事件冒泡至祖先节点
- 同一时间只有一个节点被选中
- 点击不同节点 → 替换当前选中
- 点击已选中节点 → 保持选中（不取消）

## 事件冒泡规则 (Event Bubbling Rules)

- 每个渲染节点的 click handler 调用 `event.stopPropagation()`
- 确保最深层被点击的节点被选中（而非其祖先容器）
- 示例：点击 Card 内的 Heading → 选中 Heading，而非 Card 或 Section

## Keyboard 交互 (Keyboard Interaction)

- 所有渲染节点设置 `tabIndex={0}`，使其可聚焦
- `Enter` 或 `Space` 键触发选中（与 click 行为一致）
- 焦点环（focus ring）可见，便于键盘用户定位当前焦点
- Tab 键在节点间顺序导航

## 选中视觉规则 (Selection Visual Rules)

- 选中节点添加 `outline` 或 `box-shadow`（不影响布局）
- **不使用** `border`（会改变元素尺寸）
- **不覆盖** DSL 定义的 style（选中态样式为叠加层）
- 使用明显区分色（如 `2px solid #2563eb`，蓝色轮廓）
- 未选中节点无额外视觉标记

## 无障碍 (Accessibility)

- 选中节点使用 `data-selected` 自定义属性标识，并设置 `aria-current="true"`（`aria-current` 通用性强，不限于特定 ARIA role）
- 不使用 `aria-selected`，因为该属性仅在特定 ARIA role（如 `option`、`row`、`tab`、`treeitem`、`gridcell`）上合法，在 `<h1>`、`<form>`、`<label>` 等元素上使用属于语义错误
- Disabled buttons MUST remain selectable in the DSL editor. The `disabled` semantic is preserved via `aria-disabled` rather than the HTML `disabled` attribute, ensuring click/keyboard events still trigger selection.
- 键盘可导航（Tab + Enter/Space 选中）
- 所有组件使用语义化 HTML 元素（见第 11 节）
- 不引入无意义的包装 `<div>` 破坏语义结构
- Image 始终提供 `alt` 属性
- Form 元素使用 `<label>` 关联 `<input>`

## 安全边界 (Security Boundaries)

- **禁止** `dangerouslySetInnerHTML`
- **禁止** `eval` / `exec` / `Function` 构造函数
- **禁止**从 DSL props 动态执行代码
- **禁止**从 DSL props 绑定事件处理器（如 onClick 字符串）
- 未知组件类型 → Error Boundary 捕获并显示错误信息，**不静默渲染为 div**
- Image `src` 不作为代码执行（仅设为 img src 属性）
- 所有 DSL 内容视为不可信输入：仅渲染预定义映射，不解释为代码

## 测试策略 (Test Strategy)

最少 44 个测试，分类覆盖：

| 分类 | 最少数量 | 覆盖重点 |
|------|----------|----------|
| Renderer 正向 | 9+ | 每种组件类型至少一个渲染测试 |
| Renderer Props | 5+ | props → DOM 属性映射正确性 |
| Renderer Children | 3+ | 容器递归渲染子节点 |
| Renderer Style | 3+ | 白名单 style 正确应用 |
| Renderer 反向 | 2+ | 未知组件类型触发 Error Boundary |
| Gold Case | 1+ | 完整 Gold Case 渲染无崩溃 |
| Selection Click | 5+ | 点击选中、替换选中、stopPropagation、深层节点选中 |
| Selection Keyboard | 4+ | Enter/Space 选中、Tab 导航 |
| Selection Visual | 3+ | 选中态样式、data-selected、取消选中 |
| Info Panel | 3+ | 面板显示选中节点信息、无选中时空态 |
| DSL 不可变性 | 2+ | 选中操作不修改 DSL 数据 |
| 回归 | 4+ | TypeScript 编译、生产构建、后端测试不回归、Schema 未变更 |

测试环境：vitest + jsdom + @testing-library/react。

## 验收标准 (Acceptance Criteria)

| # | 标准 |
|---|------|
| AC-01 | 本 Spec 完整存在且与 AGENTS.md / ARCHITECTURE.md 一致 |
| AC-02 | `frontend/` 目录结构存在，使用 Vite + React + TypeScript |
| AC-03 | `package.json` 仅包含已批准的依赖 |
| AC-04 | TypeScript 严格模式启用（`strict: true`） |
| AC-05 | DSL TypeScript 类型定义存在，为 discriminated union |
| AC-06 | DSL 类型与 `contracts/dsl/v0.1/schema.json` 对齐 |
| AC-07 | Page 组件渲染为 `<main>` 并设置 title |
| AC-08 | Section 组件渲染为 `<section>` 并映射 ariaLabel |
| AC-09 | Heading 组件渲染为对应层级的 `<h1>`–`<h6>` |
| AC-10 | Text 组件渲染为 `<p>` |
| AC-11 | Button 组件渲染为 `<button>` 并映射 variant/disabled |
| AC-12 | Image 组件渲染为 `<img>` 并映射 src/alt |
| AC-13 | Card 组件渲染为 `<article>` |
| AC-14 | Form 组件渲染为 `<form>` 并 preventDefault |
| AC-15 | Input 组件渲染为 `<label>` + `<input>` 并映射全部 props |
| AC-16 | 所有节点输出 `data-node-id` 和 `data-node-type` 属性 |
| AC-17 | 所有节点使用 `key={node.id}` |
| AC-18 | Style 白名单映射器为纯函数，仅映射 11 个允许属性 |
| AC-19 | 未知 style 属性被忽略（不透传） |
| AC-20 | 容器节点递归渲染 children |
| AC-21 | Gold Case 完整渲染无错误 |
| AC-22 | 未知组件类型触发 Error Boundary 而非静默渲染 |
| AC-23 | `selectedNodeId` 使用 `useState<string \| null>(null)` |
| AC-24 | 点击节点设置 selectedNodeId |
| AC-25 | `event.stopPropagation()` 阻止冒泡 |
| AC-26 | 同一时间仅一个节点被选中 |
| AC-27 | 点击不同节点替换选中 |
| AC-28 | 深层嵌套节点点击选中最深节点 |
| AC-29 | 节点设置 `tabIndex={0}` |
| AC-30 | Enter 键触发选中 |
| AC-31 | Space 键触发选中 |
| AC-32 | Tab 键可在节点间导航 |
| AC-33 | 选中节点有视觉反馈（outline/box-shadow） |
| AC-34 | 选中视觉不改变布局（不使用 border） |
| AC-35 | 选中视觉不覆盖 DSL style |
| AC-36 | 选中节点使用 `data-selected` 属性 + `aria-current="true"`（不使用 `aria-selected`） |
| AC-37 | 信息面板显示选中节点的 id、type、props |
| AC-38 | 无选中时信息面板显示空态提示 |
| AC-39 | 选中操作不修改原始 DSL 数据 |
| AC-40 | 不使用 `dangerouslySetInnerHTML` |
| AC-41 | 不使用 `eval`/`Function`/动态代码执行 |
| AC-42 | 不从 DSL 绑定事件处理器 |
| AC-43 | `tsc --noEmit` 通过 |
| AC-44 | `vite build` 成功 |
| AC-45 | ≥44 个前端测试通过 |
| AC-46 | 后端 213 个测试继续通过（无回归） |

## 验证命令 (Verification Commands)

```bash
# === 前端验证 ===

# 1. 进入前端目录
cd frontend

# 2. 安装依赖
npm install

# 3. TypeScript 类型检查
npm run typecheck

# 4. 运行全部前端测试
npx vitest run

# 5. 测试计数（确保 ≥44 个测试）
npx vitest run --reporter=verbose 2>&1 | grep -c "✓\|√\|PASS"

# 6. 生产构建
npx vite build

# 7. 构建产物存在
ls dist/index.html

# 8. 检查依赖白名单（package.json 中不应有未批准依赖）
cat package.json | python3 -c "
import json,sys
pkg = json.load(sys.stdin)
allowed_deps = {'react','react-dom'}
allowed_dev = {'typescript','vite','@vitejs/plugin-react','vitest','jsdom',
  '@testing-library/react','@testing-library/jest-dom','@testing-library/user-event',
  '@types/react','@types/react-dom'}
deps = set(pkg.get('dependencies',{}).keys())
devs = set(pkg.get('devDependencies',{}).keys())
extra_deps = deps - allowed_deps
extra_devs = devs - allowed_dev
if extra_deps: print(f'FAIL: 未批准运行时依赖: {extra_deps}'); sys.exit(1)
if extra_devs: print(f'FAIL: 未批准开发依赖: {extra_devs}'); sys.exit(1)
print('DEPS OK')
"

# 9. 安全扫描（禁止内容不应出现在源码中）
grep -rn -E "dangerouslySetInnerHTML|eval\(|new Function\(|exec\(" src/ && echo "FAIL: 存在禁止内容" || echo "OK: clean"

# 10. 验证 Gold Case 未被复制到 frontend/
find . -name "coffee-shop-landing.json" | grep -v node_modules && echo "FAIL: Gold Case 被复制" || echo "OK: no copy"

# 11. data-node-id 属性在 renderer 中存在
grep -rn "data-node-id" src/

# 12. data-node-type 属性在 renderer 中存在
grep -rn "data-node-type" src/

# 13. stopPropagation 在 renderer 中存在
grep -rn "stopPropagation" src/

# 14. tabIndex 在 renderer 中存在
grep -rn "tabIndex" src/

# 15. data-selected 在 renderer 中存在
grep -rn "data-selected" src/

# 16. useState 用于 selectedNodeId
grep -rn "selectedNodeId" src/

# 17. Error Boundary 存在
grep -rn -i "ErrorBoundary\|error.boundary\|error-boundary" src/

# === 后端回归验证 ===

# 18. 进入后端目录
cd ../backend

# 19. 运行全部后端测试
source .venv/bin/activate && pytest -v

# 20. 后端测试计数
pytest --collect-only -q | tail -1

# 21. DSL Schema 未变更
git diff --stat contracts/dsl/v0.1/schema.json

# 22. Patch Schema 未变更
git diff --stat contracts/patch/v0.1/schema.json

# 23. Gold Case 未变更
git diff --stat examples/dsl/coffee-shop-landing.json

# 24. 后端代码未变更
git diff --stat backend/

# === 整体检查 ===

# 25. .gitignore 包含前端条目
grep -E "node_modules|dist" ../.gitignore

# 26. Spec 存在且非空
wc -l ../specs/004-frontend-dsl-renderer-selection.md
```

## 审批闸门 (Approval Gates)

- **依赖**：react、react-dom（运行时）+ typescript、vite、@vitejs/plugin-react、vitest、jsdom、@testing-library/react、@testing-library/jest-dom、@testing-library/user-event、@types/react、@types/react-dom（开发）—— 已获项目所有者批准。
- **D1 状态管理**：React useState —— 已批准。
- **D4 类型维护**：手写 TS 类型 —— 已批准。
- **无剩余审批项**：除非实现过程中发现需要额外依赖，此时必须暂停并报告。

## 开放决策 (Open Decisions)

无。本轮所有技术决策已明确。

## 完成报告格式 (Completion Report Format)

按 AGENTS.md §10 固定格式输出，包含以下小节：

```text
## Result
## Repository State
## Files Created
## Files Modified
## Key Decisions Recorded
## Acceptance Criteria     （逐条 AC-01 ~ AC-46 标记 PASS / FAIL，附证据）
## Verification            （实际运行的 26 条命令与真实输出；未运行的写明"未运行"及原因）
## Scope Check             （是否安装未授权依赖/触碰范围外文件/删除文件）
## Open Decisions          （需所有者决定的问题；没有则写 None）
## Git Summary             （git status --short 与 git diff --stat）
## Recommended Next Task   （只提一个建议，不执行）
```

报告必须如实。没做的、没运行的，就直说。隐瞒失败的报告本身就是失败。
