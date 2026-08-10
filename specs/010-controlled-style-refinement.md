# Spec 010 — Controlled Style Refinement (M4-04)

## Meta

| 字段 | 值 |
|------|------|
| Spec 编号 | 010 |
| 标题 | 受控样式精修（M4-04） |
| 前置 Spec | 001（DSL 契约与校验）、003（受控 Patch 核心）、004（前端渲染与选中）、005（Refinement Pipeline + Mock Provider + API）、006（前端局部精修闭环）、008（真实模型与 SP/UP 策略）、009（多轮上下文与稳定性） |
| 前置条件 | M4-03（Spec 009）已完成并提交；回归基线为**后端 759 tests / 前端 336 tests / E2E 3 spec 全绿**；Git 基线 HEAD = `6206850`（main，M4-03 提交），工作区除本 Spec 文件外干净 |
| 里程碑 | M4-04 — 受控样式精修（`update_style` 操作 + style 上下文 + style 历史） |
| 架构依据 | [AGENTS.md](../AGENTS.md) §2 / §5 / §6 / §9、[docs/PRODUCT.md](../docs/PRODUCT.md)、[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) |
| 正文语言 | 中文；技术术语、字段名、AC 与 Verification Commands 用英文技术表述 |
| 状态 | **DRAFT — 待所有者审批**（本 Spec 含 8 项 §6 审批闸门，未获批准不得实施） |

## 1. Background

M4-03（Spec 009）交付了请求级有界对话历史与多轮稳定性证据，Task 1（受控 GenUI 原型）的六项证明目标中，第 1/2/3/4/5 项均已有自动化证据。此时**唯一剩余的主要 capability gap** 来自 AGENTS.md §2 对 MVP 范围的原文表述：

> 对选中控件下达自然语言精修指令（文案 / **颜色** / **尺寸** / **布局**等受允许属性）；后端只返回结构化 Patch。

DSL v0.1 从 Spec 001 起就定义了受控 `style` 白名单（11 字段），前端渲染器（`frontend/src/dsl/style.ts`）从 M2 起就完整支持这 11 个字段，生成侧 SP 也已把 style 白名单写入契约——也就是说，**style 在「生成」与「渲染」两端都已就绪，只有「精修」这一端缺口**：Patch v0.1 只有 `update_props` 一种操作，精修 SP 甚至明确禁止模型触碰 style。

M4-04 的职责就是把这个缺口补齐，且补齐方式必须与 M2–M4-03 已建立的受控性质完全同构：白名单、确定性校验、单节点边界、非目标零变更、模型输出永不成为状态。

### 1.1 PDF "替换"语义覆盖声明

PDF Task 1 原文「改文案/改颜色/改布局/替换等」中的"替换"已通过 `update_props` 浅合并完整满足（属性值替换：用新值覆盖旧值）。M4-04 补齐 style 维度的值替换（`update_style` 浅合并）。不引入组件级 `replace_node` 操作——PDF 核心约束「模型只改选中控件，页面其余部分保持不变」排除 tree mutation。

### 1.2 M4-03 收尾记账说明

> **M4-03 Closure Bookkeeping Note**: Owner 已授权 M4-03 closure regression 文件 `frontend/src/test/malformed-patch.test.tsx`（Spec 009 Allowed Files 未列出，Owner 授权在先）。该文件为 M4-04 的 Protected Files。

### 1.3 里程碑定位

本 Spec 为 **M4-04 FINAL IMPLEMENTATION MILESTONE 定稿**：除 style 精修能力闭环外，还负责把 `README.md` / `docs/PRODUCT.md` / `docs/ARCHITECTURE.md` 的对外陈述与实现现状对齐（AC-33 ~ AC-38），并交付一条覆盖 PRODUCT.md §9 步骤 1-5 的 Golden Path E2E（AC-39）。

本轮 closure revision 另新增三个**不参与编号体系**的收口章节（避免既有 §2 ~ §24 的交叉引用漂移）：§「PDF Task 1 Final Requirement Traceability Matrix」（紧接本节）、§「Task 1 User Acceptance Handoff」与 §「M4-04 Hard Closure Definition」（位于 §24 之后）。三者共同定义「M4-04 = PDF Task 1 实现 100%」的判据，不改变 AP-1 ~ AP-8 的任何技术方案。

## PDF Task 1 Final Requirement Traceability Matrix

本章为 M4-04 定稿新增的**收口章节**（不参与 §2 ~ §24 的编号体系，避免既有交叉引用漂移）。它把 PDF「核心任务一：控件选中感知与多轮 Prompt 设计」的原文逐条拆成 20 条 requirement（R-01 ~ R-20），并对每条给出「已有实现证据 → M4-04 需补的工作 → 自动化测试 → 用户可自行验证的方式 → 最终结论」的完整链路。

判读口径：
- **Final Status = PASS**：该 requirement 在 M4-04 开工前**已经**由既有里程碑实现且有自动化测试覆盖，M4-04 不需为它写新代码。
- **Final Status = M4-04 REQUIRED**：该 requirement 存在真实能力缺口（或缺口只在 style 维度），必须由本 Spec 的实现补齐后才能算满足。
- 本表是 §「M4-04 Hard Closure Definition」的 closure gate 输入之一：M4-04 申请 CLOSED 时，本表 20 条必须**全部**为 PASS。

| # | PDF Requirement | Requirement Interpretation | Existing Evidence / Milestone | M4-04 Work | Automated Test | User Demo / UAT Evidence | Final Status |
|---|-----------------|----------------------------|-------------------------------|------------|----------------|--------------------------|--------------|
| R-01 | 一个单页前端：用户输入一句话即可生成一个网页初稿 | 自然语言意图 → 后端生成受控 DSL → 前端渲染初稿 | **M4-01**（Spec 007 初始 DSL 生成）+ **M4-02**（Spec 008 真实模型接入）：`POST /api/generate` + `App.tsx` 生成输入框 | 无 — 已满足 | `backend/tests/api/test_generate_api.py`、`backend/tests/generation/test_generation_pipeline.py`、`frontend/src/test/generate-api.test.ts`、`frontend/src/test/generation-loop.test.tsx`、`frontend/e2e/generation-loop.spec.ts` | 顶部输入框输入「帮我做一个咖啡店落地页」→ 页面出现渲染后的初稿（Handoff Golden Path 步骤 1） | PASS |
| R-02 | 简单落地页 / 表单 / 卡片列表均可 | 至少一种页面类型可端到端演示；组件集覆盖三类页面所需节点 | **M2**（Spec 004 渲染器：9 种组件全部可渲染）+ **M4-01**（生成侧模板与 Gold Case 落地页） | 无 — 已满足 | `backend/tests/generation/test_generation_pipeline.py`（模板/页面类型）、`frontend/src/test/renderer.test.tsx`（9 种组件渲染） | 落地页（含 Section / Heading / Text / Button / Image / Card）可直接演示；换一句「做一个报名表单」可演示 Form / Input | PASS |
| R-03 | 支持在页面上点击或框选选中某个具体控件 | 节点级选中交互，选中结果为稳定 nodeId | **M2**（Spec 004 选中机制：点击节点 → `selectedNodeId`） | 无 — 已满足 | `frontend/src/test/selection.test.tsx`、`frontend/e2e/refinement-loop.spec.ts` | 点击页面上任意 Heading / Button / Card → 该节点进入选中态，侧栏显示其 id 与类型（Golden Path 步骤 2 / 8） | PASS |
| R-04 | 给出清晰的选中态视觉反馈 | 选中节点有明确、稳定、可观察的视觉标识 | **M2**（Spec 004 选中态样式：选中描边 + 选中信息展示） | 无 — 已满足 | `frontend/src/test/selection.test.tsx`（选中态 class / testid 断言）、`frontend/e2e/refinement-loop.spec.ts`（浏览器内可见性） | 被选中节点出现蓝色选中框；点击另一节点后选中框随之迁移（Golden Path 步骤 2 / 8） | PASS |
| R-05 | 用户可用自然语言对它下达精修指令 | 真实自然语言（非固定协议字符串）即可驱动精修 | **M4-02**（Spec 008 精修 SP/UP + 真实模型 Provider）+ **M3-02**（Spec 006 前端精修输入闭环） | 无 — 已满足（style 维度的自然语言可用性由 R-07 / R-08 承接） | `backend/tests/llm/test_prompts.py`、`backend/tests/provider/test_openai_compat_refinement_provider.py`、`backend/tests/llm/test_real_smoke.py`（opt-in）、`frontend/src/test/refinement-loop.test.tsx` | Real LLM 模式下在精修输入框输入「把标题改成欢迎光临」→ 生效（Golden Path 步骤 3；Mock 模式仅识别 `set_text:` 协议指令，见 Handoff §Mock vs Real LLM） | PASS |
| R-06 | 改文案 | `text` / `label` 等 props 值修改 | **M3-01**（Spec 005 `update_props` + Pipeline）+ **M3-02**（前端闭环） | 无 — 已满足 | `backend/tests/contracts/test_patch_apply.py`、`backend/tests/api/test_refine_api.py`、`frontend/src/test/refinement-loop.test.tsx`、`frontend/e2e/refinement-loop.spec.ts` | 选中 Heading → 输入「把标题改成欢迎光临」→ 文案变更、其他节点不变（Golden Path 步骤 3） | PASS |
| R-07 | 改颜色 | `color` / `backgroundColor` 等 style 值修改 | **无**（当前 Patch 只有 `update_props`；精修 SP 明确禁止 style；Pipeline 步骤 9 会把目标节点 style 变化判为 500 — §2 的 P-1 ~ P-4） | **需要**：`update_style` 操作（DD-01 ~ DD-05）+ apply 语义（DD-06 ~ DD-11）+ SP 白名单升级（DD-15）+ 步骤 9 剥离扩展（DD-20） | 新增 `backend/tests/contracts/test_patch_style_apply.py`、`backend/tests/refinement/test_style_pipeline.py`、`backend/tests/api/test_style_refine_api.py`（Scenario A）、`frontend/e2e/style-refinement.spec.ts`（AC-17 / AC-31） | 选中 Heading → 输入「改成红色」→ 标题颜色变红（Golden Path 步骤 4） | **M4-04 REQUIRED** |
| R-08 | 改布局 | `padding` / `margin` / `gap` / `textAlign` / `width` / `height` 等 style 值修改 | **无**（同 R-07：布局类指令在契约层无表达形式） | **需要**：同 R-07 的 `update_style` 链路；覆盖 Scenario C（间距）/ E（对齐）/ F（尺寸） | `backend/tests/api/test_style_refine_api.py`（Scenario C / E / F 六场景 200，AC-17）、`backend/tests/contracts/test_patch_style_apply.py`、`frontend/e2e/style-refinement.spec.ts` | 选中 Heading → 输入「居中」→ `textAlign` 变 center；再输入「增加一些内边距」→ padding 增大（Golden Path 步骤 6 / 7） | **M4-04 REQUIRED** |
| R-09 | 替换等 | 属性值替换语义：`update_props` / `update_style` 浅合并即「用新值覆盖旧值」；不引入 tree mutation | **M3-01**（props 值替换已完整满足，§1.1 PDF「替换」语义覆盖声明） | 无 — 已满足（style 维度的值替换随 R-07 / R-08 一并落地，DD-06） | `backend/tests/contracts/test_patch_apply.py`（props 覆盖）、新增 `test_patch_style_apply.py`（style 覆盖 / `null` 删键，AC-05 ~ AC-07） | 对同一节点连续两次改文案 → 后一次覆盖前一次；对同一 style 键连续改色 → 后值覆盖前值（Golden Path 步骤 3 → 4） | PASS |
| R-10 | 模型只改选中控件 | 每条 operation 的 `targetNodeId` 必须等于受信任的 `selectedNodeId`（越界即拒） | **M3-01**（Spec 005 Pipeline 步骤 7 逐条边界检查 + `candidate_boundary_violation` 502） | 无 — 已满足（步骤 7 读 `targetNodeId` 与 op 类型无关，新 op 因 DD-01 同构而自动被覆盖；本轮不改该段代码，仅补 style / 混合 ops 的证据） | `backend/tests/refinement/test_pipeline.py`（既有）、`backend/tests/security/test_adversarial.py`、新增 `test_style_pipeline.py`（style op 与混合 op 越界，AC-19） | 精修只影响被选中节点；对未选中节点下达指令无法生效（Golden Path 步骤 10 检查） | PASS |
| R-11 | 页面其余部分保持不变 | 非目标节点（含其 style）零变更，由确定性完整性校验强制 | **M3-01**（Spec 005 步骤 9 `verify_non_target_unchanged` + `non_target_mutation_detected` 500 + `integrity.nonTargetNodesUnchanged`） | **无 — 已满足**；本轮仅把「目标节点的可变字段集合」从 `{props}` 扩为 `{props, style}`（DD-20），对**非目标**节点的检查强度一字不放宽（TB-4） | `backend/tests/refinement/test_pipeline.py`（既有）、新增 `test_style_pipeline.py` B 部分（非目标 style 变化仍被检出，AC-20）、`frontend/e2e/*.spec.ts`（见证节点断言） | 每轮精修后检查其他节点文案与样式均未变；结果面板 `nonTargetNodesUnchanged: true`（Golden Path Expected Results） | PASS |
| R-12 | 支持连续多轮精修 | 同一节点可被连续多轮精修，每轮基于上一轮已确认状态 | **M4-03**（Spec 009 多轮上下文与稳定性；props 维度 ≥ 3 轮已有证据） | **需要（style 维度）**：`ConfirmedTurn.patch_style`（DD-13）+ 历史 assistant 重建含 `update_style`（DD-16）+ 每轮 `currentStyle` 由文档派生（DD-12） | `backend/tests/refinement/test_multi_turn_context.py`（既有 props 多轮）、`backend/tests/api/test_multi_turn_api.py`、新增 `test_style_pipeline.py` C 部分（Scenario B → C → D 三连轮累积，AC-23）、`frontend/e2e/multi-turn-stability.spec.ts` | 对同一 Heading 连续执行「改成红色」→「再大一点」→「居中」→「增加一些内边距」四轮，每轮都生效且前几轮结果保留（Golden Path 步骤 4 ~ 7） | **M4-04 REQUIRED**（style 维度） |
| R-13 | 保留对话…上下文 | 请求级有界对话历史进入 messages，模型能理解「再…一点」这类相对指令 | **M4-03**（Spec 009 `history` + `MAX_HISTORY_TURNS=20` / `MAX_HISTORY_CHARS=50_000` + 历史 user/assistant 确定性重建） | 无 — 已满足（本轮只在既有 history 结构上加 `patchStyle` 一个可选字段，不改机制、不改上界，DD-23 / DD-24） | `backend/tests/llm/test_history_prompts.py`、`backend/tests/refinement/test_multi_turn_context.py`、`backend/tests/security/test_history_injection.py`、`frontend/src/test/conversation-history.test.tsx` | 侧栏显示对话轮次计数并逐轮增长；「再大一点」能被正确理解为相对上一轮（Golden Path 步骤 5） | PASS |
| R-14 | 保留…页面状态上下文 | Document 是页面状态唯一事实来源；`currentProps` / `currentStyle` 每轮由已校验文档派生 | **M4-02**（`currentProps` 由文档派生）+ **M4-03**（Spec 009 DD-4 明确拒绝由前端/history 回灌 `resultProps`） | 无 — 已满足（`currentStyle` 沿用同一条派生原则，DD-12：不由模型、不由 history、不由前端提供） | `backend/tests/refinement/test_multi_turn_context.py`、新增 `test_style_pipeline.py`（`currentStyle` 派生 + 深拷贝隔离，AC-10 / AC-23） | 「再大一点」基于**当前**字号而非初始字号；切换节点再切回，之前的修改仍在（Golden Path Expected Results） | PASS |
| R-15 | 核心约束：局部修改而非整页重新生成 | 精修链路只产出针对单节点的结构化 Patch，永不整页重生成 | **M3-01 + M3-02**（`POST /api/refine` 返回 `{patch, document, integrity}`，patch 为局部操作列表；前端不重新调用生成接口） | 无 — 已满足（`update_style` 同样是单节点局部操作，不引入任何整页/树级操作，§4 Non-goals） | `backend/tests/api/test_refine_api.py`（响应含局部 patch）、`backend/tests/contracts/test_patch_apply.py`、`frontend/src/test/refine-api.test.ts`、新增 `test_style_refine_api.py` | 结果面板每轮显示的是 operation 列表（`update_props` / `update_style` + `targetNodeId`），而不是新页面；页面其余部分不闪变（Golden Path Expected Results） | PASS |
| R-16 | 保持页面其余部分稳定 | 节点 ID 跨轮稳定 + 非目标零漂移；`id` / `type` / `children` 永不可被 Patch 触碰 | **M2**（稳定 nodeId 渲染与选中）+ **M3-01**（Patch 禁改 id/type/children）+ **M4-03**（多轮零漂移证据） | 无 — 已满足（DD-20 的剥离扩展**仅**针对目标节点的 `style`；`id` / `type` / `children` 对所有节点仍在比较范围内） | `backend/tests/refinement/test_multi_turn_context.py`、`backend/tests/contracts/test_patch_apply.py`（禁改 id/type/children）、新增 `test_style_pipeline.py`（AC-20c）、`frontend/e2e/multi-turn-stability.spec.ts` | 多轮精修后同一节点仍可被选中（id 未变）；其余节点结构与样式逐项不变（Golden Path 步骤 10） | PASS |
| R-17 | 让模型准确知道「用户当前选中的是哪个控件」 | 选中控件的结构化表达：`selectedNodeId` + `nodeType` + `currentProps` + `currentStyle` | **M4-02**（UP 4 键：`instruction` / `selectedNodeId` / `nodeType` / `currentProps`） | **需要（style 维度）**：UP 升级为 5 键，新增 `currentStyle`（DD-14 / BC-9 / AP-6）——否则模型对样式类指令只能猜 | `backend/tests/llm/test_prompts.py`（既有 UP 断言）、新增 `backend/tests/llm/test_style_prompts.py`（UP 恰 5 键 + `currentStyle` 等于文档派生值，AC-15） | 精修「再大一点」时模型给出的新字号与当前字号成比例，而非固定值（说明模型确实看到了当前 style） | **M4-04 REQUIRED**（style 维度） |
| R-18 | 在连续多轮对话中稳定地只改这个控件 | 多轮场景下 boundary 检查逐轮一致，历史不授予任何越界权限 | **M4-03**（Spec 009：history 不参与判定 TB-3 + 多轮越界拒绝证据） | 无 — 已满足（步骤 7 每轮独立执行，与轮次和 op 类型无关；本轮补 style / 混合 ops 的多轮证据） | `backend/tests/security/test_history_injection.py`、`backend/tests/refinement/test_multi_turn_context.py`、新增 `test_style_pipeline.py` C 部分 + `backend/tests/security/test_style_injection.py`（AC-19 / AC-23 / TB-3） | 连续 4 轮精修同一 Heading，其余节点全程不变；伪造 history 中的其他 nodeId 不会导致越界修改 | PASS |
| R-19 | 可运行性 | 完整可启动、可演示的原型（后端 + 前端 + Mock/Real 两种模式） | **M2 ~ M4-03**（`uvicorn` 后端 + `npm run dev` 前端 + `GENUI_MODEL_PROVIDER` 双模式） | **需要（收口）**：交付 §「Task 1 User Acceptance Handoff」（普通用户可直接执行的启动与验收说明）+ Golden Path E2E（AC-39） | `frontend/e2e/generation-loop.spec.ts` / `refinement-loop.spec.ts` / `multi-turn-stability.spec.ts`（既有 3 spec）+ 新增 Golden Path spec（AC-39）；V-01 / V-13 ~ V-16 为可运行性机械证据 | Owner 按 Handoff §Startup 两条命令启动，即可走完 10 步 Golden Path，无需任何额外开发 | **M4-04 REQUIRED**（收口文档 + Golden Path E2E） |
| R-20 | Real LLM path | 真实模型路径可用且可验证（不只 Mock） | **M4-02**（`OpenAICompatRefinementProvider` + `backend/tests/llm/test_real_smoke.py`）+ **M4-03**（`test_real_multi_turn_smoke.py`） | **需要（style 维度）**：新增 opt-in 真实模型 **多轮** style smoke（见 §19.1 / AC-40） | `backend/tests/llm/test_real_smoke.py`、`test_real_multi_turn_smoke.py`（既有，opt-in）、新增 `backend/tests/llm/test_real_style_smoke.py`（2 轮 relative follow-up，AC-40） | 以 `GENUI_MODEL_PROVIDER=openai_compatible` + 真实凭证启动后端，Golden Path 全 10 步用自然语言走通（Handoff §Mock vs Real LLM） | **M4-04 REQUIRED**（style 维度） |

