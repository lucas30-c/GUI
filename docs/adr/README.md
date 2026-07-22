# ADR — 架构决策记录 (Architecture Decision Records)

## 用途

ADR 记录**真正影响多个模块、难以回滚**的重要架构决策及其理由。它的价值在于：半年后（或面试现场）能回答"当时为什么这么做"，而不是重新争论一遍。

## 什么时候写 / 不写

**该写**（与 AGENTS.md 的 Approval Gates 对应）：

- DSL 结构变更；
- Patch 语义变更；
- 存储方案变更（如本地 JSON → SQLite）；
- 模型 Provider 边界变更；
- 跨前后端协议变更。

**不该写**：

- 普通代码实现细节（函数怎么命名、模块怎么拆分）；
- 可以通过代码评审解决的局部选择；
- 已在 AGENTS.md / Spec 中明确规定、无备选方案的事项。

判断标准：如果一个决策改错了需要动多个模块、且回滚成本高，就值得一份 ADR；否则不值得。

## 命名方式

```text
NNNN-title-in-kebab-case.md
```

- `NNNN`：四位递增序号（0001、0002……），不跳号、不复用；
- 标题用英文小写连字符，能一句话说清决策主题。

示例：`0001-dsl-node-id-strategy.md`、`0002-patch-vs-full-dsl.md`

## 最小模板

```markdown
# NNNN. 决策标题

- 状态 (Status): Proposed | Accepted | Deprecated | Superseded by NNNN
- 日期 (Date): YYYY-MM-DD

## 背景 (Context)

促使本决策产生的背景与约束。为什么现在必须做决定。

## 决策 (Decision)

我们决定怎么做。一句话给出结论，随后给出必要的关键细节。

## 考虑过的备选方案 (Alternatives Considered)

考虑过哪些备选方案，各自因何被排除（简要）。

## 影响与后果 (Consequences)

正面与负面后果。对哪些模块有影响、后续需要跟进什么。
```

## 规则

1. ADR 一旦 Accepted 即为项目契约的一部分，修改它等同于修改架构，需走 Approval Gate。
2. 推翻旧决策时**不删除**旧 ADR，而是新建一份 ADR 并将旧的状态改为 `Superseded by NNNN`。
3. 每份 ADR 只记录一个决策；保持短小，超过一页说明该拆分了。
