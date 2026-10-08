# 装配计划合同

## 何时读取

研究 merge 后生成 `itinerary-plan.base.json`、编辑 `planning-decisions.json`、物化 `itinerary-plan.json`，或处理研究摘要失配时读取。

## 三层计划

- `state/itinerary-plan.base.json`：生成器根据研究状态确定性产生的候选基础。
- `state/planning-decisions.json`：主 Agent 的小型决策，只保存采用、顺序、覆盖、删除、补充、降级和理由。
- `state/itinerary-plan.json`：基础与决策物化后的装配输入。

主 Agent 不从空白手写完整计划，也不为一次旅行写 Python 装配脚本。业务时间、采用候选和降级策略属于数据，不属于代码。

## 摘要绑定

`research_state_sha256` 必须等于当前 `state/research.json` 的 SHA-256，并同时绑定 base 与 decisions。重新 merge 后：

1. 旧 plan 停止装配；
2. 重新生成 base；
3. 主 Agent 复核受影响的 decisions；
4. 再次物化 plan。

生成器不能静默沿用绑定旧摘要的 decisions。

## Collections

`collections` 声明目标集合来自哪个任务结果或 workspace 文件、对象路径和选用 ID。装配器负责来源、快照、字段归一化与引用绑定；decisions 只决定选什么，不复制完整研究对象。

## Workflow 状态

- 自动生成的计划使用 `workflow.plan_status=candidate`。
- 主 Agent 完成逐日顺序、硬时间、主备、覆盖与降级复核后改为 `reviewed`。
- 装配器拒绝 candidate。没有 `plan_status` 的历史手工计划只作兼容，不成为新流程模板。
- `workflow.phase` 使用 `proposal`、`awaiting_confirmation`、`confirmed_planning` 或 `final`。路线未确认时不能生成 final 日程。

## 主 Agent 复核清单

- 选定实体与确认路线一致；
- 硬时间、停止入场、交通缓冲、餐窗与住宿衔接可行；
- `route_worthy` 餐厅引起的路线调整已决策；
- 主选、备选、删除与补充都有理由；
- 老街、古城、市场、步行街或多节点 Citywalk 已建模为 `urban_walk` 景点事件，包含具体 checkpoints，而不是带结束时间的 `note`；
- 所有事件只使用 renderer 支持的 `subtitle`、`details[]`、`tips[]` 和类型专属字段，没有 `description`；
- 每天已声明可定位起点和终点；所有地点活动按顺序闭合，相邻地点变化之间有独立 transport 事件；
- 主选餐厅的进店、离店路线已从候选评估投影到事件流，住宿日最后一段明确回到住宿；
- 每日路线图的 stops 通过 `event_id` 覆盖所有地点活动，但没有被当作交通事件的替代品；
- 预算、天气与页面摘要从唯一事实源派生；
- 仍有 blocking unresolved 时不标记 reviewed。