覆盖性声明：以上 20 条为 PDF Task 1「需要实现」四点、「需要在设计文档中回答」三点与「评估维度」四项的完整拆解，**未发现本 Spec 此前遗漏的 PDF Task 1 requirement**——R-07 / R-08 / R-12 / R-17 / R-19 / R-20 六条缺口（其中 R-12 / R-17 / R-19 / R-20 仅缺 style 或收口维度）本来就是本 Spec §3 Goals 的六点目标与 §18 H 组 AC 的立项理由。评估维度与本表的对应关系：「控件选中感知」= R-03 / R-04 / R-10 / R-11 / R-16 / R-17；「Prompt 工程」= R-05 / R-13 / R-17 / R-18 + DD-23 的上下文预算论证；「工程与产品感」= R-01 / R-02 / R-19 + §18 H 组文档对齐；「AI 协作」由 Spec 序列（000 ~ 010）与逐轮完成报告本身承载。

## 2. Problem

当前精修链路对「颜色 / 尺寸 / 布局 / 间距」类指令**结构上无法响应**，具体表现为四条事实：

| # | 事实 | 后果 |
|---|------|------|
| P-1 | Patch v0.1 只有 `update_props` 一种操作（`patch/models.py`），`operations` 元素类型即 `UpdatePropsOperation` | 「把标题改成品牌红」在契约层没有任何可表达形式 |
| P-2 | `apply_patch` 只做 `node["props"] = {**existing_props, **operation.props}`，**完全不处理 `style`** | 即使候选中出现 style 语义，也无法落到文档上 |
| P-3 | Pipeline 步骤 9 的 `_remove_props_from_node` 只剥离目标节点的 `props` | 目标节点 style 的任何变化都会被判为 `non_target_mutation_detected`（500），即 style 修改**当前被完整性校验主动拒绝** |
| P-4 | 精修 SP 明确写着「不得修改节点的 "style"…视觉样式调整暂不在本操作的能力范围内」；UP 只提供 `currentProps`，模型看不到当前 style | 模型既被禁止、也没有做出正确 style 决策所需的上下文 |

用户可观察到的现象：对选中节点说「字大一点」「加点内边距」「背景换成浅灰」时，模型只能在 props 范围内胡乱表达（例如把颜色写进 `text`），或产出必然被校验器拒绝的候选（502）。这不是模型质量问题，是契约能力缺失。

## 3. Goals

M4-04 的目标链路，共 6 点：

1. **Patch 契约加法扩展**：新增 `update_style` 操作，使「针对当前选中节点的受控样式修改」成为契约内的一等表达；Patch 版本号**仍为 `0.1`**（DD-25）。
2. **style 白名单即能力边界**：可改字段恰为 DSL `Style` 的 11 个字段，不多不少（DD-21）；任意 CSS 在结构上不可表达。
3. **确定性 apply 语义**：浅合并、`null` 删键、空 style 拒绝、未知键拒绝、非法值拒绝——每一条都有唯一确定的判定位置与错误码（第 8 节）。
4. **模型拿到做决策所需的最小上下文**：UP 增加 `currentStyle`（由 Pipeline 从**已校验文档**派生，不由模型或 history 提供，DD-12）。
5. **style 进入多轮上下文**：`ConfirmedTurn` 增加 `patch_style`，历史 assistant 消息确定性重建时包含 `update_style` 操作（DD-13 / DD-16），使「再深一点」「间距也照着来」这类相对样式指令具备上下文。
6. **信任边界一字不放宽**：所有 style 操作仍必须 `targetNodeId === trusted selectedNodeId`；非目标节点（含其 style）零变更仍由确定性校验强制（第 12 节）。

必须被覆盖的 6 个用户场景（全部落在 11 字段白名单内）：

| # | 场景 | 指令示例 | 落到的 style 字段 |
|---|------|----------|-------------------|
| Scenario A | 前景色 / 背景色 | 「标题改成品牌红」 | `color` / `backgroundColor` |
| Scenario B | 字号 | 「字再大一点」 | `fontSize` |
| Scenario C | 间距 | 「内边距大一些」「卡片之间松一点」 | `padding` / `margin` / `gap` |
| Scenario D | 圆角 | 「按钮圆一点」 | `borderRadius` |
| Scenario E | 字重与对齐 | 「加粗」「居中」 | `fontWeight` / `textAlign` |
| Scenario F | 尺寸 | 「宽度占满」 | `width` / `height` |

外加一个组合场景：**文案与样式同一轮同时改**（「文案换成『立即预订』并且加粗」）→ 同一份 Patch 内 `update_props` + `update_style` 混合（DD-05）。

## 4. Non-goals

以下内容**明确不属于**本轮范围：

- **不引入 arbitrary CSS**：不新增 style 字段、不支持 `!important`、不支持简写属性、不支持 `calc()` / `var()` / CSS 函数、不支持任意单位（单位仍限 `px` / `rem` / `em` / `%`）、不支持任意颜色写法（`rgb()` / `hsl()` / 除三个命名色外的 CSS 命名色一律拒绝）。**白名单与值域完全等于 DSL v0.1 现状**（DD-21）。
- **不引入 tree mutation**：不新增 `add_node` / `remove_node` / `move_node` / `replace_node` / `reorder_children` 等任何操作；`children` 与节点 `id` / `type` 仍不可被 Patch 触碰（AGENTS.md §5.2 / §5.3）。
- **不修改 DSL v0.1 契约**：`contracts/dsl/v0.1/schema.json` 与 `backend/src/genui_api/contracts/**` 零变更；不新增组件类型、不新增 props 字段、不新增 style 字段、不放宽任何 style 值域正则。
- **不提升 Patch 版本号**：本轮是**加法扩展**（新增一个 op 类型），`version` 仍为 `"0.1"`，不引入 `0.2` 与版本协商机制（DD-25）。
- **不引入任何新依赖**（后端与前端均不新增），不新增环境变量与配置项，不引入 tokenizer。
- **不引入主题 / 设计 token / 样式变量 / 全局样式表 / 样式继承计算**：style 恒为节点级字面值。
- **不引入批量样式操作**：一个操作恒只针对一个节点；不支持「所有 Button」「同类节点」等选择器语义。
- **不引入 style 的撤销 / diff 视图 / 样式面板 / 取色器**：前端只做「让 style 精修可用且可观察」的最小改动（DD-29）。
- **不修改生成链路**：`generation/**` 整个模块零变更；生成侧 SP 已含 style 白名单，无需改动。
- **不修改多轮上界口径**：`MAX_HISTORY_TURNS = 20` / `MAX_HISTORY_CHARS = 50_000` 不变（DD-23）。
- **不实现 repair 循环 / 自动重试 / 自动降级**：延续 Spec 008 DD-13 的 fail fast。
- **不实现指标采集 / TTUR / Eval**（属 M5）。

## 5. Current State

（事实基础，均已在本 Spec 编写前逐一读取源码确认。）

### 5.1 DSL style 契约（`backend/src/genui_api/contracts/dsl.py`）

`style` 与 `props` **同级**，是节点顶层字段：`node = { id, type, props, style?, children? }`。9 种组件**全部**声明 `style: Optional[Style] = None`。

`Style` 模型 11 字段，全部 `Optional`，`model_config = ConfigDict(extra="forbid")`：

| 组 | 字段 | 值域 |
|----|------|------|
| 颜色（2） | `color`、`backgroundColor` | 正则 `^#[0-9a-fA-F]{3,8}$`，或命名色 `black` / `white` / `transparent` |
| 尺寸（7） | `fontSize`、`width`、`height`、`padding`、`margin`、`borderRadius`、`gap` | 正则 `^\d+(\.\d+)?(px|rem|em|%)$` |
| 枚举（2） | `fontWeight` | `Literal["normal","medium","semibold","bold"]` |
| | `textAlign` | `Literal["left","center","right"]` |

### 5.2 Patch v0.1 现状（`backend/src/genui_api/patch/models.py`）

- `PatchDocument`：`extra="forbid"`；`version: Literal["0.1"]`；`operations: list[UpdatePropsOperation] = Field(min_length=1)`。
- `UpdatePropsOperation`：`extra="forbid"`、`populate_by_name=True`；`op: Literal["update_props"]`；`target_node_id: str`（alias `targetNodeId`，`min_length=1`，拒绝纯空白）；`props: Dict[str, Any]`（拒绝空 dict，递归校验 JSON 兼容）。
- 只有一种 op；`contracts/patch/v0.1/schema.json` 由 `patch/schema_export.py` 确定性导出（`sort_keys=True, indent=2`），既有测试断言「导出结果 + 换行 == 已提交文件」。

### 5.3 Patch 应用现状（`backend/src/genui_api/patch/apply.py`）

`apply_patch`：校验 Patch 结构 → 校验源文档 → `deepcopy` → 遍历操作（`_find_node` + 浅合并 `props`）→ 后校验 → 返回 `DslDocument`。**`style` 完全不被读、不被写**。

### 5.4 Pipeline 现状（`backend/src/genui_api/refinement/pipeline.py`）

10 步不变量中与本轮相关的三步：

- 步骤 4：构造 `RefinementContext`，`selected_node_props` 为目标节点 props 的深拷贝；**不携带 style**。
- 步骤 7：遍历 `candidate["operations"]`，逐条要求 `targetNodeId == trusted_selected_node_id`（读的是 dict 键，与 op 类型无关）。
- 步骤 9：`verify_non_target_unchanged` 序列化两份文档，对目标节点**只剥离 `props`**（`_remove_props_from_node`）后深等比较 → **目标节点 style 的任何变化都会导致 `non_target_mutation_detected`（500）**。既有测试 `tests/refinement/test_pipeline.py::test_target_style_change_detected`（Spec 005 AC-73）正是断言这一行为。

### 5.5 上下文与历史现状（`backend/src/genui_api/provider/base.py`）

