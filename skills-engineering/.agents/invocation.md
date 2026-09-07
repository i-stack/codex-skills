# Agent 调用规范

## 调用流程

1. **接收任务** → 解析用户意图和关键词
2. **Skill 匹配** → 遍历已注册 skill 的 `AGENT-BRIEF.md`，判断是否命中触发条件
3. **加载 Skill** → 命中后依次完整读取：
   - `<skill>/SKILL.md` — 主入口和核心规则
   - `<skill>/references/<reference>.md` — 按路由表加载相关细则
   - `<skill>/OUT-OF-SCOPE.md` — 确认问题在 skill 范围内
4. **执行规则** → 严格按 skill 规则执行回答
5. **记录审计** → iOS 工程任务完成后追加 `<usage-audit>` 块

## 多 Skill 并行

多个 skill 同时命中时并行加载：
- `ios-engineer` + 全局 skills（engineering-discipline、cognitive-reasoning 等）可同时生效
- 全局 skills 提供正交约束层（输出结构、论证质量、真值接地）
- 平台 skills 提供领域知识和具体修法

## Skill 命名约定

| 类型 | 格式 | 示例 |
|------|------|------|
| 平台 skill | `<platform>-engineer` | `ios-engineer` |
| 全局技能 | `<domain>-<descriptor>` | `cognitive-reasoning`, `engineering-discipline` |
| 引用文件 | `snake_case.md` | `cognitive_expansion.md`, `swift_concurrency.md` |

## Agent 判定速查

遇到以下关键词时，对应 skill 应在 1 个 turn 内加载：

| 关键词 | Skill | 优先级 |
|--------|-------|--------|
| iOS / Swift / SwiftUI / Xcode / CocoaPods | ios-engineer | P0 |
| 卡顿 / 崩溃 / 内存泄漏 / 布局错位 | ios-engineer | P0 |
| 校准 / 真实 / 不确定 / 核验路径 | cognitive-reasoning (GR-011~013) | P1 |
| 挑战我 / 不要迎合 / red team / 反迎合 | cognitive-reasoning (CAM-001~005, Tier 2) | P1（认知对手模式，合并后的认知与论证纪律技能） |
| 逻辑 / 推断 / 因果 / 论证 | cognitive-reasoning (GR-010) | P1 |
| 写/改文档 / 文档卫生 / 禁过程叙事 | doc-hygiene | P1（writing-docs.md 强制 depends_on） |
| 根因 / 修复 / 安全 / 敏感信息 | engineering-discipline | P1 |
| 第一性原理 / 深层需求 / 问题偏差 | problem-analysis | P1 |
| 解读 / 翻译 / 赏析 / 道德经 / 易经 / 阴符经 / 庄子 / 克制模式 | classics-reading | P1（克制型经典解读；无义理需求时跳过） |
| 立项 / Go-No-Go / 商业可行性 / MVP 实验 / 项目排序或终止 | project-decision-evaluation | P1 |
| 锁定计划 / 盘问 / grill me / 先别写代码 | plan-grill | P1（条件自动 + 显式；产出 PLAN.md 供 cross-model-review 接力） |
| 帮我优化提问 / 优化 prompt / 改写提问 / @prompt-optimizer | prompt-optimizer | P1（主动触发；委托 plan-grill 盘问 + historical-recall 召回，改写后回写闭环） |
| 对抗审查 / cross review / stress-test PLAN.md | cross-model-review | P1（接力 plan-grill；需 PLAN.md 存在） |
| 盲区 / 邻域 / 拓展 / 带走 | cognitive-reasoning (CE-001~013) | P2（回答后追加） |
| `/auto-review` / `使用 auto-code-review` / `启动跨模型代码审查` | auto-code-review | P1（仅用户显式触发） |
| 非平凡构建/修改/方案/迁移/审查/排障（动手前召回历史） | historical-recall | P1（全局门控；best-effort，不阻断主任务） |
| 非平凡 + ≥2 子结论 + 跨轮存活（边做边落盘中间结论） | checkpoint-persist | P1（全局门控；每产出一结论即落盘，防超窗丢失） |

`auto-code-review` 不因代码生成或修改完成自动加载。默认触发只授权只读审查；只有 `/auto-review --fix` 或明确“审查并修复”才授权主 agent 修改代码。

多全局技能同时命中时的块发射顺序与冲突裁决，见 `.agents/composition.md`。
