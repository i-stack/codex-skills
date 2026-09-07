# checkpoint-persist 范围外

本 skill 负责**过程中间结论的增量落盘**（把「结论 + 决策 + 未决」写入 `.plan-reviews/checkpoint/`，防止超窗丢失），不负责回答内容本身，也不负责计划锁定、审查或历史召回。

## 不处理的内容

- **回答的主体内容**：本 skill 只在后台落盘中间结论，不参与主体回答的生成。
- **历史召回（historical-recall）**：动手前召回历史线索由 historical-recall 负责（读）；本 skill 只负责动手后落盘（写）。两者独立触发。
- **计划锁定（plan-grill）**：是否进入盘问、盘问如何收敛、PLAN.md 如何写由 plan-grill 负责；本 skill 只在其多决策点分析过程中增量保护中间结论，不替代 PLAN.md 成品。
- **代码审查（auto-code-review / cross-model-review）**：审查执行、reviewer 仲裁、归档结构由对应 skill 负责；本 skill 只在长审查中保护中间结论，不负责归档到 `.plan-reviews/`。
- **成品知识库写入**：本 skill 只写入 `.plan-reviews/checkpoint/`（进行中工作区，以 `kind=checkpoint` 进入索引），**不写** `.plan-reviews/` 下的成品 plan 目录，也不执行 `sync` / `merge`；checkpoint 中间态不参与 `merge` 新陈代谢合并。
- **对话全量快照**：本 skill 只落「结论」，不落「用户提问 + AI 思考 + 逐字回复」的对话流；对话级快照属宿主侧能力，不在本 skill 范围。

## 触发门控

仅在非平凡任务 + ≥2 子结论 + 跨轮存活三条全满足时触发。trivial 任务、单轮任务、单点子结论、事实查询 / 翻译 / 闲聊跳过。门控绑定任务形态，不绑定是否盘问。
