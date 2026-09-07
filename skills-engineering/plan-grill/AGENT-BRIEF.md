# plan-grill Agent 调用指南

## 一句话描述

对每个非平凡构建/修改/方案请求先做需求清晰度门控；仅在存在无法查明且会实质改变结果的阻塞性决策时自动逐问盘问。确认前不执行，产出 PLAN.md 供 cross-model-review 接力。

## 何时调用

- **条件自动**：非平凡请求仍存在无法从代码/上下文查明的阻塞性决策
- **用户强制触发**：用户说 `【盘问】` / "grill me" / "锁定计划" / "盘问我的方案"
- **接力 problem-analysis**：problem-analysis 完成后，问题已清晰，需要锁定实现方案

## 关键行为

1. 阅读 `SKILL.md` + `references/plan_grill.md` 全文。
2. 先执行需求清晰度门控（PG-000）；历史召回已由全局 `historical-recall` 负责，本 skill 不再内联召回（PG-006 仅声明委托）。
3. 一次一个问题（PG-001），每问给推荐答案 + 理由（PG-002）。
4. 能查代码回答的，直接查，不问用户（PG-003）。
5. PG-003 涉及跨文件/跨模块依赖分析且已加载平台 engineer 时，暂停盘问，委托快速架构分析并把 `architecture-analysis.md` 路径写回 PLAN.md（PG-005）。
6. 决策树解析完且用户确认后，在当前工作区根创建 `.plan-reviews/<plan-slug>/`，将七段填实的计划写入 `.plan-reviews/<plan-slug>/PLAN.md`（PG-004）。
7. 确认前不执行计划。

## 不调用的情况

- trivial 改动（typo、格式化、单点语法）
- 事实查询、解释、翻译、review 或只诊断不修复
- 验收标准与实施路径均已明确的纯执行任务
- 用户明确「直接做」「不要盘问」
- problem-analysis 未完成（问题本身未审查）
