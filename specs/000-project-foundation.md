# Spec 000 — 项目奠基：契约、架构文档与 Spec 体系

## 目标 (Goal)

建立项目契约、产品边界、架构边界、术语系统和后续 Spec 模板，使后续所有任务都能通过独立 Spec 驱动。

## 背景 (Context)

这是仓库的第一份 Spec（对应任务 M0-01），在空仓库上执行。它本身也是后续所有 Spec 的范例：范围明确、验收可判定、不含业务代码。项目约束见 [AGENTS.md](../AGENTS.md)，产品与架构边界见 [docs/PRODUCT.md](../docs/PRODUCT.md) 与 [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)。

## 范围内 (In Scope)

- `AGENTS.md`
- `README.md`
- `docs/**`（PRODUCT、ARCHITECTURE、GLOSSARY、adr/README）
- `specs/README.md`
- `specs/000-project-foundation.md`（本文件）

## 范围外 (Out of Scope)

- 初始化 React / Vite；
- 初始化 FastAPI；
- 安装任何依赖；
- 编写 DSL Schema；
- 编写 Patch 实现；
- 接入模型；
- 编写应用代码；
- 创建数据库；
- 创建 CI；
- 实现 UI；
- 初始化 Git 仓库、创建 Git 提交。

## 允许的文件 (Allowed Files)

- `AGENTS.md`（新建）
- `README.md`（新建）
- `docs/PRODUCT.md`（新建）
- `docs/ARCHITECTURE.md`（新建）
- `docs/GLOSSARY.md`（新建）
- `docs/adr/README.md`（新建）
- `specs/README.md`（新建）
- `specs/000-project-foundation.md`（新建）

## 禁止的变更 (Forbidden Changes)

- 任何 React / TypeScript / Python / FastAPI 业务代码；
- 任何依赖安装与脚手架初始化（npm / pnpm / pip 等）；
- 状态管理库选型；
- 连接真实模型；
- 数据库、CI/CD、Docker 配置；
- DSL 或 Patch 的实现；
- 大而空的企业级目录；
- Git 提交；
- 覆盖用户已有内容；
- 修改本 Spec 未允许的文件。

## 功能需求 (Functional Requirements)

- FR-1：AGENTS.md 包含全部 20 条不可违反约束、11 项审批闸门、任务执行协议、测试与安全规则、完成报告格式。
- FR-2：PRODUCT.md 定义问题、用户、旅程、MVP 功能、组件集、局部精修流程、模板概念、指标（含北极星）、演示场景、非目标、风险与完成定义。
- FR-3：ARCHITECTURE.md 定义系统上下文、前后端职责、共享契约、DSL 模型、组件注册表、选中状态、Patch 校验管线、非目标完整性校验、Provider 边界、模板边界、错误处理、测试策略、安全边界、仓库结构与里程碑顺序。
- FR-4：GLOSSARY.md 定义全部关键术语且互不矛盾。
- FR-5：docs/adr/README.md 规定 ADR 用途、命名与最小模板。
- FR-6：specs/README.md 规定 Spec 的必备小节与执行规则。
- FR-7：所有文档内容为中文；关键协议术语可保留英文括注以便与代码对应。

## 验收标准 (Acceptance Criteria)

1. 所有目标文档存在；
2. 项目目标在各文档中一致；
3. MVP 范围和非目标范围明确；
4. DSL、Patch、模型与校验责任边界明确；
5. AGENTS.md 包含所有不可违反约束；
6. 后续任务可以通过独立 Spec 驱动；
7. 文档不存在明显自相矛盾；
8. 没有安装依赖或创建业务代码；
9. 没有覆盖、删除用户已有文件；
10. 所有 Markdown 文件格式可正常阅读。

## 验证命令 (Verification Commands)

本阶段纯文档、无代码与工具链，因此没有自动化测试命令。改用以下人工/脚本检查：

```bash
# 1. 目标文件全部存在
ls AGENTS.md README.md docs/PRODUCT.md docs/ARCHITECTURE.md docs/GLOSSARY.md docs/adr/README.md specs/README.md specs/000-project-foundation.md

# 2. 不存在占位符与含糊表述
grep -rn -i -E "TODO|TBD|placeholder|以后再说" --include="*.md" . || echo "OK: no placeholders"

# 3. 没有意外生成业务代码或依赖文件
find . -type f -not -path "./.*" -not -name "*.md" | wc -l   # 期望 0
```

## 审批闸门 (Approval Gates)

无。本轮不触碰 AGENTS.md §6 的任何闸门（不装依赖、不改协议、不删文件、不初始化 Git）。

## 完成报告 (Completion Report)

按 AGENTS.md §10 的固定格式输出，逐条对照上方验收标准标记 PASS / FAIL 并附证据。