- `ConfirmedTurn(frozen=True)`：`instruction` / `selected_node_id` / `selected_node_type` / `patch_props`；`as_wire_dict()` 输出 4 键 camelCase。
- `RefinementContext`：`instruction` / `selected_node_id` / `selected_node_type` / `selected_node_props` / `document_version` / `conversation_history: tuple[ConfirmedTurn, ...] = ()`。
- 常量单一事实来源：`MAX_HISTORY_TURNS = 20`、`MAX_HISTORY_CHARS = 50_000`、`MAX_TURN_PROPS_KEYS = 16`；`history_char_size()` 用 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))` 取 `len()`。

### 5.6 提示词现状（`backend/src/genui_api/llm/prompts.py`）

- 精修 SP：「唯一允许的操作」只列 `update_props`；「不可修改项」明确禁止 style（含「视觉样式调整暂不在本操作的能力范围内」「用户要求改样式…不要伪造 style 字段」）。
- 当前轮 UP：4 键 JSON `{instruction, selectedNodeId, nodeType, currentProps}`。
- 历史 user：3 键 JSON `{instruction, selectedNodeId, nodeType}`。
- 历史 assistant：确定性重建 `{"version":"0.1","operations":[{"op":"update_props","targetNodeId":…,"props":…}]}`。
- messages 布局：`[system] + (user_i, assistant_i) × N + [user_current]` = `2N+2`。

### 5.7 API 现状（`backend/src/genui_api/api/schemas.py`、`routes.py`）

- `RefineHistoryTurn`：4 个 camelCase 字段 `instruction` / `selectedNodeId` / `nodeType` / `patchProps`，`extra="forbid"`；`patchProps: dict[str, PatchPropValue]`，`PatchPropValue = str | int | float | bool | None`，键数 ≤ 16。
- `RefineRequest`：`document` / `selectedNodeId` / `instruction` / `history?`。
- `RegisteredNodeType`：9 种 Literal 镜像。
- 精修错误码 → HTTP：`invalid_instruction` / `invalid_source_document` / `target_node_not_found` / `invalid_request_structure` → 422；`provider_error` / `invalid_candidate_structure` / `candidate_boundary_violation` / `patch_application_failed` → 502；`non_target_mutation_detected` / `internal_error` → 500。

### 5.8 前端现状（`frontend/src/**`）

- 渲染：`dsl/types.ts` 的 `DslStyle` 已镜像 11 字段；`dsl/style.ts` 的 `mapDslStyle` 按 11 字段白名单映射为 `CSSProperties`——**渲染侧无需任何改动即可显示 style 变更**。
- 响应守卫：`api/refine.ts` 的 `isPatchOperationShape` **硬编码** `if (value.op !== 'update_props') return false`；`isPatchDocumentShape` 逐条调用它。
- 派生：`App.tsx` 的 `derivePatchProps` 只取 `targetNodeId` 匹配的操作的 `props` 标量值，浅合并，键数上限 16。
- 类型：`api/types.ts` 的 `PatchOperation` 为单形状 `{op: "update_props", targetNodeId, props}`；`ConfirmedTurn` 为 `{instruction, selectedNodeId, nodeType, patchProps}`。
- 结果面板：逐条渲染 `refine-patch-op` / `refine-patch-target` / `refine-patch-props`（`JSON.stringify(operation.props)`）。
- Mock 链路：`provider/mock.py` 解析 `set_text:` 前缀，恒返回单条 `update_props`；E2E 通过真实后端 + MockProvider 运行，因此**E2E 要覆盖 style 必须扩展 Mock 指令**（DD-26）。

### 5.9 现状小结：style 在链路上的四段缺口

```text
[生成侧 SP: 已含 style 白名单] ✅
        ↓
[DSL 契约: Style 11 字段] ✅        [前端渲染: mapDslStyle] ✅
        ↓
[Patch 契约: 只有 update_props] ❌  ← 缺口 1
[apply_patch: 不处理 style]     ❌  ← 缺口 2
[Pipeline 步骤 4/9: 无 style]   ❌  ← 缺口 3（步骤 9 会主动拒绝）
[精修 SP/UP: 禁止且无上下文]     ❌  ← 缺口 4
[前端守卫: 硬编码 update_props] ❌  ← 缺口 5
```

## 6. Design Decisions

每条决策均为**最终拍板**（未拍板的只出现在 Open Decisions）。DD-01 ~ DD-30。

| # | 决策 | 理由 |
|---|------|------|
| DD-01 | **新增 `update_style` 操作**，wire 形状恰为 3 键：`{"op": "update_style", "targetNodeId": "<id>", "style": { … }}`；`extra="forbid"`、`populate_by_name=True`、`target_node_id` 复用 `alias="targetNodeId"` + `min_length=1` + 拒绝纯空白——与 `UpdatePropsOperation` **逐项同构** | 同构是最便宜的正确性来源：边界检查（步骤 7）读的是 `targetNodeId` 这一个键，只要新 op 的键名与约束与旧 op 一致，既有信任边界代码**一行不改**即对新 op 生效；错误码映射、issue path 形态、前端守卫结构也都能平移。任何「换个键名更好看」的变体都要以修改信任边界为代价，不划算 |
| DD-02 | **`style` 字段的类型直接复用 DSL 的 `Style` 模型**（`from genui_api.contracts.dsl import Style`），而**不是** `Dict[str, StyleValue]` | ① 白名单与值域必须只有一个事实来源：复用后「11 字段 + 正则 + Literal」自动跟随 DSL，不可能漂移；若用 `Dict[str, str|None]` 则必须在 patch 层复制一份白名单，产生第二处可漂移定义（AGENTS.md §5.10 精神）；② `Style` 已是 `extra="forbid"`，未知键在 **Patch schema 层**即被拒（DD-09）；③ 依赖方向合法：`patch/apply.py` 今天已 import `contracts.dsl`，`patch → contracts` 不是新方向、无循环 |
| DD-03 | **wire 层 style 值域恒为 `str | None`**：11 个字段的合法值全部是字符串（颜色 `#hex` / 命名色、尺寸「数字+单位」、两个枚举字符串），`null` 表示删除（DD-07）。**不使用** `PatchPropValue`（不接受 `int` / `float` / `bool`） | `fontSize: 16`（数字）是模型最常见的越界写法之一，允许 `int` 只会让「16」这种无单位值穿过 schema 层再被 DSL 值域拒绝，制造两跳失败；直接在类型层拒绝非字符串，使错误定位恒为一处。`bool` 与 `float` 对 style 没有任何合法语义 |
| DD-04 | **`PatchDocument.operations` 成为 discriminated union**：`PatchOperation = Annotated[Union[UpdatePropsOperation, UpdateStyleOperation], Field(discriminator="op")]`，`operations: list[PatchOperation] = Field(min_length=1)` | discriminator 让错误消息定位到具体 op 类型而不是「两个候选都不匹配」的联合噩梦；也让导出的 JSON Schema 带 `oneOf` + `discriminator.mapping`，对模型（JSON mode / schema 提示）与人类读者都更明确。**约束**：`_map_pydantic_error_to_code` 必须把 discriminator 失配（`union_tag_invalid` / `union_tag_not_found`）继续映射为 `invalid_op`，保持既有 issue code 集合语义（DD-28） |
| DD-05 | **同一请求允许混合 ops**：一份 `PatchDocument` 内可同时含 `update_props` 与 `update_style`，但**每一条**都必须 `targetNodeId == trusted selectedNodeId`（步骤 7 不变） | 「文案换成 X 并且加粗」是真实高频指令；若强制拆成两轮，用户要付两次模型延迟，且第一轮的中间态会进入 history。混合不放宽任何安全性质：边界检查逐条执行，与 op 类型无关（TB-2） |
| DD-06 | **style apply 语义 = 浅合并**：`node["style"] = {**existing_style, **operation_style}`，与 props 的合并语义**逐字同构**；未提及的 style 键保持原值 | 与 props 同构使 SP 只需一句话说明（降低模型出错率），也使「只给出需要变化的字段」这一已被 M4-02/M4-03 验证过的交互模式对 style 直接成立。深合并对扁平的 11 字段无意义 |
| DD-07 | **`null` 语义 = 删除该 style 键**（恢复该属性的渲染默认值）：候选中 `{"color": null}` → 从节点 style 中 `del` `color`。判定依据是「该键在候选中被显式给出」，实现上用 `Style.model_dump(exclude_unset=True)`（显式 `null` 会保留在结果中，未给出的键不出现） | 必须存在「清除」表达，否则「取消加粗」「去掉背景色」无法完成，用户只能靠猜一个「默认值」（而 DSL 并未定义默认值字面量）。选 `null` 而不是新增 `remove_style` 操作：语义等价、契约面积更小、模型更容易产出。用 `exclude_unset` 而非 `exclude_none` 是关键——后者会把「显式 null」与「未提及」混为一谈，删除语义就无法表达 |
| DD-08 | **空 style `{}` 被拒绝**：`UpdateStyleOperation` 的 `model_validator(mode="after")` 断言至少显式给出一个 style 键（`len(self.style.model_fields_set) >= 1`），否则 `ValueError` → issue code `empty_style` → `invalid_patch_structure` | 与 `UpdatePropsOperation` 拒绝空 props 完全同构：「操作必须有效果」。允许空操作会让「模型什么都没做」伪装成成功轮，进而污染 history 并让 `patch_style` 恒为空 |
| DD-09 | **未知 style 键 = schema 层拒绝**：`Style` 的 `extra="forbid"` 使 `boxShadow` / `position` / `zIndex` / `content` / `--var` 等一律在 `PatchDocument.model_validate` 阶段失败 → 步骤 6 → `invalid_candidate_structure`（502）；`apply_patch` 独立调用时为 `invalid_patch_structure` | 白名单必须是 **hard gate 且位于最外层**：越早拒绝，越不可能出现「部分应用」的中间态。这也是「不引入 arbitrary CSS」这一 Non-goal 的强制手段，而不只是文档承诺 |
| DD-10 | **非法 style 值 = 两道确定性闸门**：① 主闸门在 Patch schema 层（DD-02 复用 `Style` 的 field validators）→ 步骤 6 `invalid_candidate_structure`（502）；② 第二道闸门是 `apply_patch` 的应用后 DSL 全量校验（`_validate_patched_document`）→ `invalid_patched_document` → 步骤 8 `patch_application_failed`（502）。两道闸门都不得移除 | 研究基础曾预期非法值只在 DSL 后校验被拒；复用 `Style` 后它会更早失败（fail fast，错误定位更准）。但**第二道闸门必须保留**：它是「无论 Patch 层将来如何演化，落到文档上的东西一定是合法 DSL」这一不变量的兜底（AGENTS.md §9）。两者同为 502，前端与用户可见行为一致 |
| DD-11 | **同一份 Patch 内多条 `update_style` → 按数组顺序依次浅合并**（后者覆盖前者同名键），与多条 `update_props` 的现有语义同构；`update_props` 与 `update_style` **互不影响**（前者只写 `props`，后者只写 `style`） | 顺序语义必须被写明才可测；「按数组顺序」是唯一无歧义且与既有实现一致的选择。互不影响使混合 ops（DD-05）的结果可由两条独立规则推出，无需定义交叉规则 |
| DD-12 | **`RefinementContext` 新增 `selected_node_style: dict`（带默认值 `field(default_factory=dict)`）**，由 Pipeline 步骤 4 从**已校验文档**的目标节点派生（`target_node.style.model_dump(mode="json", by_alias=True, exclude_none=True) if target_node.style else {}`）；**不由模型提供、不由 history 提供、不由前端提供** | AGENTS.md §9：系统持有的 DSL Document 才是状态事实来源。style 上下文若来自 history 或前端，就会出现与文档竞争权威的第二份副本——这正是 Spec 009 DD-4 拒绝 `resultProps` 的同一条理由。`exclude_none=True` 使 `currentStyle` 只呈现「实际生效的样式」，不给模型灌 11 个 `null`（省 token 且更少误导） |
| DD-13 | **`ConfirmedTurn` 新增 `patch_style: dict`（默认 `field(default_factory=dict)`）**；`as_wire_dict()` 扩展为 5 键（`patchStyle` 恒出现，空时为 `{}`）。旧 4 参构造调用保持可用，缺省即 `{}` | 加默认字段是加性变更，M4-03 的全部构造点与测试零回归；`as_wire_dict()` 恒输出 5 键使 API 层（`model_dump(by_alias=True)`）与 Pipeline 层（`as_wire_dict()`）对同一份 history 仍得出**同一个** `history_char_size`（Spec 009 DD-22 的双侧一致性性质必须保住） |
| DD-14 | **当前轮 UP 扩展为 5 键 JSON**：`{instruction, selectedNodeId, nodeType, currentProps, currentStyle}`，键顺序固定如上；`build_refinement_user_prompt` 新增**带默认值**参数 `current_style: dict | None = None`（`None` 与 `{}` 等价，均序列化为 `{}`） | 模型必须看到当前 style 才能正确执行「再深一点」「大一号」这类相对样式指令，否则只能猜——而猜错的代价是 502。**这构成 UP 契约的一次受控版本升级**：M4-03 的「当前轮 UP 与 M4-02 逐字节相同」口径在本轮被**显式取代**为「UP 为 5 键且对同一 context 逐字节稳定」（见第 15 节与 AP-6）。带默认值的签名使既有 4 参调用点不必改写 |
| DD-15 | **精修 SP 一次受控版本升级**：删除「不得修改 style」与「不要伪造 style 字段」两条禁令，新增 ① `update_style` 操作说明与 wire 形状、② **完整 11 字段 style 白名单及其值域**、③ 浅合并与 `null` 删除语义、④ 「style 与 props 平级、不得写进 props」这一仍然成立的约束、⑤ 混合 ops 的允许与 target 约束。SP 仍为**无参纯函数**、每请求逐字节稳定、不含任何用户内容 | Spec 008 曾刻意不把 style 白名单写进精修 SP，理由是「那会诱导模型产出必然失败的候选」——该理由随本轮契约扩展而**失效**：现在 style 白名单内的输出是必然**成功**的。SP 必须如实描述模型真实拥有的能力，否则就是让契约去迁就旧文本（Spec 009 DD-7 的同一逻辑）。该项使既有测试 `test_refinement_system_prompt_declares_style_as_unmodifiable` 的语义反转（AP-6） |
| DD-16 | **历史 assistant 确定性重建扩展**：`patch_props` 非空 → 输出 `update_props` op；`patch_style` 非空 → 追加 `update_style` op（顺序恒为 props 在前、style 在后）；两者皆空 → **退化为 M4-03 行为**（单条空 props 的 `update_props` op），保证既有历史 prompt 测试逐字节不变 | 历史 assistant 是给模型的 few-shot 正例，必须与「当时真正被系统确认的那份 Patch」同构，否则模型会学到错误的操作形状。固定顺序使输出确定性可断言。保留退化分支是为了让 M4-03 的既有断言零修改仍全绿（回归护栏优先） |
| DD-17 | **前端 `isPatchOperationShape` 升级为 discriminated 运行时守卫**：`op === 'update_props'` → 要求 `targetNodeId` 非空字符串 + `props` 为普通对象；`op === 'update_style'` → 要求 `targetNodeId` 非空字符串 + `style` 为普通对象；其他 `op` 值 → `false`。`api/types.ts` 的 `PatchOperation` 相应成为 TS discriminated union | 网络响应一律不可信（Spec 006 口径 / 记忆化规范「Network response is untrusted」）：下游 `derivePatchProps` / `derivePatchStyle` / 结果面板都会**结构化读取** `props` 或 `style`，因此每条 op 的形状必须在守卫层被逐条确认，不能靠 TS 静态类型（编译期类型不产生运行时检查） |
| DD-18 | **新增 `derivePatchStyle(patch, selectedNodeId)`**，逻辑镜像 `derivePatchProps`：只取 `op === 'update_style'` 且 `targetNodeId` 匹配的操作 → 按数组顺序浅合并 → **只保留 `string` 与 `null` 值**（丢弃 number / boolean / object / array）→ 键数超过 `MAX_TURN_STYLE_KEYS` 时按插入顺序保留前 11 个 | 与 props 侧同构使「下一轮请求必然满足后端 schema」继续成为前端可自证的性质（Spec 009 DD-17）。值域收窄到 `string | null` 与 DD-03 严格对齐——前端不得产出后端会 422 的 history |
| DD-19 | **前端 `ConfirmedTurn` 扩展 `patchStyle?: Record<string, StylePatchValue>`**（`StylePatchValue = string | null`，新增类型）；构造 turn 时**仅当派生结果非空才写入该键**，请求体因此在纯 props 轮次中与 M4-03 逐字节相同 | 可选 + 省空键使「旧请求形态」在生产链路上继续真实存在（并被既有测试覆盖），向后兼容不靠承诺而靠请求体形状可断言（AC-09 / AC-25） |
| DD-20 | **Pipeline 步骤 9 扩展**：`_remove_props_from_node` 更名/扩展为 `_remove_mutable_fields_from_node`，对目标节点同时剥离 `props` 与 `style`；`verify_non_target_unchanged` 其余逻辑（全文档序列化 + 深等比较）一字不改 | 「非目标零变更」的正确定义是「除目标节点的**可变字段**外全等」。M4-04 把 style 纳入可变字段集合，剥离范围必须同步扩展，否则合法 style 修改会被判为 500——即缺口 3。**该扩展仅对目标节点生效**：任何其他节点的 style 变化仍然会被检出（TB-4），`id` / `type` / `children` 对**所有**节点（含目标）仍在比较范围内。该项使 Spec 005 AC-73 的既有断言语义反转（AP-6） |
| DD-21 | **style whitelist 恒等于 DSL `Style` 的 11 个字段，不多不少**，且**不提供任何扩展点**（无配置项、无环境变量、无「允许额外字段」开关）。扩展白名单必须走新 Spec + §6 审批（修改 DSL Schema） | 这是 AGENTS.md §5.5 / §9 在样式维度的直接体现：白名单是安全边界，任何运行期可调开关都等于把边界交给配置。硬编码 + 复用 DSL 模型（DD-02）使「不多不少」可被一条镜像漂移测试证明（AC-04） |
| DD-22 | **新增常量 `MAX_TURN_STYLE_KEYS = 11`**（= 白名单大小），定义在 `provider/base.py`（与既有三个上界常量同处，Spec 009 DD-21 的单一事实来源），由 `api/schemas.py` import 并再导出，前端 `App.tsx` 导出同值镜像并由后端漂移测试守护 | 上界必须存在（否则 history 的 style 键数无界），而其自然取值就是白名单大小——超过 11 个键的 style 在语义上不可能合法。放在 `provider/base.py` 是因为它约束的正是该模块定义的 `ConfirmedTurn`；不新建 `constants.py`、不新增 config 子系统 |
| DD-23 | **上下文预算影响评估：`MAX_HISTORY_CHARS` / `MAX_HISTORY_TURNS` 均不变**。`patchStyle` 每轮最多 11 个键、值为短字符串（典型 ≤ 12 字符），单轮增量典型 20–200 字符、理论上界约 `11 × (18 + 值长)`；空 style 轮次因 `as_wire_dict()` 恒含 `"patchStyle":{}` 而固定增加 18 字符（20 轮 = 360 字符）。20 轮总增量相对 50,000 字符预算 < 5% | 上界既是安全上界也是可复现性锚点，无理由随能力扩展而变动；把增量量级写清楚是为了证明「不变」是经过计算的决定，而不是遗漏。若将来实测触发上界，属 OD-2 范畴 |
| DD-24 | **`RefineHistoryTurn` 新增 `patchStyle` 可选字段**：`patch_style: dict[str, StylePatchValue] = Field(alias="patchStyle", default_factory=dict, max_length=MAX_TURN_STYLE_KEYS)`，其中 `StylePatchValue = str | None`。缺省 / `{}` 两态行为等价；`extra="forbid"` 不变；键名与值域非法 → 422 `invalid_request_structure`（不新增错误码） | 加可选字段是加性 API 变更：M4-03 的请求体（4 键 turn）继续 200（AC-09）。值域收窄到 `str | None`（不复用 `PatchPropValue`）与 DD-03 一致；`max_length` 复用 pydantic 对 dict 的键数约束（与 `patchProps` 的写法同构） |
| DD-25 | **Patch 版本号保持 `"0.1"`**；`contracts/patch/v0.1/schema.json` 由 `patch/schema_export.py` **重新导出**（不手写），既有一致性测试因此自动覆盖新 schema | 新增一个 op 类型是**加法扩展**：M4-03 及更早产出的所有 Patch 文档在新 schema 下**仍然合法**（`update_props` 分支未变），因此不构成破坏性变更，提升版本号只会带来版本协商、双 schema 维护与前端多分支解析的成本而无收益。契约文件必须由导出脚本生成，手写会立刻被 `test_exported_schema_matches_committed_file` 抓住 |
| DD-26 | **MockProvider 受控扩展**：新增两个确定性指令前缀——`set_style:k=v[,k=v…]` → 单条 `update_style`；`set_text_style:<text>|k=v[,k=v…]` → `update_props` + `update_style` 两条（混合场景）。值字面量 `null`（小写）解析为 JSON `null`；不做 trim、不做白名单过滤、不做值域校验（候选就该由校验层判定）。**其他任何指令（含 `set_text:` 与裸文本）的输出与 M4-03 逐字节相同** | E2E 与 mock 模式 API 测试跑的是真实后端 + MockProvider，若 mock 不能产出 style 候选，本轮能力就没有任何端到端证据（AGENTS.md §8）。Mock 刻意**不**净化非法输入，从而同时提供确定性的负向 E2E/API 路径（`set_style:boxShadow=1px` → 502）。既有指令逐字节不变使 Spec 009 DD-20 的「mock 链路零变化」性质对既有测试继续成立（AC-27） |
| DD-27 | **空 style 归一化**：若某次 apply 后目标节点的 style dict 变为空（所有键都被 `null` 删除），则**从节点上移除 `style` 键**，不保留 `{}` | 保持文档规范形态唯一：`style: {}` 与「无 style」在渲染与语义上等价，若两种表示同时存在，非目标零变更比较与前端快照断言就要处理两种等价形态。移除键使「文档形态」与「渲染结果」保持一对一 |
| DD-28 | **issue code 集合最小新增**：新增 `empty_style`（空 style）、`unknown_style_key`（extra 键）、`invalid_style_value`（值域失败）三个 **issue-level** code；`PatchError.code` 与 `RefinementError.code` 顶层错误码集合**零新增**（复用 `invalid_patch_structure` / `invalid_candidate_structure` / `patch_application_failed` / `candidate_boundary_violation`）；HTTP 状态码集合零新增 | 顶层错误码与状态码是公开 API 面，扩大它等于扩大对外契约与前端分支；issue 是明细层，扩充不影响任何调用方逻辑却让排障可定位。`invalid_op` 在 discriminated union 下必须继续被映射（DD-04），否则既有语义静默退化 |
| DD-29 | **前端最小可观察改动**：结果面板对 `update_style` 操作渲染新的 `refine-patch-style`（`JSON.stringify(operation.style)`），`update_props` 操作继续渲染既有 `refine-patch-props` testid；`refine-patch-op` / `refine-patch-target` 不变。**不新增样式面板 / 取色器 / diff 视图**；渲染侧（`dsl/**`）零改动 | 保留既有 testid 使 M3-02/M4-03 的既有前端测试与 E2E 断言零修改；新增独立 testid 使 style 结果可被 E2E 观察（否则「样式改了」只能靠计算样式断言，脆弱且与浏览器实现耦合）。TS discriminated union 迫使这一分支必须显式处理，否则编译失败——这是好事 |
| DD-30 | **常量镜像与漂移守护**：`MAX_TURN_STYLE_KEYS` 与 style 白名单（11 字段）在前端各有一份镜像（`App.tsx` 常量 / `dsl/style.ts` 既有 `STYLE_WHITELIST`），一致性由**后端测试读取前端源码文本**断言（延续 Spec 009 DD-21 的漂移测试手法），不引入构建期代码生成 | 跨语言镜像无法靠类型系统保证，只能靠测试；读源码文本的漂移测试成本极低且已在仓库中有先例（`conversation-history.test.tsx` 反向读取、后端读取 `App.tsx`），比引入 codegen 工具链（新依赖 + 构建复杂度）划算得多 |

## 7. Patch Contract Proposal

### 7.1 `update_style` 精确定义（wire，camelCase）

```jsonc
{
  "version": "0.1",
  "operations": [
    {
      "op": "update_style",                 // Literal，必填
      "targetNodeId": "hero.title",         // string，必填，min_length=1，非纯空白
      "style": {                            // object，必填，至少 1 个显式键（DD-08）
        "color": "#c0392b",                 // str | null，键必属 11 字段白名单
        "fontSize": "2rem",
        "fontWeight": "bold",
        "textAlign": "center",
        "backgroundColor": null             // null = 删除该键（DD-07）
      }
    }
  ]
}
```

后端模型（`backend/src/genui_api/patch/models.py`，实现时按此语义落地）：

```python
StylePatchValue = str | None            # DD-03（wire 值域，文档化用）

class UpdateStyleOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    op: Literal["update_style"]
    target_node_id: str = Field(alias="targetNodeId", min_length=1)
    style: Style                         # DD-02：复用 contracts.dsl.Style（extra="forbid"）

    @model_validator(mode="after")
    def _validate_fields(self):          # 与 UpdatePropsOperation 同构
        if self.target_node_id.strip() == "":
            raise ValueError("targetNodeId 不能为纯空白字符串")
        if len(self.style.model_fields_set) == 0:
            raise ValueError("style 不能为空对象")     # DD-08 → empty_style
        return self

PatchOperation = Annotated[
    Union[UpdatePropsOperation, UpdateStyleOperation],
    Field(discriminator="op"),
]

class PatchDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["0.1"]
    operations: list[PatchOperation] = Field(min_length=1)   # DD-04
```

### 7.2 与 `update_props` 的关系

| 维度 | `update_props` | `update_style` |
|------|----------------|----------------|
| 作用字段 | 节点的 `props` | 节点的 `style`（与 props **平级**的顶层字段） |
| 值域 | 该组件类型在 DSL 中定义的 props（标量） | style 白名单 11 字段，值为 `str | null` |
| 键白名单来源 | 各组件 props 模型（`extra="forbid"`） | `contracts.dsl.Style`（`extra="forbid"`，DD-02） |
| 合并语义 | 浅合并 | 浅合并（同构，DD-06） |
| 删除语义 | **无**（props 不支持删键，本轮不引入） | `null` 删键（DD-07） |
| 空对象 | 拒绝（既有） | 拒绝（DD-08） |
| target 约束 | `targetNodeId == trusted selectedNodeId` | **完全相同**（DD-01 / 步骤 7 不改） |
| 版本 | `0.1` | `0.1`（加法扩展，DD-25） |

**互不影响性质（DD-11）**：`update_props` 只读写 `node["props"]`，`update_style` 只读写 `node["style"]`；因此混合 ops 的最终结果 = 「props 侧按顺序合并」与「style 侧按顺序合并」两个独立结果的并集。

### 7.3 JSON Schema 影响（`contracts/patch/v0.1/schema.json`）

由 `patch/schema_export.py` 重新导出（DD-25），预期变化：`$defs` 新增 `UpdateStyleOperation` 与 `Style`（及其字段定义）；`properties.operations.items` 由单 `$ref` 变为带 `discriminator` 的 `oneOf`；`x-patch-version` 仍为 `"0.1"`。既有测试 `test_exported_schema_matches_committed_file` 自动成为新 schema 的一致性守护。

## 8. Style Semantics

设 `E` = 目标节点当前 style dict（无 style 时为 `{}`），`C` = 候选操作的 style（`Style.model_dump(exclude_unset=True)`，含显式 `null`）。

| # | 语义 | 规则 | 判定位置 / 错误码 |
|---|------|------|-------------------|
| SS-1 | **浅合并** | `merged = {**E, **C}`，随后删除 `merged` 中值为 `None` 的键（DD-06 / DD-07） | `apply_patch` 步骤 4（成功路径） |
| SS-2 | **null = 删除** | `C["color"] is None` → 结果中不含 `color`；对 `E` 中本就不存在的键使用 `null` 是**幂等无操作**（不报错） | 同上；「删不存在的键」不构成失败，因为结果状态与用户意图一致 |
| SS-3 | **空 style 归一化** | 若 `merged == {}` → 从节点删除 `style` 键（DD-27） | `apply_patch` 步骤 4 |
| SS-4 | **空 style 操作被拒** | 候选中 `"style": {}` → `empty_style` → `invalid_patch_structure`；经 Pipeline 时为步骤 6 → `invalid_candidate_structure`（502） | `UpdateStyleOperation` validator（DD-08） |
| SS-5 | **未知 style 键被拒** | `"boxShadow"` / `"position"` / `"--x"` / `"props"` 等 → `unknown_style_key` → 同 SS-4 路径 | `Style.extra="forbid"`（DD-09） |
| SS-6 | **非法 style 值被拒** | `"fontSize": "16"`（无单位）、`"color": "red"`、`"fontWeight": "800"`、`"fontSize": 16`（非字符串）、`"width": "calc(100% - 2px)"` → `invalid_style_value` → 同 SS-4 路径；即使绕过第一道闸门，应用后 DSL 全量校验仍会拒绝（`invalid_patched_document` → `patch_application_failed`） | `Style` field validators（DD-10 双闸门） |
| SS-7 | **多条 `update_style`** | 按 `operations` 数组顺序依次执行 SS-1，后者覆盖前者同名键；`null` 与非 `null` 可在不同 op 中交替，最终结果由最后一次写入决定（DD-11） | `apply_patch` 步骤 4 循环 |
| SS-8 | **混合 ops** | `update_props` 与 `update_style` 在同一份 Patch 中按数组顺序执行，各自只影响自己的字段；顺序不影响最终结果（互不影响，DD-11） | 同上 |
| SS-9 | **目标节点不存在** | 与既有行为一致：`patch_target_not_found` → Pipeline 步骤 8 → `patch_application_failed`（502） | `apply_patch` 的 `_find_node` |
| SS-10 | **`style` 写进 `props`** | 仍然非法（`props.style` 不是任何组件的 props 字段）→ 应用后 DSL 校验拒绝。既有安全测试 `test_style_inside_props_is_rejected` 继续成立 | DSL 校验（不变） |
| SS-11 | **不可变字段** | `id` / `type` / `children` 仍不可被任何操作修改；`update_style` 只能写 `style` 键（结构上无法表达其他写入） | 契约结构 + 步骤 9（对全部节点比较 `id`/`type`/`children`） |

**幂等性**：对同一节点重复应用同一份 `update_style`，结果文档逐字节相同（可断言，AC-06）。

## 9. Context Model

`RefinementContext` 扩展（`backend/src/genui_api/provider/base.py`）：

```python
@dataclass
class RefinementContext:
    instruction: str
    selected_node_id: str
    selected_node_type: str
    selected_node_props: dict
    document_version: str
    conversation_history: tuple[ConfirmedTurn, ...] = ()
    selected_node_style: dict = field(default_factory=dict)   # ← M4-04 新增（DD-12）
```

| # | 性质 | 说明 |
|---|------|------|
| CM-1 | **来源唯一** | `selected_node_style` 只由 Pipeline 步骤 4 从**已通过 `validate_dsl_document` 的文档**的目标节点派生；模型、history、前端均不能写入（AGENTS.md §9） |
| CM-2 | **派生规则确定** | `target_node.style.model_dump(mode="json", by_alias=True, exclude_none=True) if target_node.style else {}`；深拷贝后放入 context（Provider 的任何写入不影响调用方） |
| CM-3 | **加性兼容** | 带默认值 → M4-03 的 6 参 / M4-02 的 5 参构造调用全部继续可用，`selected_node_style == {}`（AC-13） |
| CM-4 | **Protocol 签名不变** | `async def generate_patch(self, context: RefinementContext) -> dict` 一字不改（延续 Spec 009 DD-14） |
| CM-5 | **不含其他节点信息** | 仍不提供兄弟 / 父节点 / 完整文档 / metadata（最小权限，Spec 008 DD-10） |

## 10. History Model

### 10.1 `ConfirmedTurn` 扩展

```python
@dataclass(frozen=True)
class ConfirmedTurn:
    instruction: str
    selected_node_id: str
    selected_node_type: str
    patch_props: dict
    patch_style: dict = field(default_factory=dict)          # ← M4-04 新增（DD-13）

    def as_wire_dict(self) -> dict:                          # 5 键，patchStyle 恒出现
        return {
            "instruction": self.instruction,
            "selectedNodeId": self.selected_node_id,
            "nodeType": self.selected_node_type,
            "patchProps": self.patch_props,
            "patchStyle": self.patch_style,
        }
```

### 10.2 向后兼容

| # | 情形 | 行为 |
|---|------|------|
| HM-1 | wire turn 缺 `patchStyle`（M4-03 形态） | 归一化为 `{}` → 200；messages 中该轮 assistant 内容与 M4-03 **逐字节相同**（DD-16 退化分支）（AC-09） |
| HM-2 | wire turn 显式 `"patchStyle": {}` | 与 HM-1 完全等价（两态行为一致，可断言） |
| HM-3 | props-only turn 与 style-only turn 与混合 turn | 三者均合法；style-only turn 的 `patchProps` 可为 `{}`（`patchProps` 仍为必填键，值可为空 dict——与 M4-03 一致） |
| HM-4 | `history_char_size` 计算 | API 层 `model_dump(by_alias=True)` 与 Pipeline 层 `as_wire_dict()` 均输出 5 键，两侧对同一 history 得同一个数（Spec 009 DD-22 性质保持，AC-24） |
| HM-5 | 上界 | `MAX_HISTORY_TURNS` / `MAX_HISTORY_CHARS` 不变；新增 `MAX_TURN_STYLE_KEYS = 11`（DD-22 / DD-23） |

### 10.3 历史 assistant 确定性重建（DD-16）

```text
patch_props 非空 且 patch_style 空  → [update_props]                    （= M4-03 输出，逐字节相同）
patch_props 空   且 patch_style 非空 → [update_style]
patch_props 非空 且 patch_style 非空 → [update_props, update_style]      （固定顺序）
patch_props 空   且 patch_style 空   → [update_props(props={})]          （M4-03 退化行为，保持不变）
```

序列化恒为 `json.dumps(..., ensure_ascii=False)`，`version` 恒 `"0.1"`，`targetNodeId` 恒取 `turn.selected_node_id`（**不取** 任何模型原文）。

## 11. Prompt Architecture

### 11.1 System Prompt 升级（DD-15）

删除（两处禁令）：

- 「不得修改节点的 "style"：…视觉样式调整暂不在本操作的能力范围内。」
- 「用户要求改样式（颜色、字号、间距等）时，不要伪造 style 字段…」

新增 / 改写（固定文本，实施时按此语义落地）：

```text
# 允许的操作（两种）
- {"op": "update_props", "targetNodeId": "<选中节点的 id>", "props": { ... }}
- {"op": "update_style", "targetNodeId": "<选中节点的 id>", "style": { ... }}
- 除这两种以外不存在任何操作类型（不存在 add / remove / move / replace），写出来一定失败。
- 同一次输出可以同时包含这两种操作（例如同时改文案与颜色），但每一条的 targetNodeId 都必须是同一个选中节点。

# style 可修改范围（白名单，共 11 个，不得出现其他属性）
- color、backgroundColor：#hex（3~8 位）或 "black" / "white" / "transparent"。
- fontSize、width、height、padding、margin、borderRadius、gap：「数字+单位」，单位只能是 px / rem / em / %，例如 "16px"、"1.5rem"、"100%"。
- fontWeight：只能是 "normal" / "medium" / "semibold" / "bold"。
- textAlign：只能是 "left" / "center" / "right"。
- 语义为浅合并：只给出需要变化的字段，未提及的字段保持原值。
- 把某个字段设为 null 表示删除该样式（恢复默认外观）。
- 值必须是字符串或 null；数字（如 16）、布尔值一律非法。
- 不允许任意 CSS：任何未列出的属性都会导致整份 Patch 被拒绝。

# 仍然不可修改（硬性）
- 不得修改 "id" / "type" / "children"，不得新增、删除、移动节点。
- "style" 与 "props" 是节点上平级的两个字段：把 style 写进 props 一定失败，把 props 写进 style 也一定失败。
- 不得触碰目标节点之外的任何节点。
- 目标节点的当前样式以最后一条 user 消息的 currentStyle 为准（未列出的字段表示当前未设置）。
```

SP 必须保持的性质（可机械验证）：无参纯函数；跨请求逐字节稳定；不含任何 instruction / history 文本；仍包含 M4-02/M4-03 的既有要点 token（`update_props`、`targetNodeId`、`operations`、`0.1`、`JSON`、`children`、多轮语义段落）。

### 11.2 User Prompt 扩展（DD-14）

```jsonc
// 当前轮 UP：5 键，键顺序固定
{
  "instruction": "标题改成品牌红并且加粗",
  "selectedNodeId": "hero.title",
  "nodeType": "Heading",
  "currentProps": { "text": "Brew & Bean", "level": 1 },
  "currentStyle": { "fontSize": "2rem" }          // ← 新增；无 style 时为 {}
}
```

签名：`build_refinement_user_prompt(instruction, selected_node_id, node_type, current_props, current_style: dict | None = None)`；`None` 与 `{}` 等价。

### 11.3 History message 扩展

- 历史 user：**仍为 3 键** `{instruction, selectedNodeId, nodeType}`，**不含** `currentProps`、**不含** `currentStyle`（延续 Spec 009 DD-4：历史状态快照会与当前轮竞争权威）。
- 历史 assistant：按 DD-16 重建，可含 `update_style`。
- messages 布局仍为 `[system] + (user_i, assistant_i) × N + [user_current]` = `2N+2`（不变）。

## 12. Trust Boundary

Pipeline 10 步中，**只有步骤 4 与步骤 9 发生变更**，其余步骤（含错误码集合）一字不改。

| 步骤 | M4-03 | M4-04 变更 |
|------|-------|------------|
| 1 instruction 校验 | 非空、≤1000 | 不变 |
| 2 源文档校验 | `validate_dsl_document` | 不变（style 值域校验本就在其中） |
| 3 查找目标节点 | 保存 `trusted_selected_node_id` | 不变 |
| 4 构造 context | props 深拷贝 + history 上界复核 | **新增** `selected_node_style` 派生（DD-12）；history 深拷贝携带 `patch_style` |
| 5 调用 Provider | 不可信候选 dict | 不变 |
| 6 候选结构校验 | `PatchDocument.model_validate` | 不变的调用点，因模型扩展而**自动**接受 `update_style` 并拒绝越界 style（DD-04 / DD-09 / DD-10） |
| 7 边界检查 | 逐 op 比对 `targetNodeId` | **不变**（读 dict 键，与 op 类型无关——通用性见 TB-2） |
| 8 应用 Patch | `apply_patch` | 不变的调用点；`apply_patch` 内部新增 style 合并分支（DD-06 / DD-07 / DD-27） |
| 9 非目标完整性验证 | 剥离目标 `props` 后深等 | **扩展**为剥离目标 `props` + `style`（DD-20） |
| 10 构造返回值 | `{success, patch, document, integrity}` | 不变（envelope 零变化） |

| # | 保证 | 强制手段 |
|---|------|----------|
| TB-1 | **style 操作不能越权到其他节点** | 步骤 7 逐条要求 `targetNodeId == trusted_selected_node_id`（来源恒为 `request.selectedNodeId`）；越界 → 502 `candidate_boundary_violation` |
| TB-2 | **边界检查对 op 类型通用** | 步骤 7 读取的是 `op.get("targetNodeId", …)`，不分支于 `op` 值；因此任何未来新增的 op 类型**自动**受边界约束（这正是 DD-01 要求新 op 与旧 op 键名同构的收益） |
| TB-3 | **history 仍不授予任何权限** | 延续 Spec 009 DD-9：`patch_style` 只进入 Provider 上下文，不参与步骤 1/2/3/6/7/8/9 的任何判定 |
| TB-4 | **非目标节点 style 变更仍被检出** | 步骤 9 的剥离**只对目标节点**执行；任何其他节点的 style / props / id / type / children 变化 → 500 `non_target_mutation_detected`（AC-05） |
| TB-5 | **目标节点的 id / type / children 仍受保护** | 剥离集合恰为 `{props, style}`；`id` / `type` / `children` 仍参与深等比较（含目标节点） |
| TB-6 | **arbitrary CSS 在结构上不可达** | `Style.extra="forbid"` + 值域正则/Literal（DD-09 / DD-10 双闸门）；无任何配置开关可放宽（DD-21） |
| TB-7 | **模型输出永不直接成为状态** | 顺序不变：schema 校验 → 边界检查 → 应用到**副本** → 完整性校验 → 才返回；失败路径下调用方文档零变更（AC-30） |
| TB-8 | **前端二次不信任** | 响应 patch 逐条结构守卫（DD-17）；`integrity.nonTargetNodesUnchanged === true` 与 `selectedNodeId` 匹配检查不变（Spec 006 C-5/C-6/C-7） |

## 13. Failure Semantics

| # | 触发条件 | 错误码（顶层） | HTTP | issue code | 副作用 |
|---|----------|----------------|------|------------|--------|
| FS-1 | 候选 `op` 为未注册值（`update_styles` / `remove` / …） | `invalid_candidate_structure` | 502 | `invalid_op`（DD-28） | 文档零变更 |
| FS-2 | 候选 `style` 含未知键 | `invalid_candidate_structure` | 502 | `unknown_style_key` | 文档零变更 |
| FS-3 | 候选 style 值非法（无单位 / 非白名单颜色 / 非枚举 / 非字符串） | `invalid_candidate_structure` | 502 | `invalid_style_value` | 文档零变更 |
| FS-4 | 候选 `style` 为 `{}` | `invalid_candidate_structure` | 502 | `empty_style` | 文档零变更 |
| FS-5 | 候选缺 `style` 键 / `style` 非对象 | `invalid_candidate_structure` | 502 | `schema_error` | 文档零变更 |
| FS-6 | `update_style` 的 `targetNodeId ≠ selectedNodeId`（含混合 ops 中任一条越界） | `candidate_boundary_violation` | 502 | 同名 | 文档零变更 |
| FS-7 | `targetNodeId` 在文档中不存在（仅当等于 `selectedNodeId` 且文档无该节点，理论上被步骤 3 提前拦截） | `patch_application_failed` | 502 | `patch_application_failed` | 文档零变更 |
| FS-8 | 应用后文档不再合法（第二道闸门，DD-10） | `patch_application_failed` | 502 | `patch_application_failed` | 文档零变更 |
| FS-9 | 非目标节点被修改（含其 style） | `non_target_mutation_detected` | 500 | 同名 | 文档零变更 |
| FS-10 | 请求 history 中 `patchStyle` 键数 > 11 / 值非 `str|null` / turn 含未知键 | `invalid_request_structure` | 422 | 同名 | Provider **不被调用** |
| FS-11 | history 条数 > 20 或序列化字符数 > 50,000 | `invalid_request_structure` | 422 | 同名 | Provider **不被调用** |
| FS-12 | 前端收到含非法 `update_style`（缺 `style` / `style` 非对象 / 未知 `op`）的响应 | 本地 `invalid_response` | — | — | 不写文档、不入 history |

不新增顶层错误码、不新增 HTTP 状态码（DD-28）。所有失败路径均 fail closed：文档、history、前端 state 三者同时零变更。

## 14. Frontend Trust Boundary

### 14.1 类型（`frontend/src/api/types.ts`）

```ts
export type StylePatchValue = string | null;                     // DD-03 对齐

export interface UpdatePropsOperation {
  op: 'update_props';
  targetNodeId: string;
  props: Record<string, unknown>;
}

export interface UpdateStyleOperation {
  op: 'update_style';
  targetNodeId: string;
  style: Record<string, unknown>;
}

export type PatchOperation = UpdatePropsOperation | UpdateStyleOperation;   // discriminated union

export interface ConfirmedTurn {
  instruction: string;
  selectedNodeId: string;
  nodeType: string;
  patchProps: Record<string, PatchPropValue>;
  patchStyle?: Record<string, StylePatchValue>;                  // DD-19：空时省略该键
}
```

### 14.2 运行时守卫（`frontend/src/api/refine.ts`，DD-17）

```text
isPatchOperationShape(value):
  isRecord(value) 否 → false
  value.op === 'update_props' → isNonEmptyString(targetNodeId) && isRecord(props)
  value.op === 'update_style' → isNonEmptyString(targetNodeId) && isRecord(style)
  其他 op 值 → false
```

`isPatchDocumentShape` 逐条调用它（不变）。守卫必须是**运行时**检查——TS 类型不产生运行时保护（项目既有规范：Runtime validation required over TypeScript static type）。

### 14.3 派生与 turn 构造（`frontend/src/App.tsx`，DD-18 / DD-19）

```text
derivePatchStyle(patch, selectedNodeId) -> Record<string, StylePatchValue>:
  for op of patch.operations:
    if op.op !== 'update_style' → skip
    if op.targetNodeId !== selectedNodeId → skip
    for [k, v] of Object.entries(op.style):
      if !(typeof v === 'string' || v === null) → skip        // 净化：丢弃 number/boolean/object/array
      merged[k] = v
  键数 > MAX_TURN_STYLE_KEYS(11) → 按插入顺序保留前 11 个

turn 构造（步骤 9，与 REFINE_SUCCESS 同一次 dispatch）:
  patchProps = derivePatchProps(result.patch, snapshotSelectedNodeId)
  style      = derivePatchStyle(result.patch, snapshotSelectedNodeId)
  turn = { instruction, selectedNodeId, nodeType, patchProps, ...(有键时) patchStyle: style }
```

失败轮次仍在结构上无法入队（`REFINE_FAILURE` 分支不触碰 history，Spec 009 CS-3）。

### 14.4 展示（DD-29）

结果面板逐条渲染：`refine-patch-op`（op 名）、`refine-patch-target`；`update_props` → `refine-patch-props`（既有 testid，不变）；`update_style` → **新增** `refine-patch-style`。渲染器（`dsl/**`）零改动。

## 15. Backward Compatibility

| # | 项 | 口径 |
|---|----|------|
| BC-1 | **Patch 版本号** | 仍为 `"0.1"`；M4-03 及更早的所有合法 Patch 文档在新 schema 下**仍然合法**（加法扩展，DD-25） |
| BC-2 | **props-only 轮次** | 请求 / 响应 / messages / 文档演进与 M4-03 **完全一致**；`patchStyle` 在请求体中被省略（DD-19），历史 assistant 重建逐字节相同（DD-16 退化分支） |
| BC-3 | **旧 history（无 `patchStyle`）** | 仍被接受（422 不会因缺该键触发）；缺省与 `{}` 两态等价（HM-1 / HM-2） |
| BC-4 | **`RefinementContext` / `ConfirmedTurn` 构造** | 新字段均带默认值 → M4-02 的 5 参、M4-03 的 6 参构造与 4 参 turn 构造全部继续可用（CM-3 / DD-13） |
| BC-5 | **Provider Protocol** | 签名一字不改（CM-4） |
| BC-6 | **响应 envelope** | 仍为 `{success, patch, document, integrity}`；无新键、无新状态码、无新顶层错误码 |
| BC-7 | **Mock 既有指令** | `set_text:` 与裸文本指令的输出与 M4-03 **逐字节相同**（DD-26），既有 API 测试与 2 条既有 E2E 不受影响 |
| BC-8 | **前端既有 testid** | `refine-patch-op` / `refine-patch-target` / `refine-patch-props` / `refine-history-*` 全部保留（DD-29） |
| BC-9 | **UP 契约（例外，需审批）** | 当前轮 UP 从 4 键升级为 **5 键**——这是本轮**唯一**的 prompt 契约破坏点，**取代** Spec 009 DD-10 中「当前轮 UP 与 M4-02 逐字节相同」的口径。新口径：UP 恰 5 键、对同一 context 逐字节稳定、`currentStyle` 恒由文档派生（DD-14 / AP-6） |
| BC-10 | **既有断言语义反转（例外，需审批）** | 两条既有断言与本轮能力**互相排斥**，必须被替换（AP-6）：① `tests/refinement/test_pipeline.py::test_target_style_change_detected`（Spec 005 AC-73：目标节点 style 变化 → `False`）与 DD-20 冲突；② `tests/llm/test_prompts.py::test_refinement_system_prompt_declares_style_as_unmodifiable`（断言 SP 禁止 style 且不含白名单字段名）与 DD-15 冲突。此外两条「UP 恰 4 键」断言需改为 5 键 |

## 16. Allowed Files

新建：

- `backend/tests/contracts/test_patch_style_models.py` — `UpdateStyleOperation` / discriminated union 的正反向 schema 测试
- `backend/tests/contracts/test_patch_style_apply.py` — style 合并 / null 删键 / 归一化 / 未知键 / 非法值 / 多条与混合 ops / 幂等
- `backend/tests/refinement/test_style_pipeline.py` — Pipeline 级：步骤 4 派生 `currentStyle`、步骤 7 边界（style op）、步骤 9 剥离扩展与非目标完整性
- `backend/tests/llm/test_style_prompts.py` — SP 升级要点、UP 5 键、历史 assistant 含 `update_style`、SP 稳定性
- `backend/tests/api/test_style_refine_api.py` — API 级：6 场景 200、混合 ops、`patchStyle` 兼容矩阵、常量漂移、OpenAPI schema
- `backend/tests/security/test_style_injection.py` — arbitrary CSS / 越界 style / 污染 history / 危险值的安全行为
- `backend/tests/llm/test_real_style_smoke.py` — opt-in（`@pytest.mark.real_llm` + `GENUI_RUN_REAL_LLM=1`），默认 skip
- `frontend/src/test/style-refinement.test.tsx` — 守卫、`derivePatchStyle`、turn 构造、请求体形态、面板展示
- `frontend/e2e/style-refinement.spec.ts` — 浏览器内 style 精修全流程
- `frontend/e2e/golden-path.spec.ts` — Golden Path：生成 → 选中 → 文案 → 颜色 → 尺寸 → non-target unchanged（AC-39；若选择在 `style-refinement.spec.ts` 内交付则不新建此文件）

允许修改（最小增量）：

- `contracts/patch/v0.1/schema.json` — **由 `patch/schema_export.py` 重新导出**，不手写（**§6 审批：修改 Patch Schema**）
- `backend/src/genui_api/patch/models.py` — 新增 `UpdateStyleOperation` / `PatchOperation` union / `StylePatchValue`；`PatchDocument.operations` 类型变更（**§6 审批**）
- `backend/src/genui_api/patch/apply.py` — 步骤 4 新增 style 分支（合并 / null 删键 / 空归一化）；`_map_pydantic_error_to_code` 新增三个 issue code 并保持 `invalid_op` 映射（**§6 审批**）
- `backend/src/genui_api/patch/__init__.py` — 导出新符号（`UpdateStyleOperation` 等）
- `backend/src/genui_api/provider/base.py` — `RefinementContext.selected_node_style`、`ConfirmedTurn.patch_style`、`as_wire_dict` 5 键、`MAX_TURN_STYLE_KEYS`（**§6 审批：跨模块基础抽象**）
- `backend/src/genui_api/refinement/pipeline.py` — 步骤 4 派生 style + history 携带 `patch_style`；步骤 9 剥离扩展（**§6 审批**）
- `backend/src/genui_api/llm/prompts.py` — SP 受控升级、UP 5 键、历史 assistant 重建扩展（**§6 审批：prompt 契约升级**）
- `backend/src/genui_api/api/schemas.py` — `RefineHistoryTurn.patchStyle`、`StylePatchValue`、re-export `MAX_TURN_STYLE_KEYS`（**§6 审批：公开 API**）
- `backend/src/genui_api/api/routes.py` — 仅 wire → `ConfirmedTurn` 转换处透传 `patch_style`
- `backend/src/genui_api/provider/mock.py` — 新增 `set_style:` / `set_text_style:` 指令；既有行为逐字节不变（**§6 审批：DD-26**）
- `frontend/src/api/types.ts` — `PatchOperation` discriminated union、`StylePatchValue`、`ConfirmedTurn.patchStyle?`
- `frontend/src/api/refine.ts` — `isPatchOperationShape` 升级为 discriminated 守卫
- `frontend/src/App.tsx` — `derivePatchStyle`、turn 构造、`MAX_TURN_STYLE_KEYS` 镜像常量、面板 style 分支
- `frontend/src/app.css` — 仅新增 style 展示所需样式（如有）
- **既有测试的最小语义修订（仅以下 3 个文件、仅以下断言，**§6 审批 AP-6**）**：
  - `backend/tests/refinement/test_pipeline.py` — 仅 `test_target_style_change_detected`（改为断言「目标节点 style 变化不再构成 non-target mutation」，并新增「非目标节点 style 变化仍被检出」的对偶断言）
  - `backend/tests/llm/test_prompts.py` — 仅 `test_refinement_system_prompt_declares_style_as_unmodifiable`（改为断言 SP 声明 `update_style` 能力与 11 字段白名单）与 UP「恰 4 键」断言（改为 5 键）
  - `backend/tests/llm/test_history_prompts.py` — 仅 `test_current_user_prompt_has_exactly_four_keys`（改为 5 键）
- `docs/ARCHITECTURE.md` — 新增受控样式精修架构说明与 M4-04 状态（§4.1 / §17 / §18 / §19 与实现对齐，AC-37）
- `docs/GLOSSARY.md` — 如需新增术语（Style Patch / Style Whitelist）
- `README.md` — 「当前状态」行、「尚未实现」列表、Patch 最小示例（新增 `update_style`）、里程碑路线表与过时行删除（AC-33 ~ AC-36 / AC-38）
- `docs/PRODUCT.md` — **仅限陈述对齐**（使文档描述与最终实现一致）；**不得修改产品范围、验收要求或功能定义**（AC-33 ~ AC-38 的证据范围内）
- `specs/010-controlled-style-refinement.md`（本文件，仅在获批修订时）

## 17. Protected Files

以下路径 M4-04 **不得修改**（以 `git diff --exit-code` 证明）：

- `contracts/dsl/v0.1/schema.json`（**DSL 契约零变更**）、`examples/**`（Gold Case）
- `backend/src/genui_api/contracts/**`（`dsl.py` / `validation.py` / `schema_export.py`——style 白名单与值域一字不改）
- `backend/src/genui_api/generation/**`（**整个生成模块**）
- `backend/src/genui_api/llm/client.py`、`backend/src/genui_api/main.py`、`backend/pyproject.toml`
- `backend/src/genui_api/provider/openai_compat_provider.py`（Provider 只调用 `build_refinement_messages(context)`，无需感知 style）
- `frontend/src/dsl/**`（渲染器与 `mapDslStyle` 已支持 11 字段，零改动）
- `frontend/package.json`、`frontend/package-lock.json`、`frontend/vite.config.ts`、`frontend/playwright.config.ts`
- 全部既有测试文件，**除** §16 明确列出的 3 个文件的指定断言之外（含 `frontend/src/test/**` 与 `frontend/e2e/**` 既有 3 个 spec 全部零修改）
- `frontend/src/test/malformed-patch.test.tsx`（M4-03 closure regression，Owner 已授权新建，见 §1.2）
- `AGENTS.md`、`specs/000-project-foundation.md` ~ `specs/009-multi-turn-context-stability.md`
- `.env.example`、`.gitignore`
- 不删除任何文件；不使用 `eval` / `exec` / `subprocess` / `pickle`；不引入任何新依赖

**清单一致性声明（M4-04 定稿）**：`docs/PRODUCT.md` 与 `README.md` **只出现在 §16 Allowed Files**（限定为陈述对齐，不得改变产品范围、验收要求或功能定义），**不出现在本节 Protected Files**；`AGENTS.md` 与 `specs/000` ~ `specs/009` **只出现在本节**。除 §16 显式列出的 3 个既有测试文件（且修改范围被限定到具体测试函数级别）外，两份清单**无任何交集，无任何矛盾**——每个文件恰好归属一处。

## 18. Acceptance Criteria

共 40 条（AC-01 ~ AC-40），每条为**可自动验证的行为断言**（文档类 AC-33 ~ AC-38 以文件内容为证据，逐条人工核对；AC-40 为 opt-in 真实模型断言，无凭证时记为 `NOT RUN`）。模型侧断言除 AC-40 外统一通过注入 `OpenAICompatRefinementProvider(client=stub(...), model="test-model")` 或直接注入 stub provider 捕获，零真实网络请求。

### A. Patch contract

| # | 标准 |
|---|------|
| AC-01 | A patch `{"version":"0.1","operations":[{"op":"update_style","targetNodeId":"hero.title","style":{"color":"#c0392b"}}]}` validates via `PatchDocument.model_validate`; `operations[0]` is an `UpdateStyleOperation` instance with `target_node_id == "hero.title"`; `PatchDocument` still accepts pure `update_props` documents **and** mixed documents |
| AC-02 | Negative matrix on `update_style`, each raising `ValidationError` (via `apply_patch` → `PatchError("invalid_patch_structure")` with the stated issue code): unknown style key `boxShadow` → `unknown_style_key`; `style: {}` → `empty_style`; `fontSize: "16"` / `color: "red"` / `fontWeight: "800"` / `width: "calc(100% - 2px)"` → `invalid_style_value`; `fontSize: 16` (number) / `disabled: true`-style non-string value → `invalid_style_value`; missing `style`; `style: null`; `style: []`; extra key `props` inside the operation; `targetNodeId: ""` / `"   "` → `empty_target_node_id`; `op: "update_styles"` → `invalid_op` (discriminator failure still maps to `invalid_op`, DD-04 / DD-28) |
| AC-03 | `contracts/patch/v0.1/schema.json` equals `export_patch_schema() + "\n"` byte-for-byte (existing consistency test stays green); the exported schema contains `$defs.UpdateStyleOperation`, a `discriminator` on `op` for `operations.items`, and `x-patch-version == "0.1"` (**version unchanged**, DD-25) |
| AC-04 | Style whitelist drift: the set of field names accepted by `UpdateStyleOperation.style` equals exactly the 11 field names of `genui_api.contracts.dsl.Style`, equals the `STYLE_WHITELIST` literal parsed out of `frontend/src/dsl/style.ts`, and equals the key set of `DslStyle` parsed out of `frontend/src/dsl/types.ts` (DD-21 / DD-30) |

### B. Patch application semantics

| # | 标准 |
|---|------|
| AC-05 | Applying `update_style` to a node **with** existing style shallow-merges: pre-existing untouched style keys are preserved, provided keys are overwritten; every other node in the document is deep-equal unchanged (including its `style`), and the target node's `id` / `type` / `props` / `children` are unchanged |
| AC-06 | Applying the same `update_style` twice produces byte-identical documents (idempotence); applying to a node **without** any style creates the `style` object containing exactly the provided keys |
| AC-07 | `null` semantics: `{"color": null}` removes the `color` key from the node's style (DD-07); removing a key that does not exist succeeds as a no-op; when the last remaining key is removed, the node no longer carries a `style` key at all (`"style" not in node`, DD-27) |
| AC-08 | Order semantics: two `update_style` ops in one document merge in array order (later wins, including `null` after a value and a value after `null`); a mixed document (`update_props` + `update_style` on the same node) applies **both** — final props and final style each equal their independently-computed expectation, and swapping the two ops' order yields a byte-identical document (DD-11 / SS-8) |

### C. Context & history model

| # | 标准 |
|---|------|
| AC-09 | Backward compatibility of history: a request whose turns **omit** `patchStyle` → 200; a request with explicit `"patchStyle": {}` → 200; both produce **byte-identical** captured `messages`; the reconstructed history `assistant` message for such a turn is byte-identical to the M4-03 output (DD-16 degenerate branch) |
| AC-10 | `RefinementContext.selected_node_style` equals the target node's style dict derived from the **validated document** with `exclude_none=True` (a node with `style: {"fontSize": "2rem"}` yields exactly `{"fontSize": "2rem"}`; a node without style yields `{}`); a provider mutating `context.selected_node_style` does not mutate the caller's document (deep copy) |
| AC-11 | `ConfirmedTurn.as_wire_dict()` returns exactly 5 keys `instruction` / `selectedNodeId` / `nodeType` / `patchProps` / `patchStyle`, with `patchStyle == {}` for a 4-arg constructed turn; `ConfirmedTurn` remains frozen (attribute assignment raises `FrozenInstanceError`) |
| AC-12 | Turn-level bounds: `patchStyle` with 12 keys → 422 `invalid_request_structure`; `patchStyle` value of type `int` / `bool` / `float` / object / array → 422 (only `str` and `null` accepted, DD-24); `MAX_TURN_STYLE_KEYS == 11`, is the **same object** when imported from `genui_api.provider.base` and `genui_api.api.schemas`, and equals the literal parsed out of `frontend/src/App.tsx` (DD-22 / DD-30) |
| AC-13 | Additive compatibility: the M4-02 5-kwarg and M4-03 6-kwarg `RefinementContext` constructions still succeed with `selected_node_style == {}`; the 4-arg `ConfirmedTurn` construction still succeeds with `patch_style == {}`; `RefinementProvider.generate_patch` signature is unchanged |

### D. Prompt architecture

| # | 标准 |
|---|------|
| AC-14 | `build_refinement_system_prompt()` takes no arguments, is byte-stable across repeated calls and across different requests, contains **all 11** style field names, the `update_style` operation form, the shallow-merge statement, the `null` deletion statement, the "style 与 props 平级" statement, and retains all M4-02/M4-03 required tokens (`update_props`, `targetNodeId`, `operations`, `0.1`, `JSON`, `children`, the multi-turn clause); it contains **neither** the removed prohibition text ("视觉样式调整暂不在本操作的能力范围内") nor any current/history `instruction` text |
| AC-15 | The final `user` message parses as a JSON object with **exactly 5 keys** `instruction` / `selectedNodeId` / `nodeType` / `currentProps` / `currentStyle`; `currentStyle` deep-equals `context.selected_node_style`; for the same context the UP is byte-identical across repeated builds and independent of `history` (DD-14) |
| AC-16 | History `user` messages remain **exactly 3 keys** (no `currentProps`, no `currentStyle`); a history `assistant` message for a turn with non-empty `patch_style` parses deep-equal to `{"version":"0.1","operations":[{"op":"update_props",…},{"op":"update_style","targetNodeId":turn.selectedNodeId,"style":turn.patchStyle}]}` in that fixed order, and to a single `update_style` op when `patch_props` is empty (DD-16) |

### E. Pipeline & trust boundary

| # | 标准 |
|---|------|
| AC-17 | Positive path for all 6 scenarios (A `color`/`backgroundColor`, B `fontSize`, C `padding`/`margin`/`gap`, D `borderRadius`, E `fontWeight`/`textAlign`, F `width`/`height`): stub provider emits a valid `update_style` → 200, `integrity.nonTargetNodesUnchanged === true`, the returned document's target node carries the new style values, and every non-target node is deep-equal to its pre-request value |
| AC-18 | Mixed ops end-to-end: stub emits `update_props` + `update_style` on the selected node → 200; the returned document shows **both** the new prop value and the new style values; `integrity` is verified |
| AC-19 | Boundary: an `update_style` whose `targetNodeId ≠ selectedNodeId` → 502 `candidate_boundary_violation`, document deep-equal unchanged; a **mixed** candidate whose `update_props` is in-boundary but whose `update_style` is out-of-boundary → 502 as well (per-operation check, TB-2) |
| AC-20 | Non-target integrity: (a) a candidate mutating **another** node's `style` → 500 `non_target_mutation_detected`; (b) `verify_non_target_unchanged(original, patched, target_id)` returns `True` when only the target node's `style` differs (DD-20, inverting Spec 005 AC-73) and `False` when any other node's `style` differs; (c) it still returns `False` when the target node's `id` / `type` / `children` differ |
| AC-21 | Whitelist as a hard gate through the full pipeline: candidates with `boxShadow` / `position: "absolute"` / `--custom` / `content` / `zIndex` → 502 `invalid_candidate_structure`, document unchanged; a candidate putting a valid style dict inside `props` → 502 (`props.style` is not a DSL props field, SS-10) |
| AC-22 | Invalid style values through the full pipeline → 502 with document unchanged for: `fontSize: "16"`, `fontSize: 16`, `color: "red"`, `color: "#12"`, `fontWeight: "800"`, `textAlign: "justify"`, `padding: "1 rem"`, `width: "calc(100%)"` |
| AC-23 | Multi-turn style accumulation (Scenario B → C → D): three consecutive successful rounds on the same node changing `fontSize`, then `padding`, then `borderRadius` → each round returns 200 with verified integrity; the final document's target node carries **all three** style keys simultaneously; round *k*'s captured messages contain the *k-1* prior turns with their `update_style` ops in order; `currentStyle` in round *k*'s UP equals the confirmed style after round *k-1* (**Document is the sole source of truth for style**, DD-12) |
| AC-24 | `history_char_size` parity: for the same logical history, the value computed at the API layer (`[t.model_dump(by_alias=True) …]`) equals the value computed at the Pipeline layer (`[t.as_wire_dict() …]`); `MAX_HISTORY_TURNS == 20` and `MAX_HISTORY_CHARS == 50_000` are unchanged; a 20-turn history whose turns each carry 11 style keys is still accepted (200) — i.e. the budget change is non-breaking (DD-23) |
| AC-25 | Empty-style rejection and null through the pipeline: a candidate with `"style": {}` → 502 `invalid_candidate_structure` with issue code `empty_style`, document unchanged; a candidate with `{"backgroundColor": null}` on a node that has `backgroundColor` → 200 and the returned node no longer carries that key |

### F. Frontend behavior

| # | 标准 |
|---|------|
| AC-26 | Guard accepts valid `update_style`: a success response whose patch contains `{op:'update_style', targetNodeId, style:{color:'#fff'}}` is accepted (document replaced, no local `invalid_response`), and the panel renders `refine-patch-op` == `update_style` plus `refine-patch-style` containing the serialized style |
| AC-27 | Guard rejects malformed `update_style`, each case producing local `invalid_response` with **no** document/history mutation: missing `style`; `style: null`; `style: []`; `style: "x"`; missing `targetNodeId`; `targetNodeId: ''`; `op: 'update_styles'`; `op` absent |
| AC-28 | `derivePatchStyle` correctness: picks only `update_style` ops whose `targetNodeId` matches the submitted node; merges multiple matching ops in array order (later wins); keeps `string` and `null` values while discarding number / boolean / object / array; truncates to the first 11 keys by insertion order; returns `{}` when nothing matches; is deterministic across repeated calls |
| AC-29 | Turn construction & request shape: after a style round, `conversationHistory` has one turn whose `patchStyle` equals the derived style and whose `patchProps` equals the derived props; the **next** request body carries that `patchStyle`; after a props-only round the next request body's turn has **no** `patchStyle` key (byte-identical to M4-03 shape, DD-19); after a mixed round the turn carries both |
| AC-30 | Failure isolation unchanged: for a 502 style rejection, a local `invalid_response`, `nonTargetNodesUnchanged: false`, and an `integrity.selectedNodeId` mismatch (four cases) → `currentDocument`, `conversationHistory` and the history count UI are all unchanged |

### G. E2E, real model & regression

| # | 标准 |
|---|------|
| AC-31 | E2E (browser, real backend + MockProvider): selecting a node and submitting `set_style:color=#c0392b,fontSize=2rem` updates the target node's computed color and font-size while two witness nodes keep their Gold Case text **and** style; the panel shows `update_style` with `nonTargetNodesUnchanged: true`; a following `set_text_style:立即预订|fontWeight=bold` round shows both operations and both effects; a final `set_style:boxShadow=1px` round surfaces an error and leaves the document unchanged |
| AC-32 | Regression & scope: all Protected Files show zero diff (`git diff --exit-code`), notably `contracts/dsl/**`, `backend/src/genui_api/contracts/**`, `generation/**`, `frontend/src/dsl/**`, `AGENTS.md`, `specs/000`–`specs/009`; no new dependency (`backend/pyproject.toml`, `frontend/package.json`, `frontend/package-lock.json` unchanged); the 759 pre-existing backend tests pass (only the 4 explicitly approved assertions in 3 files modified, AP-6) together with the new M4-04 tests; 336 pre-existing frontend tests plus new tests pass; typecheck and build pass; Playwright runs the pre-existing 3 specs unmodified plus the M4-04 spec(s) green; the real-LLM style smoke is **opt-in and `skipped` by default** (`GENUI_RUN_REAL_LLM != "1"`) — when credentials are absent it must be reported as `NOT RUN — credentials not configured` and **never** as PASS |

### H. Documentation alignment & golden path (M4-04 final closure)

本组 AC 为 M4-04 FINAL IMPLEMENTATION MILESTONE 定稿新增。文档类 AC 的证据为对应文件的实际内容（逐条核对），不得以「已知悉」代替实际修改；AC-39 的 Golden Path E2E 与 AC-31 的 style E2E 可以为两个独立 spec 文件，若如此，则 §19 第 10 层与 V-16 的 spec 计数需同步上调。

| # | 标准 | 证据 | 结论 |
|---|------|------|------|
| AC-33 | README "当前状态"行准确反映 M4-04 完成状态（含 style 精修、多轮 style 上下文） | README.md L5 更新 | PASS / FAIL |
| AC-34 | README "尚未实现"列表移除已实现项（多轮对话上下文、update_style、Patch HTTP API） | README.md §尚未实现 更新 | PASS / FAIL |
| AC-35 | README Patch 示例包含 `update_style` 最小示例 | README.md §Patch v0.1 最小示例 新增 | PASS / FAIL |
| AC-36 | README L168 "Patch HTTP API 尚未实现"过时行删除 | README.md 行删除 | PASS / FAIL |
| AC-37 | ARCHITECTURE.md §4.1 / §17 / §18 / §19 与实现一致 | docs/ARCHITECTURE.md 相关章节更新 | PASS / FAIL |
| AC-38 | 里程碑路线表增加 M4-04 完成记录 | README.md §里程碑路线 更新 | PASS / FAIL |
| AC-39 | 存在一条完整 E2E 覆盖「生成 → 选中 → 文案精修 → 颜色精修 → 尺寸精修 → non-target unchanged」全链路（PRODUCT.md §9 步骤 1-5） | E2E spec 文件存在且通过 | PASS / FAIL |

### I. Real LLM multi-turn style smoke（opt-in）

| # | 标准 |
|---|------|
| AC-40 | Real LLM **multi-turn** style smoke（`backend/tests/llm/test_real_style_smoke.py`，`@pytest.mark.real_llm`，默认 skip）：在 `GENUI_RUN_REAL_LLM=1` 且凭证有效时，对同一 Heading 节点连续执行两轮**自然语言**指令 —— Round 1「把标题改成红色」→ 200 且 `color` 变为红色系合法值且非目标节点零变更；Round 2「再大一点」→ 200 且 `selectedNodeId` 与 Round 1 相同、Round 2 的 `currentStyle` 来自 Round 1 **已确认后的 Document**（非模型输出、非 history 回灌）、confirmed history 含 Round 1 的 `ConfirmedTurn`、产出合法 `fontSize` 修改、**Round 1 已确认的 `color` 未被丢失**（浅合并语义正确）、非目标节点零变更、Document 仍为唯一事实来源。凭证缺失时必须报告 `NOT RUN — credentials not configured`，**严禁标记为 PASS**；MockProvider E2E（AC-31 / AC-39）作为 deterministic CI evidence 保留不变，本条是真实模型行为的 opt-in 补充证据（详见 §19.1） |

## 19. Test Matrix

全部自动化测试离线运行（stub provider / stub model client / 注入 fetcher），零真实网络请求。数量为**最少**下限。

| # | 层 | 文件 | 最少数量 | 覆盖重点 |
|---|----|------|----------|----------|
| 1 | Patch schema（正/反） | `backend/tests/contracts/test_patch_style_models.py` | 14+ | `update_style` 正向；混合 operations 正向；纯 `update_props` 回归；未知键 / 空 style / 非法值 / 非字符串值 / 缺 `style` / `style` 非对象 / 额外键 / 空 `targetNodeId` / 未注册 `op`（→ `invalid_op`）；discriminator 行为；11 字段白名单与 DSL `Style` 一致（AC-01 ~ AC-04） |
| 2 | Patch application | `backend/tests/contracts/test_patch_style_apply.py` | 12+ | 有/无既有 style 的合并；未提及键保持；`null` 删键；删不存在键幂等；删空后移除 `style` 键；幂等重放；多条 `update_style` 顺序；混合 ops 双生效与换序等价；非目标节点零变更；应用后 DSL 校验兜底（AC-05 ~ AC-08） |
| 3 | Pipeline boundary | `backend/tests/refinement/test_style_pipeline.py`（A 部分） | 8+ | 步骤 4 派生 `currentStyle`（含 `exclude_none` 与深拷贝隔离）；步骤 6 接受 `update_style`；步骤 7 对 style op 与混合 op 逐条边界检查；越界 → 502 且文档零变更（AC-10 / AC-19） |
| 4 | Pipeline non-target integrity | `backend/tests/refinement/test_style_pipeline.py`（B 部分） | 6+ | 目标节点 style 变化 → `True`；非目标节点 style 变化 → `False`；目标 `id`/`type`/`children` 变化 → `False`；候选改他人 style → 500（AC-20） |
| 5 | Prompt / message | `backend/tests/llm/test_style_prompts.py` | 10+ | SP 含 11 字段与 `update_style` 形状、不含旧禁令、无参逐字节稳定、不含用户内容；UP 恰 5 键且 `currentStyle` 正确；历史 user 仍 3 键；历史 assistant 三种分支与退化分支（AC-14 ~ AC-16） |
| 6 | Multi-turn style history | `backend/tests/refinement/test_style_pipeline.py`（C 部分） | 5+ | B→C→D 三连轮累积；round *k* messages 含前 *k-1* 轮 style op；`currentStyle` 恒等于上一轮确认后的文档派生值；失败轮不污染（AC-23） |
| 7 | API schema | `backend/tests/api/test_style_refine_api.py` | 12+ | 6 场景 200；混合 200；`patchStyle` 缺省/`{}`/非空三态；12 键与非法值 → 422 且 Provider 未被调用；常量单一来源与前端镜像漂移；`history_char_size` 双侧一致；20 轮 × 11 键仍 200；OpenAPI `$defs.RefineHistoryTurn` 含 `patchStyle`、`PatchDocument` 含 `update_style`；mock 模式 `set_style:` / `set_text_style:` 行为；既有 `set_text:` 输出逐字节不变（AC-09 / AC-12 / AC-17 / AC-18 / AC-24 / AC-25 / BC-7） |
| 8 | Frontend runtime response validation | `frontend/src/test/style-refinement.test.tsx`（A 部分） | 10+ | 守卫接受合法 `update_style`；8 种 malformed 变体 → `invalid_response` 且零状态变更；混合 patch 逐条校验；未知 op 拒绝（AC-26 / AC-27） |
| 9 | Frontend state / history | `frontend/src/test/style-refinement.test.tsx`（B 部分） | 10+ | `derivePatchStyle` 6 条规则；turn 构造三形态；请求体含/省 `patchStyle`；失败四类不入队；面板 `refine-patch-style` 展示；既有 testid 不变（AC-28 ~ AC-30） |
| 10 | E2E | `frontend/e2e/style-refinement.spec.ts` | 1 spec | 浏览器内：style 轮 → 计算样式变化 + 见证节点零变更；混合轮 → 两个 op 与两种效果；非法 style 轮 → 报错且文档不变（AC-31） |
| 10b | E2E Golden Path | `frontend/e2e/golden-path.spec.ts`（或在第 10 层 spec 内交付） | 1 spec | 生成 → 选中 → 文案精修 → 颜色精修 → 尺寸精修 → non-target unchanged 全链路（PRODUCT.md §9 步骤 1-5，AC-39） |
| 11 | Real LLM opt-in smoke | `backend/tests/llm/test_real_style_smoke.py` | 1–2 | `GENUI_RUN_REAL_LLM != "1"` → skip；opt-in 时执行 §19.1 的**两轮**自然语言流程（Round 1「把标题改成红色」→ Round 2「再大一点」relative follow-up），断言 200 / 同一 selectedNodeId / `currentStyle` 来自已确认 Document / Round 1 的 `color` 未丢失 / 非目标零变更（AC-40；模型的选值品味不作必跑断言，延续 Spec 009 DD-19） |
| 12 | Security | `backend/tests/security/test_style_injection.py` | 8+ | arbitrary CSS（`position` / `boxShadow` / `--var` / `content` / `zIndex`）被拒；`props.style` 被拒；`javascript:` 类值在 style 中被拒（不匹配任何值域正则）；越界 style op 被拒；污染 history 的 `patchStyle` 不授予权限、不进入非 user role；超长 style 值触发字符上界；组合攻击下文档零变更（AC-21 / AC-22 / TB-3 / TB-6） |
| 13 | Full regression | 无新增文件 | — | 759 后端 + 336 前端 + 3 既有 E2E 全绿；除 AP-6 批准的 4 处断言外，既有测试零修改 |
| 14 | 文档对齐 | `README.md`、`docs/ARCHITECTURE.md`、`docs/PRODUCT.md`（无自动化测试） | — | 当前状态行 / 尚未实现列表 / Patch 最小示例含 `update_style` / 过时行删除 / 里程碑路线表 / ARCHITECTURE §4.1 §17 §18 §19；证据为 `git diff` 逐行审阅（AC-33 ~ AC-38） |

### 19.1 Real LLM Multi-turn Style Smoke（opt-in）

本小节精确定义第 11 层测试的行为口径（对应 AC-40）。它的目的不是评价模型的审美，而是证明**真实模型路径下多轮 style 精修的受控性质与 Mock 路径完全一致**。

**前置条件**：`GENUI_RUN_REAL_LLM=1` + 有效 API credentials（`GENUI_LLM_API_KEY` / `GENUI_LLM_BASE_URL` / `GENUI_LLM_MODEL`，均取自环境变量，仓库内一律使用 `<API_KEY>` 之类的占位符）。

**测试流程**：

Round 1:
- 选择具有确定初始 style 的 Heading 节点
- 自然语言指令：「把标题改成红色」
- 验证：
  - `success`（200）
  - 目标节点 `color` 变为红色系合法值（匹配 DSL 颜色值域）
  - non-target unchanged（`integrity.nonTargetNodesUnchanged === true`，且非目标节点逐一深等）

Round 2（同一 Heading，relative follow-up）:
- 自然语言指令：「再大一点」
- 验证：
  - `success`（200）
  - `selectedNodeId` 与 Round 1 相同
  - Round 2 的 `currentStyle` 来自 Round 1 **已确认后的 Document**（非模型输出、非 history 回灌，DD-12）
  - confirmed history 包含 Round 1 的 `ConfirmedTurn`（其 `patchStyle` 含 Round 1 的 `color`，DD-13）
  - Round 2 产生合法 `fontSize` style modification（匹配「数字 + 单位」值域）
  - **Round 1 已确认的 `color` 未被意外丢失**（style 浅合并语义正确，DD-06）
  - non-target nodes unchanged
  - Document remains source of truth（每轮的返回文档 = 系统对副本应用 + 完整性校验后的结果）

**credentials 不存在时**：报告 `NOT RUN — credentials not configured`（**严禁**标记为 PASS；参见 §20 的 V-16 附注与 AGENTS.md §8）。

**与 Mock 路径的关系**：MockProvider E2E（§19 第 10 / 10b 层，AC-31 / AC-39）作为 **deterministic CI evidence** 保留不变，是每次收口必跑的证据；Real LLM smoke 是**真实模型行为的 opt-in 补充证据**，不进入必跑清单，也不得替代 Mock 路径的确定性断言。

**不作断言的部分**（延续 Spec 008 DD-13 / Spec 009 DD-19）：具体色值、字号增幅、模型是否额外给出其他白名单字段——只要落在白名单与值域内、边界与完整性成立，即视为通过；不引入 repair 循环或重试。

## 20. Verification Commands

共 17 条（V-01 ~ V-17）。全部为 POSIX shell、使用**仓库相对路径**、从仓库根目录执行；需切换目录的统一用子 shell `( cd … && … )`；后端统一使用 `backend/.venv/bin/python`；前端统一使用 `npx`（不依赖 npm scripts 命名）。

```bash
# === 后端测试 ===

# V-01. 后端全量测试（759 既有 + 本轮新增；real_llm 应为 skipped）
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest --tb=short -q )

# V-02. 本轮新增测试合并运行
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest \
  tests/contracts/test_patch_style_models.py tests/contracts/test_patch_style_apply.py \
  tests/refinement/test_style_pipeline.py tests/llm/test_style_prompts.py \
  tests/api/test_style_refine_api.py tests/security/test_style_injection.py --tb=short -q )

# V-03. 既有链路零回归（契约 / 生成 / Provider / 既有 Pipeline / 既有 API / 既有安全）
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/contracts/ tests/generation/ \
  tests/provider/ tests/refinement/ tests/llm/test_prompts.py tests/llm/test_history_prompts.py \
  tests/llm/test_client.py tests/api/ tests/security/ --tb=short -q )

# === 契约与 Schema ===

# V-04. Patch JSON Schema 重新导出后与已提交文件逐字节一致，且版本号仍为 0.1
( cd backend && PYTHONPATH=src .venv/bin/python -m genui_api.patch.schema_export --stdout \
  | .venv/bin/python -c 'import json,sys; s=json.load(sys.stdin); \
assert s["x-patch-version"]=="0.1", s.get("x-patch-version"); \
assert "UpdateStyleOperation" in s["$defs"], sorted(s["$defs"]); \
print("PATCH SCHEMA OK: version 0.1 + update_style")' )
git diff --stat -- contracts/patch/v0.1/schema.json

# V-05. DSL 契约与渲染器零变更（style 白名单事实来源不动）
git diff --exit-code -- contracts/dsl/v0.1/schema.json examples/ \
  backend/src/genui_api/contracts/ backend/src/genui_api/generation/ \
  backend/src/genui_api/llm/client.py backend/src/genui_api/main.py \
  backend/pyproject.toml frontend/src/dsl/ frontend/package.json frontend/package-lock.json \
  AGENTS.md specs/000-project-foundation.md specs/009-multi-turn-context-stability.md \
  && echo "PROTECTED FILES OK: zero diff"

# V-06. style 白名单三方一致（后端 Style / 前端 style.ts / 前端 types.ts）
( cd backend && PYTHONPATH=src .venv/bin/python - <<'PY'
import re, pathlib
from genui_api.contracts.dsl import Style
from genui_api.patch.models import UpdateStyleOperation
backend = set(Style.model_fields)
patch_side = set(UpdateStyleOperation.model_fields["style"].annotation.model_fields)
root = pathlib.Path("..").resolve()
ts = (root / "frontend/src/dsl/style.ts").read_text(encoding="utf-8")
block = ts.split("STYLE_WHITELIST = [")[1].split("]")[0]
fe_whitelist = set(re.findall(r"'([A-Za-z]+)'", block))
types = (root / "frontend/src/dsl/types.ts").read_text(encoding="utf-8")
iface = types.split("interface DslStyle {")[1].split("}")[0]
fe_types = set(re.findall(r"(\w+)\?:", iface))
assert len(backend) == 11, sorted(backend)
assert backend == patch_side == fe_whitelist == fe_types, (
    sorted(backend), sorted(patch_side), sorted(fe_whitelist), sorted(fe_types))
print("STYLE WHITELIST OK — 11 fields, 4 sources aligned:", sorted(backend))
PY
)

# V-07. 上界常量单一事实来源与前端镜像（MAX_TURN_STYLE_KEYS）
( cd backend && PYTHONPATH=src .venv/bin/python - <<'PY'
import re, pathlib
from genui_api.provider import base as pbase
from genui_api.api import schemas as sch
assert pbase.MAX_TURN_STYLE_KEYS == 11, pbase.MAX_TURN_STYLE_KEYS
assert sch.MAX_TURN_STYLE_KEYS is pbase.MAX_TURN_STYLE_KEYS, "not the same object"
assert pbase.MAX_HISTORY_TURNS == 20 and pbase.MAX_HISTORY_CHARS == 50_000
app = (pathlib.Path("..").resolve() / "frontend/src/App.tsx").read_text(encoding="utf-8")
m = re.search(r"MAX_TURN_STYLE_KEYS\s*=\s*(\d+)", app)
assert m and int(m.group(1)) == pbase.MAX_TURN_STYLE_KEYS, m and m.group(0)
print("CONSTANT SOURCE OK — MAX_TURN_STYLE_KEYS=11, frontend mirror aligned")
PY
)

# === 行为专项（stub 驱动，离线） ===

# V-08. style apply 语义：合并 / null 删键 / 空归一化 / 幂等 / 混合 ops
( cd backend && PYTHONPATH=src .venv/bin/python - <<'PY'
import copy, json
from genui_api.patch.apply import apply_patch, PatchError
DOC = {"version": "0.1", "root": {"id": "page", "type": "Page", "props": {"title": "T"},
       "children": [{"id": "hero.title", "type": "Heading",
                     "props": {"text": "Brew", "level": 1},
                     "style": {"fontSize": "2rem", "color": "#111111"}},
                    {"id": "hero.sub", "type": "Text", "props": {"text": "sub"},
                     "style": {"color": "#222222"}}]}}
BEFORE = copy.deepcopy(DOC)

def patch(ops): return {"version": "0.1", "operations": ops}
def style_op(style, target="hero.title"):
    return {"op": "update_style", "targetNodeId": target, "style": style}
def node(doc, nid):
    return next(c for c in doc["root"]["children"] if c["id"] == nid)

# ① 浅合并：未提及键保留，非目标节点零变更
d = apply_patch(DOC, patch([style_op({"color": "#c0392b", "padding": "16px"})])).model_dump(
    mode="json", by_alias=True)
t = node(d, "hero.title")
assert t["style"]["fontSize"] == "2rem" and t["style"]["color"] == "#c0392b" \
    and t["style"]["padding"] == "16px", t["style"]
assert node(d, "hero.sub")["style"]["color"] == "#222222"
assert t["props"] == {"text": "Brew", "level": 1} and t["id"] == "hero.title"
assert DOC == BEFORE, "源文档被修改"
print("MERGE OK")

# ② null 删键 + 删不存在键幂等
d = apply_patch(DOC, patch([style_op({"color": None, "gap": None})])).model_dump(
    mode="json", by_alias=True)
t = node(d, "hero.title")
assert t["style"].get("color") is None and t["style"]["fontSize"] == "2rem"
print("NULL DELETE OK")

# ③ 删完所有键 → 节点上不再有 style（DD-27）
d = apply_patch(DOC, patch([style_op({"fontSize": None, "color": None})])).model_dump(
    mode="json", by_alias=True, exclude_none=True)
assert "style" not in node(d, "hero.title"), node(d, "hero.title")
print("EMPTY NORMALIZE OK")

# ④ 幂等 + 多条顺序 + 混合 ops 换序等价
p = patch([style_op({"fontWeight": "bold"})])
a = apply_patch(DOC, p).model_dump(mode="json", by_alias=True)
b = apply_patch(DOC, p).model_dump(mode="json", by_alias=True)
assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
d = apply_patch(DOC, patch([style_op({"padding": "8px"}), style_op({"padding": "24px"})]))
assert node(d.model_dump(mode="json", by_alias=True), "hero.title")["style"]["padding"] == "24px"
props_op = {"op": "update_props", "targetNodeId": "hero.title", "props": {"text": "New"}}
m1 = apply_patch(DOC, patch([props_op, style_op({"textAlign": "center"})])).model_dump(
    mode="json", by_alias=True)
m2 = apply_patch(DOC, patch([style_op({"textAlign": "center"}), props_op])).model_dump(
    mode="json", by_alias=True)
assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)
assert node(m1, "hero.title")["props"]["text"] == "New"
assert node(m1, "hero.title")["style"]["textAlign"] == "center"
print("IDEMPOTENT / ORDER / MIXED OK")

# ⑤ 负向：未知键 / 空 style / 非法值 / 数字值
for bad, label in [({"boxShadow": "1px"}, "unknown key"), ({}, "empty style"),
                   ({"fontSize": "16"}, "no unit"), ({"color": "red"}, "named color"),
                   ({"fontWeight": "800"}, "bad enum"), ({"fontSize": 16}, "number value")]:
    try:
        apply_patch(DOC, patch([style_op(bad)]))
    except PatchError as e:
        assert e.code == "invalid_patch_structure", (label, e.code)
        print(f"REJECT OK [{label}]:", e.issues[0].code)
    else:
        raise SystemExit(f"FAIL: {label} 未被拒绝")
assert DOC == BEFORE
print("STYLE APPLY SEMANTICS OK")
PY
)

# V-09. Pipeline：currentStyle 派生 + 步骤 9 剥离扩展 + 越界拒绝 + 非目标 style 检出
( cd backend && PYTHONPATH=src .venv/bin/python - <<'PY'
import asyncio, copy
from genui_api.contracts.validation import validate_dsl_document
from genui_api.refinement.pipeline import refine, RefinementError, verify_non_target_unchanged
DOC = {"version": "0.1", "root": {"id": "page", "type": "Page", "props": {"title": "T"},
       "children": [{"id": "hero.title", "type": "Heading", "props": {"text": "Brew", "level": 1},
                     "style": {"fontSize": "2rem"}},
                    {"id": "hero.sub", "type": "Text", "props": {"text": "sub"}}]}}
BEFORE = copy.deepcopy(DOC)
seen = {}

class Stub:
    def __init__(self, ops): self.ops = ops
    async def generate_patch(self, context):
        seen["style"] = context.selected_node_style
        seen["props"] = context.selected_node_props
        return {"version": "0.1", "operations": self.ops}

def run(ops, node="hero.title"):
    return asyncio.run(refine(document=DOC, selected_node_id=node,
                              instruction="改样式", provider=Stub(ops)))

# ① currentStyle 由已校验文档派生（exclude_none）
r = run([{"op": "update_style", "targetNodeId": "hero.title", "style": {"color": "#c0392b"}}])
assert seen["style"] == {"fontSize": "2rem"}, seen["style"]
assert r.integrity["nonTargetNodesUnchanged"] is True
tgt = r.document["root"]["children"][0]
assert tgt["style"]["color"] == "#c0392b" and tgt["style"]["fontSize"] == "2rem"
assert DOC == BEFORE
print("CONTEXT STYLE OK:", seen["style"])

# ② 混合 ops 同时生效
r = run([{"op": "update_props", "targetNodeId": "hero.title", "props": {"text": "New"}},
         {"op": "update_style", "targetNodeId": "hero.title", "style": {"fontWeight": "bold"}}])
tgt = r.document["root"]["children"][0]
assert tgt["props"]["text"] == "New" and tgt["style"]["fontWeight"] == "bold"
print("MIXED PIPELINE OK")

# ③ 越界 style op 与混合中的越界分支
for ops, label in [
    ([{"op": "update_style", "targetNodeId": "hero.sub", "style": {"color": "#000000"}}], "style out"),
    ([{"op": "update_props", "targetNodeId": "hero.title", "props": {"text": "x"}},
      {"op": "update_style", "targetNodeId": "hero.sub", "style": {"color": "#000000"}}], "mixed out"),
]:
    try:
        run(ops)
    except RefinementError as e:
        assert e.code == "candidate_boundary_violation", (label, e.code)
        print(f"BOUNDARY OK [{label}]")
    else:
        raise SystemExit(f"FAIL: {label} 未被拒绝")
assert DOC == BEFORE

# ④ 步骤 9 语义：目标 style 变化允许，非目标 style 变化仍被检出
orig = validate_dsl_document(DOC)
d1 = copy.deepcopy(DOC); d1["root"]["children"][0]["style"] = {"color": "#000000"}
assert verify_non_target_unchanged(orig, validate_dsl_document(d1), "hero.title") is True
d2 = copy.deepcopy(DOC); d2["root"]["children"][1]["style"] = {"color": "#000000"}
assert verify_non_target_unchanged(orig, validate_dsl_document(d2), "hero.title") is False
d3 = copy.deepcopy(DOC); d3["root"]["children"][0]["type"] = "Text"
d3["root"]["children"][0]["props"] = {"text": "x"}
assert verify_non_target_unchanged(orig, validate_dsl_document(d3), "hero.title") is False
print("STEP 9 SEMANTICS OK")
PY
)

# V-10. Prompt：SP 升级要点 + UP 恰 5 键 + 历史 assistant 含 update_style
( cd backend && PYTHONPATH=src .venv/bin/python - <<'PY'
import json
from genui_api.llm.prompts import (build_refinement_system_prompt, build_refinement_messages,
                                   build_refinement_history_user_prompt)
from genui_api.provider.base import ConfirmedTurn, RefinementContext
from genui_api.contracts.dsl import Style
sp = build_refinement_system_prompt()
assert sp == build_refinement_system_prompt()
for f in Style.model_fields:
    assert f in sp, f
for tok in ("update_style", "update_props", "targetNodeId", "operations", "0.1", "JSON",
            "children", "浅合并", "null", "平级"):
    assert tok in sp, tok
assert "视觉样式调整暂不在本操作的能力范围内" not in sp
ctx = RefinementContext(instruction="标题改红并加粗", selected_node_id="hero.title",
                        selected_node_type="Heading",
                        selected_node_props={"text": "Brew", "level": 1},
                        document_version="0.1",
                        conversation_history=(ConfirmedTurn(
                            instruction="字大一点", selected_node_id="hero.title",
                            selected_node_type="Heading", patch_props={},
                            patch_style={"fontSize": "2rem"}),),
                        selected_node_style={"fontSize": "2rem"})
msgs = build_refinement_messages(ctx)
assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"], msgs
up = json.loads(msgs[-1]["content"])
assert set(up) == {"instruction", "selectedNodeId", "nodeType", "currentProps", "currentStyle"}, up
assert up["currentStyle"] == {"fontSize": "2rem"}
assert set(json.loads(msgs[1]["content"])) == {"instruction", "selectedNodeId", "nodeType"}
hist = json.loads(msgs[2]["content"])
assert hist == {"version": "0.1", "operations": [
    {"op": "update_style", "targetNodeId": "hero.title", "style": {"fontSize": "2rem"}}]}, hist
assert "标题改红并加粗" not in sp and "字大一点" not in sp
print("PROMPT ARCHITECTURE OK — 5-key UP, style-aware SP, reconstructed update_style")
PY
)

# V-11. API：patchStyle 三态兼容 + 超限拒绝 + Provider 未被调用
( cd backend && PYTHONPATH=src .venv/bin/python - <<'PY'
import asyncio, copy, httpx
from genui_api.main import create_app
from genui_api.provider.base import MAX_TURN_STYLE_KEYS
DOC = {"version": "0.1", "root": {"id": "page", "type": "Page", "props": {"title": "T"},
       "children": [{"id": "hero.title", "type": "Heading",
                     "props": {"text": "Brew", "level": 1}, "style": {"fontSize": "2rem"}}]}}
BEFORE = copy.deepcopy(DOC)
calls = []

class Counting:
    async def generate_patch(self, context):
        calls.append(context)
        return {"version": "0.1", "operations": [
            {"op": "update_style", "targetNodeId": "hero.title", "style": {"color": "#c0392b"}}]}

app = create_app(refinement_provider=Counting(), generation_provider=object())

async def call(history):
    body = {"document": DOC, "selectedNodeId": "hero.title", "instruction": "改红"}
    if history is not None:
        body["history"] = history
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post("/api/v1/dsl/refine", json=body)

def turn(**extra):
    base = {"instruction": "字大一点", "selectedNodeId": "hero.title",
            "nodeType": "Heading", "patchProps": {}}
    base.update(extra)
    return base

# ① 缺省 / {} / 非空 三态均 200
for h, label in [(None, "omitted"), ([turn()], "no patchStyle"),
                 ([turn(patchStyle={})], "empty patchStyle"),
                 ([turn(patchStyle={"fontSize": "2rem"})], "with patchStyle")]:
    r = asyncio.run(call(h))
    assert r.status_code == 200, (label, r.status_code, r.text[:200])
    assert r.json()["integrity"]["nonTargetNodesUnchanged"] is True
    print(f"ACCEPT OK [{label}]")

# ② 超限与非法值 → 422 且 Provider 未被调用
calls.clear()
for h, label in [([turn(patchStyle={f"k{i}": "1px" for i in range(MAX_TURN_STYLE_KEYS + 1)})], "12 keys"),
                 ([turn(patchStyle={"fontSize": 16})], "int value"),
                 ([turn(patchStyle={"fontSize": True})], "bool value"),
                 ([turn(patchStyle={"fontSize": {"a": 1}})], "object value")]:
    r = asyncio.run(call(h))
    assert r.status_code == 422, (label, r.status_code, r.text[:200])
    assert r.json()["error"]["code"] == "invalid_request_structure", r.json()
    assert "document" not in r.json() and "patch" not in r.json()
    print(f"REJECT OK [{label}]")
assert calls == [], "FAIL: 非法请求仍调用了 Provider"
assert DOC == BEFORE
print("API PATCHSTYLE CONTRACT OK")
PY
)

# V-12. Mock 既有行为逐字节不变 + 新增 style 指令可用
( cd backend && PYTHONPATH=src .venv/bin/python - <<'PY'
import asyncio, json
from genui_api.provider.mock import MockProvider
from genui_api.provider.base import RefinementContext

def ctx(instruction):
    return RefinementContext(instruction=instruction, selected_node_id="hero.title",
                             selected_node_type="Heading",
                             selected_node_props={"text": "Brew", "level": 1},
                             document_version="0.1")

legacy = asyncio.run(MockProvider().generate_patch(ctx("set_text:新标题")))
assert legacy == {"version": "0.1", "operations": [
    {"op": "update_props", "targetNodeId": "hero.title", "props": {"text": "新标题"}}]}, legacy
plain = asyncio.run(MockProvider().generate_patch(ctx("裸文本")))
assert plain["operations"][0]["props"] == {"text": "裸文本"}, plain
styled = asyncio.run(MockProvider().generate_patch(ctx("set_style:color=#c0392b,fontSize=2rem")))
assert styled["operations"] == [{"op": "update_style", "targetNodeId": "hero.title",
                                 "style": {"color": "#c0392b", "fontSize": "2rem"}}], styled
mixed = asyncio.run(MockProvider().generate_patch(ctx("set_text_style:立即预订|fontWeight=bold")))
assert [o["op"] for o in mixed["operations"]] == ["update_props", "update_style"], mixed
cleared = asyncio.run(MockProvider().generate_patch(ctx("set_style:color=null")))
assert cleared["operations"][0]["style"] == {"color": None}, cleared
print("MOCK PROVIDER OK — legacy byte-identical, style directives available")
PY
)

# === 前端 ===

# V-13. 前端单元测试（336 既有 + 本轮新增）
( cd frontend && npx vitest run )

# V-14. 前端类型检查（discriminated union 必须编译通过）
( cd frontend && npx tsc --noEmit -p tsconfig.app.json )

# V-15. 前端生产构建
( cd frontend && npx vite build )

# === E2E 与 opt-in smoke ===

# V-16. Playwright（3 条既有 + 本轮新增 spec；style 精修 1 条、Golden Path 1 条若拆分交付则共 5 spec）
( cd frontend && npx playwright test )

# 附：opt-in 真实模型 style smoke —— 默认应为 skipped（不是 passed）
( cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/llm/ -k "real" -q -rs )

# === 范围纪律（AP-8 判据）===

# V-17. 零新依赖 + 范围零扩散：依赖清单与契约/生成/渲染模块均不得变更
git diff --exit-code -- \
  backend/pyproject.toml \
  frontend/package.json frontend/package-lock.json \
  frontend/vite.config.ts frontend/playwright.config.ts \
  backend/src/genui_api/generation \
  backend/src/genui_api/llm/client.py \
  backend/src/genui_api/main.py \
  backend/src/genui_api/provider/openai_compat_provider.py \
  frontend/src/dsl \
  AGENTS.md .env.example .gitignore
# 并确认未引入危险原语（预期无输出）
grep -rnE "\b(eval|exec|subprocess|pickle)\b" backend/src/genui_api --include="*.py" || echo "OK: no dangerous primitives"
```

补充说明：

- V-04 ~ V-12 中传入 `object()` 作为生成侧 Provider，仅为满足 Spec 008 DD-5 的「两侧显式注入 → 跳过配置校验」条件，本身不参与被测链路。
- 附加命令（`-k "real"`）的预期输出是 `skipped`，不是 `passed`；出现 `failed` 即视为不合格。真实 style smoke（`GENUI_RUN_REAL_LLM=1` + 真实凭证）为 opt-in，其行为口径见 **§19.1（两轮 relative follow-up，AC-40）**，不属必跑命令；未运行时在报告中写明 `Real style smoke: NOT RUN — credentials not configured`，**严禁伪造成功**。
- V-16 需要本地可用的 Playwright 浏览器；若环境缺失必须如实记录为未运行并说明原因，不得以「已通过单测」代替。
- V-05 的 `git diff --exit-code` 是范围纪律的机械证据；`contracts/patch/v0.1/schema.json` **不在**该清单中（本轮允许其变更，但必须由 V-04 证明是导出结果）。
- V-17 是 AP-8 四项边界口径的机械证据（无新依赖 / 生成模块零变 / 渲染层零变 / 无危险原语）；它与 V-05 互补：V-05 盯 DSL 契约与 Gold Case，V-17 盯依赖与非本轮模块。
- **文档文件的判据（M4-04 定稿口径）**：`docs/PRODUCT.md` 与 `README.md` 是 §16 Allowed Files（仅限陈述对齐），因此**不在** V-05 / V-17 的 `git diff --exit-code` 清单中；`AGENTS.md` 与 `specs/000` ~ `specs/009` 仍在清单内（V-05 抽查 `specs/000` 与 `specs/009` 两端）。文档类变更的判据是 AC-33 ~ AC-38 的逐条内容核对（`git diff -- README.md docs/PRODUCT.md docs/ARCHITECTURE.md` 逐行审阅），而不是「零 diff」。

## 21. Security Analysis

前提（AGENTS.md §9，项目既有规范）：**模型输出是不可信输入**，网络响应也是不可信输入。style 只是新增了一类可被模型请求的写入，安全模型不变。

| # | 保证 | 强制手段 |
|---|------|----------|
| S-1 | **style whitelist 是 hard gate，不是建议** | `Style.extra="forbid"` 在 Patch schema 层拒绝所有未列出属性（DD-09），并在应用后 DSL 全量校验处再拒一次（DD-10）。**没有任何配置项 / 环境变量 / 请求字段能放宽它**（DD-21）。SP 中的白名单描述只是提高一次成功率，不参与判定 |
| S-2 | **arbitrary CSS 不可达** | 11 字段之外无法表达；值域为固定正则与 Literal，`position` / `z-index` / `content` / `transform` / CSS 变量 / 简写属性 / `!important` / `calc()` / `url()` 全部不可表达（AC-21 / AC-22） |
| S-3 | **无脚本注入面** | style 值不可能承载可执行内容：颜色必须匹配 `^#[0-9a-fA-F]{3,8}$` 或三个命名色，尺寸必须匹配「数字+单位」，枚举为 Literal —— `javascript:` / `url(...)` / `expression(...)` / `<script>` 均不匹配任一值域。前端 `mapDslStyle` 也只映射白名单键，且渲染为 React `style` 对象（非 `dangerouslySetInnerHTML`） |
| S-4 | **越界写入不可能** | 步骤 7 对**每一条** op（含混合中的 style op）要求 `targetNodeId == trusted_selected_node_id`（TB-1 / TB-2）；步骤 9 对**除目标节点 props/style 之外**的一切做深等比较（TB-4 / TB-5） |
| S-5 | **模型不能成为状态事实来源** | `currentStyle` 由已校验文档派生（DD-12）；候选先应用到副本、通过完整性校验后才返回；任何失败路径下调用方文档零变更（AC-30 / FS-*） |
| S-6 | **history 不授予权限、不承载任意 payload** | 延续 Spec 009：history 不参与任何判定（TB-3）；`patchStyle` 值域仅 `str | null`、键数 ≤ 11、整份 history 字符数 ≤ 50,000（DD-22 / DD-24 / FS-10 / FS-11），超限 422 且 Provider 不被调用 |
| S-7 | **role injection 仍不可能** | wire 契约无 `role` 字段、`extra="forbid"`；messages 仍只由 `llm/prompts.py` 组装；历史 assistant 内容为**重建**结果，模型原文从不回灌（DD-16） |
| S-8 | **攻击面未扩大** | 不新增端点 / HTTP 状态码 / 顶层错误码 / 依赖 / 环境变量；不引入 `eval` / `exec` / `subprocess` / `pickle`；新增的三个 issue code 只出现在错误明细中（DD-28） |
| S-9 | **prompt injection 按能力定义** | 延续 Spec 008 DD-14：合法值必须被接受（例如 `Text.text = "<div>x</div>"`、`color = "#000000"`），只有结构性越界被拒；测试不得断言「响应中不许出现 HTML 样式字符」 |
| S-10 | **fail closed** | 任一闸门失败 → 文档、history、前端 state 三者同时零变更；前端守卫失败 → 本地 `invalid_response`，不写状态（FS-12 / AC-27） |
| S-11 | **凭证与内容不泄漏** | 可观察性边界不变（Spec 008 DD-15）：日志不记录 instruction 原文、history、模型输出原文、style 内容；错误响应仍为固定净化文案 |

## 22. Open Decisions

| # | 待决问题 | 说明与建议 |
|---|----------|------------|
| OD-1 | **是否在本轮同时引入 props 的删除语义**（`update_props` 支持 `null` 删键） | 本 Spec 明确**不做**（第 7.2 节）：props 的删除会触及「required 字段能否被删」这一 DSL 语义问题（例如 `Heading.text` 删掉即文档非法），需要逐组件定义可删字段集合，范围远大于 style。建议观察真实使用后另立 Spec |
| OD-2 | **是否需要为 style 提供语义化取值辅助**（如「主色」「深一点」映射到具体色值） | 本轮不做：这会引入设计 token / 主题体系（Non-goals）。当前由模型直接给出字面值，若真实使用中出现「模型选色不稳定」的证据，建议在 SP 中加入固定调色板示例（纯 prompt 层变更）而非引入 token 系统 |
| OD-3 | **`update_style` 是否应支持一次针对多个节点**（如「所有卡片圆角一致」） | 本轮不做（Non-goals：无选择器语义）：多节点写入会直接冲击「单选中节点」这一核心信任边界（AGENTS.md §5.3/§5.4）。若产品确需，建议以「前端发起多次单节点精修」的编排方式实现，而不是放宽 Patch 边界 |
| OD-4 | **UP 契约升级的口径确认（需所有者拍板）** | 本 Spec 建议：接受 UP 从 4 键升级为 5 键（DD-14 / BC-9），并同意 Spec 009 DD-10 中「当前轮 UP 与 M4-02 逐字节相同」的口径被本轮取代。若所有者希望保持 UP 逐字节冻结，则唯一替代方案是把 `currentStyle` 塞进 `currentProps`（**不推荐**：与 DSL 中 style/props 平级的事实相矛盾，会教模型把 style 写进 props，而那在契约层必然失败） |
| OD-5 | **既有断言语义反转的确认（需所有者拍板）** | Spec 005 AC-73（目标 style 变化 → 完整性失败）与 Spec 008 的「SP 禁止 style」断言与本轮能力**互相排斥**（BC-10）。本 Spec 建议：批准以最小范围替换这 4 处断言（AP-6），并在报告中逐条列出替换前后的语义。若不批准，M4-04 无法实施——请改为拒绝本 Spec 而非在实现中绕过测试（AGENTS.md §5.9） |

除以上五项外，本 Spec 已对任务书列出的全部设计点拍板：op 形状与类型定义、值域、union 结构、混合与顺序语义、null / 空 / 未知键 / 非法值判定位置、context 与 history 扩展方式、prompt 三层升级、信任边界与失败语义、前端守卫与派生、向后兼容口径、测试与验证清单。实现过程中如出现本 Spec 未覆盖的新决策点，必须暂停并上报（AGENTS.md §5.14），不得自行拍板。

## 23. Approval Gates

以下事项必须在**实施前**获得项目所有者明确批准（对应 AGENTS.md §6）。**未获批准前，Agent 不得修改** `contracts/patch/v0.1/schema.json`、`patch/**`、`provider/base.py`、`provider/mock.py`、`refinement/pipeline.py`、`llm/prompts.py`、`api/schemas.py`、`api/routes.py`、任何前端源文件与 §16 列出的 3 个既有测试文件。

| # | 审批项 | 内容 | AGENTS.md §6 条目 |
|---|--------|------|-------------------|
| AP-1 | **修改 Patch Schema：新增 `update_style` 操作** | `patch/models.py` 新增 `UpdateStyleOperation`（`op` / `targetNodeId` / `style`，`extra="forbid"`）；`operations` 成为 discriminated union；`style` 类型复用 `contracts.dsl.Style`；`contracts/patch/v0.1/schema.json` 由导出脚本重新生成；**`version` 仍为 `"0.1"`**（加法扩展，DD-01 ~ DD-04 / DD-25） | 修改 Patch Schema |
| AP-2 | **修改 Patch 应用语义** | `apply.py` 新增 style 浅合并、`null` 删键、空 style 归一化；新增 issue code `empty_style` / `unknown_style_key` / `invalid_style_value`，并保持 `invalid_op` 在 union 下的映射；**顶层错误码与 HTTP 状态码零新增**（DD-06 ~ DD-11 / DD-27 / DD-28） | 修改 Patch Schema（配套）/ 修改已确认的行为契约 |
| AP-3 | **扩展跨模块基础抽象** | `provider/base.py`：`RefinementContext` 追加带默认值 `selected_node_style`；`ConfirmedTurn` 追加带默认值 `patch_style` 且 `as_wire_dict()` 扩为 5 键；新增常量 `MAX_TURN_STYLE_KEYS = 11`（单一事实来源）。**Provider Protocol 签名不变**（DD-12 / DD-13 / DD-22） | 新增跨模块基础抽象 |
| AP-4 | **修改 Pipeline 步骤 4 与步骤 9** | 步骤 4 派生 `selected_node_style` 并深拷贝携带 `patch_style`；步骤 9 的剥离范围由 `{props}` 扩展为 `{props, style}`（**仅对目标节点**）。其余 8 步、错误码集合、非目标零变更强度不变（DD-12 / DD-20 / TB-4 / TB-5） | 新增跨模块基础抽象 / 修改已确认的行为契约 |
| AP-5 | **修改公开 API：`RefineHistoryTurn` 新增 `patchStyle`** | 可选字段 `patchStyle`，值域 `str | None`，键数 ≤ 11，缺省与 `{}` 等价；`extra="forbid"` 不变；违规复用 422 `invalid_request_structure`（不新增错误码）；响应 envelope 零变化；`routes.py` 仅透传（DD-24 / FS-10） | 修改公开 API |
| AP-6 | **Prompt 契约升级 + 4 处既有断言语义反转** | ① 精修 SP 移除 style 禁令、新增 `update_style` 说明与 11 字段白名单（DD-15）；② 当前轮 UP 由 4 键升级为 5 键（DD-14，取代 Spec 009 DD-10 的 UP 冻结口径）；③ 历史 assistant 重建扩展（DD-16）；④ 因此必须替换的既有断言共 4 处：`test_pipeline.py::test_target_style_change_detected`（Spec 005 AC-73 反转）、`test_prompts.py::test_refinement_system_prompt_declares_style_as_unmodifiable`（反转）、`test_prompts.py` 与 `test_history_prompts.py` 中各一处「UP 恰 4 键」（改为 5 键）。**除这 4 处外不修改任何既有测试**（BC-9 / BC-10 / OD-4 / OD-5） | 修改已经确认的验收标准 |
| AP-7 | **MockProvider 受控扩展** | 新增 `set_style:` / `set_text_style:` 两个确定性指令前缀；`set_text:` 与裸文本指令输出**逐字节不变**（DD-26 / BC-7）。理由：E2E 与 API 层需要一条不依赖真实模型的确定性 style 证据链；若不批准，AC-30（E2E）与 V-16 新增 spec 无法交付，须同时降级本 Spec 的 §19 第 10 层 | 修改已经确认的验收标准（Mock 行为契约） |
| AP-8 | **口径确认（无代码变更，仅确认边界）** | ① **不引入任何新依赖**（前后端 lockfile 与 `pyproject.toml` 零变更）；② **不引入 arbitrary CSS**——style 键集恒等于 DSL `Style` 的 11 字段，值域恒等于 DSL 正则/枚举（DD-21 / S-2）；③ **不引入 tree mutation**——本轮不新增 `add_node` / `remove_node` / `move_node` / `replace_node`（§4）；④ **DSL 契约零变更**（§17）；⑤ **Patch `version` 保持 `"0.1"`**（DD-25） | 修改已经确认的验收标准（边界确认） |

审批处置约定：

- AP-1 ~ AP-5 为**实施前置**：任一未获批准，则对应模块不得动工，本 Spec 整体不可实施（style 链路是一条端到端的最小闭环，无法只落地其中一段）。
- AP-6 / AP-7 若不获批准，**正确的处置是驳回或修订本 Spec**，而不是绕过、跳过、放宽或删除既有测试（AGENTS.md §5.9「不得削弱测试」）。Agent 在未获批准的情况下**不得**以 `xfail` / `skip` / 注释掉断言等方式规避 BC-9 / BC-10 所述冲突。
- AP-8 无需代码变更，仅需所有者确认边界口径；确认后即成为 §17 与 V-05 / V-17 的判据。
- 审批意见应记录在本 Spec 的 §22 Open Decisions 中（逐条标注「批准 / 驳回 / 修订后批准」），并据此把 Meta 状态由 `DRAFT` 改为 `APPROVED`。

## 24. Implementation Plan

实施顺序遵循「契约 → 应用 → 编排 → 提示词 → 边界外沿 → 前端 → 端到端」的自下而上依赖链。**每个阶段结束时该阶段列出的验证命令必须全绿才可进入下一阶段**；任一阶段出现红灯，先修复该阶段，不得带着红灯前进（AGENTS.md §5）。所有阶段完成后再执行一次 V-01 ~ V-17 全量收口。

| 阶段 | 范围 | 涉及文件 | 落地内容 | 阶段门槛（验证命令） |
|------|------|----------|----------|----------------------|
| **P-0** | 前置确认 | 无（只读） | 确认 §23 全部审批项已获批准并记录于 §22；确认工作区 clean、基线为 `759` 后端 / `336` 前端 / `3` E2E spec | `git status --short` 为空；V-01 / V-13 在**未改动**状态下全绿（基线复现） |
| **P-1** | Patch 契约层 | `patch/models.py`、`patch/__init__.py`、`contracts/patch/v0.1/schema.json`（导出生成）、新建 `tests/contracts/test_patch_style_models.py` | `StylePatchValue`；`UpdateStyleOperation`（复用 `contracts.dsl.Style`、`extra="forbid"`、空 style 拒绝）；`PatchOperation` discriminated union；`PatchDocument.operations` 换型；**`version` 不动**；重新导出 schema（DD-01 ~ DD-05 / DD-08 / DD-21 / DD-25） | V-04（导出逐字节一致且 `version == "0.1"`）、V-05、V-06、`tests/contracts/` 全绿 |
| **P-2** | Patch 应用层 | `patch/apply.py`、新建 `tests/contracts/test_patch_style_apply.py` | style 浅合并；`null` 删键；删空后移除 `style` 键；多条 / 混合 ops 顺序语义；`_map_pydantic_error_to_code` 新增 `empty_style` / `unknown_style_key` / `invalid_style_value` 且保持 `invalid_op`（DD-06 / DD-07 / DD-09 ~ DD-11 / DD-27 / DD-28） | V-08、V-04、`tests/contracts/` 全绿；顶层错误码集合与 HTTP 映射零新增 |
| **P-3** | 域模型与 Pipeline | `provider/base.py`、`refinement/pipeline.py`、既有 `tests/refinement/test_pipeline.py` 的**单个**断言替换、新建 `tests/refinement/test_style_pipeline.py` | `RefinementContext.selected_node_style`（带默认值）、`ConfirmedTurn.patch_style`（带默认值）、`as_wire_dict()` 5 键、`MAX_TURN_STYLE_KEYS = 11`；步骤 4 从 Document 派生 `selected_node_style`（Document 为唯一事实来源）；步骤 9 剥离范围扩为 `{props, style}` 且**仅对目标节点**（DD-12 / DD-13 / DD-20 / DD-22 / TB-4 / TB-5） | V-07、V-09、`tests/refinement/` 全绿；步骤 7 边界检查代码**零改动**（TB-2） |
| **P-4** | 提示词层 | `llm/prompts.py`、既有 `tests/llm/test_prompts.py` 与 `tests/llm/test_history_prompts.py` 的指定断言替换、新建 `tests/llm/test_style_prompts.py` | SP 移除 style 禁令、新增 `update_style` 说明与 11 字段白名单及值域；当前轮 UP 升级为 5 键（`+currentStyle`）；历史 assistant 确定性重建按四分支扩展；messages 布局仍为 `2N+2`、SP 仍为稳定前缀（DD-14 ~ DD-16 / DD-23） | V-10、`tests/llm/` 全绿（`real_llm` 应 skipped） |
| **P-5** | API 与 Mock | `api/schemas.py`、`api/routes.py`、`provider/mock.py`、新建 `tests/api/test_style_refine_api.py`、`tests/security/test_style_injection.py` | `RefineHistoryTurn.patchStyle`（可选、`str \| None`、≤ 11 键、缺省 ≡ `{}`）；`routes.py` 仅透传；MockProvider 新增 `set_style:` / `set_text_style:` 且既有指令逐字节不变（DD-24 / DD-26 / FS-10 / S-1 ~ S-11） | V-11、V-12、V-03、V-01 全绿；`extra="forbid"` 与响应 envelope 零变化 |
| **P-6** | 前端 | `api/types.ts`、`api/refine.ts`、`App.tsx`、`app.css`（如需）、新建 `src/test/style-refinement.test.tsx` | `PatchOperation` TS discriminated union；`isPatchOperationShape` 升级为按 `op` 分派的运行时守卫；`derivePatchStyle`；turn 构造携带 `patchStyle`；`MAX_TURN_STYLE_KEYS` 镜像；结果面板新增 style 分支且既有 testid 全部保留（DD-17 ~ DD-19 / DD-29 / BC-8） | V-13、V-14、V-15、V-06、V-07 全绿；`frontend/src/dsl/**` `git diff --exit-code` 为空 |
| **P-7** | 端到端与收口 | 新建 `frontend/e2e/style-refinement.spec.ts`、新建 Golden Path E2E spec、新建 `tests/llm/test_real_style_smoke.py`、`docs/ARCHITECTURE.md`、`docs/GLOSSARY.md`、`README.md`、`docs/PRODUCT.md` | 浏览器内 style 精修全流程（含多轮累积 Scenario B → C → D）；Golden Path E2E（生成 → 选中 → 文案 → 颜色 → 尺寸 → non-target unchanged，AC-39）；opt-in 真实模型**两轮** style smoke（§19.1 / AC-40：Round 1 改色 → Round 2「再大一点」relative follow-up；默认 skip，无凭据时记为 `NOT RUN — credentials not configured`）；文档同步与对外陈述对齐（AC-33 ~ AC-38）；完成报告中逐条填写 §「PDF Task 1 Final Requirement Traceability Matrix」并给出 §「Task 1 User Acceptance Handoff」可直接执行的启动与验收说明 | V-16（3 条既有 + 本轮新增 spec 全绿）、V-01 ~ V-17 **全量复跑**、`git status --short` 与 §16/§17 清单逐条对齐、§「M4-04 Hard Closure Definition」的 Closure Gate 逐条满足 |

分阶段实施的补充约束：

- **不得跳阶段并行**：P-1 未收口就动 P-2/P-3 会让 discriminated union 的错误码归属难以定位（DD-28 的 `invalid_op` 保持是 P-2 的核心风险点）。
- **既有测试的 4 处断言替换必须落在其所属阶段**（P-3 一处、P-4 三处），且每次替换都要在同一次提交内附上对偶的正向断言（例如「非目标节点 style 变化仍被检出」），保证测试强度不下降而只是语义重定向（AGENTS.md §5.9）。
- **每阶段结束需确认零扩散**：`git status --short` 中出现的文件必须全部在 §16 Allowed Files 内；一旦出现 §17 Protected Files 中的路径，立即回退该改动并复查。
- **回退单元**：每个阶段自身可独立回退（P-1 ~ P-5 为后端纯加法 + 两处剥离/映射调整，P-6 为前端加法）。若 P-7 的 E2E 无法在本地环境运行（缺 Playwright 浏览器），必须如实记录为未运行并说明原因，**不得**以单测代替（V-16 说明）。
- **提交策略**：建议 P-1 ~ P-7 全部完成、V-01 ~ V-17 全绿后**一次性提交** M4-04（与 M4-01 ~ M4-03 的收口方式一致）；提交信息需列出本轮审批项（AP-1 ~ AP-8）与被替换的 4 处既有断言。

## Task 1 User Acceptance Handoff

M4-04 Completion Report 必须提供普通用户能够直接执行的最终测试说明。M4-04 Implementation 完成后，Owner 应该不需要任何额外开发工作即可按此说明启动项目并真实测试。

本章与 §「PDF Task 1 Final Requirement Traceability Matrix」的 **User Demo / UAT Evidence** 列一一对应：矩阵里每条 requirement 的用户验证方式，都必须能在下面的 Golden Path 中被走到。

### Startup

#### 后端启动

```bash
cd backend
source .venv/bin/activate
# Mock 模式（无需 API key）：
GENUI_MODEL_PROVIDER=mock uvicorn genui_api.main:app --reload --port 8000

# Real LLM 模式：
GENUI_MODEL_PROVIDER=openai_compatible \
GENUI_LLM_API_KEY=<your-api-key> \
GENUI_LLM_BASE_URL=<api-base-url> \
GENUI_LLM_MODEL=<model-name> \
uvicorn genui_api.main:app --reload --port 8000
```

#### 前端启动

```bash
cd frontend
npm run dev
# 浏览器访问 http://localhost:5173
```

> 凭证一律通过环境变量传入，仓库内任何文件（含本 Spec、测试、夹具）**不得出现真实 key**，统一使用 `<your-api-key>` 之类的占位符（AGENTS.md §9）。可参考仓库根目录的 `.env.example`。

### Normal User Golden Path

用户启动项目后，可以通过正常 UI 完成以下完整旅程（使用自然语言，不使用 `set_style:` 等 Mock 协议指令）：

1. 在顶部输入框输入自然语言需求，例如「帮我做一个咖啡店落地页」→ 页面渲染初稿
2. 点击页面上某个 Heading 节点 → 出现蓝色选中框
3. 在精修输入框输入「把标题改成欢迎光临」→ 文案变更，其他节点不变
4. 继续输入「改成红色」→ 标题颜色变红
5. 继续输入「再大一点」→ 字号增大（relative follow-up 基于当前状态）
6. 继续输入「居中」→ `textAlign` 变为 center
7. 继续输入「增加一些内边距」→ padding 增加
8. 点击其他节点（如 Button）→ 选中态切换
9. 输入「把按钮文案改成立即预约，同时改成深色背景」→ 文案 + 背景色同时变更（mixed `update_props` + `update_style`）
10. 检查最终页面：之前修改的 Heading 样式保持不变

### Expected Results

用户应观察到：

- selected node 正确变化（文案 / 颜色 / 尺寸 / 布局按指令生效）
- non-target nodes 不变（之前未选中的节点保持原样）
- previous confirmed changes preserved（切换节点后回看，之前的修改仍在）
- relative instruction 正确基于当前状态工作（「再大一点」基于当前字号而非初始字号）
- 页面无需 full regeneration（每轮只做局部 Patch；结果面板显示的是 operation 列表与 `nonTargetNodesUnchanged: true`）
- 错误请求不会破坏已有页面状态（输入无法执行的指令时，页面保持不变并显示错误提示）

### Mock vs Real LLM

- **Mock 模式**：使用确定性 MockProvider，只响应 `set_text:` / `set_style:` / `set_text_style:` 格式的精确指令。自然语言（如「改成红色」）在 Mock 模式下不会被理解（Mock 不做语义解析）。Mock 模式用于开发、CI、E2E 确定性证据。
- **Real LLM 模式**：使用真实模型，理解自然语言精修指令。**Normal User Golden Path 需要 Real LLM 模式**。
- 两种模式共用同一条受控管线：白名单、单节点边界、非目标零变更、Document 为事实来源在两种模式下**完全一致**——切换 Provider 不放宽任何安全性质。

## M4-04 Hard Closure Definition

### Closure Gate

M4-04 CLOSED 意味着：

- PDF Task 1 100% implemented
- 不存在 M4-05
- 所有 PDF Task 1 requirements 在 §「PDF Task 1 Final Requirement Traceability Matrix」中为 PASS
- 所有 AC-01 ~ AC-40 为 PASS
- 所有 V-01 ~ V-17 为 PASS 或 NOT RUN（仅限 opt-in real smoke 在无 credentials 时）
- §「Task 1 User Acceptance Handoff」可直接执行，无需额外开发

### Post-M4-04: Task 1 Final Acceptance

定义严格为：

- READ-ONLY / VERIFICATION-ONLY AUDIT
- 独立确认 PDF requirement → implementation → test → demo 全部已存在
- 不承担新的 implementation / test creation / documentation completion / integration work / demo creation

### Reopening Condition

如果 Final Acceptance 发现某个明确属于 PDF Task 1 的功能仍需开发：

- M4-04 = NOT CLOSED（重新打开）
- 不创建 M4-05
- 在 M4-04 内补齐后重新申请 closure

### Engineering Phase Relationship

```text
M4-01 + M4-02 + M4-03 + M4-04 = PDF TASK 1 IMPLEMENTATION 100%
→ Task 1 Final Acceptance (verification only)
→ TASK 1 CLOSED
→ M5 / PDF Task 2
```
