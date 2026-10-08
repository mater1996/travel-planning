# 合并、装配与交付

## 何时读取

所有任务完成后执行 status、merge、候选计划生成、主 Agent 决策复核、assemble、audit 或 render 时读取。

## 状态与合并

```bash
python3 skills/travel-planning/scripts/research_workspace.py status \
  --workspace ".travel-research/hangzhou-2026-10"

python3 skills/travel-planning/scripts/research_workspace.py merge \
  --workspace ".travel-research/hangzhou-2026-10"
```

merge 默认要求所有已分配任务达到可接受提交状态，并重新校验 assignment 身份、revision、结果契约、来源与快照绑定。它生成轻量 `travel-research-state/v2`：任务索引只保留摘要与结果路径，完整内容继续从 `results/<task_id>.json` 定向读取。

`global_state.shared_entities[]` 按 `entity_id` 去重，互补字段合并，来源、别名和标签取并集。字段冲突保留双方值、任务、时间和采用规则，不能静默丢失。

## 声明式计划

```bash
python3 skills/travel-planning/scripts/generate_itinerary_plan.py \
  --workspace ".travel-research/hangzhou-2026-10"
```

生成器读取 `state/research.json`、`selected-route.json`、`brief.json`、`route-proposals.json` 与任务结果，生成：

- `state/itinerary-plan.base.json`：确定性候选基础；
- `state/planning-decisions.json`：主 Agent 的小型采用与覆盖决策；
- `state/itinerary-plan.json`：二者物化后的装配输入。

主 Agent 不从空白手写完整计划，只在 decisions 中复核实体采用、事件顺序、覆盖、删除、补充和理由。确认后把 `workflow.plan_status` 改为 `reviewed` 并重新生成。

## 装配与摘要绑定

```bash
python3 skills/travel-planning/scripts/assemble_itinerary.py \
  --workspace ".travel-research/hangzhou-2026-10" \
  --print-research-sha256

python3 skills/travel-planning/scripts/assemble_itinerary.py \
  --workspace ".travel-research/hangzhou-2026-10"
```

`research_state_sha256` 绑定研究状态。merge 后摘要变化时，旧 decisions 与旧 plan 不能静默复用；必须重新生成并复核。装配器拒绝 `candidate` 状态、缺失实体、选定路线不一致、快照冲突与重复事件 ID。

## 审查与渲染

装配后运行 `audit_itinerary.py`。只有 `blocking=[]` 才渲染最终 HTML；失败时修补对应研究或 decisions 后重跑，不创建独立审查 Agent。输出合同见 [输出与交付入口](../output/index.md)。

主 Agent 默认只读取合并摘要；需要证据时按 `task_id`、`source_id` 或 `record_id` 定向读取。二进制资料先看元数据和摘要，再决定是否打开。
