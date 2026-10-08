# 任务域与字段所有权

## 何时读取

创建 assignment、拆分大任务、判断谁能写某字段，或 merge 报告字段冲突时读取。

## 任务域

| 任务域 | 独占产出 | 可引用但不可改写 |
| --- | --- | --- |
| `attractions` | 景点身份、官方入口、适用日期运营、入口出口、checkpoints、景点费用与预约草案 | 路线日期、人群约束 |
| `transport-intercity` | 同一城际边的航班、铁路、大巴或公路候选、快照引用与门到门比较 | 城市顺序、住宿日期、硬时间 |
| `transport-local` | 住宿、景点、餐厅之间的本地交通边与路线锚点 | 景点入口出口、住宿与餐饮锚点 |
| `road-trip` | 车辆、驾驶、租车、停车、补能、道路限制与应急生命周期 | 已采用停靠点、日期与交通边 |
| `lodging` | 住宿候选、快照引用、入住、退房与行李补丁 | 每日片区、交通窗口 |
| `meal-windows` | 午晚餐窗、前后锚点、预算、绕行与饮食约束 | 初始事件骨架 |
| `restaurant-research` | discovery 候选与社区价值判断、路线影响、动态快照；ranking 的最终 `meal_options[]` | 餐窗、锚点与路线评估 |
| `weather-risk` | 天气对象、固定图标、事件或路线影响与天气备选 | 景点、交通与 checkpoint ID |
| `readiness` | 节假日、公告、行李、入境、通信、保险与分阶段复核 | 已选交通与住宿夜 |

迁移期间可读取旧的 `route-data` 与 `stay-food` 结果，但新 workspace 使用细分域；兼容域不新增字段所有权。

## 统一结果包

结果必须从 assignment 指定的模板复制，保留 `schema_version`、`template_version`、`template_digest`、`input_revision` 和 `task_id`。允许的核心字段为：

- `summary`：不超过 200 字，只写结论和阻塞项，不直接进入页面；
- `source_snapshot_ids[]`：本任务落盘的标准快照；
- `entities`：本域拥有的规范化实体；
- `shared_entities[]`：其他任务、排程、审查或页面确实需要读取的实体；
- `event_bindings[]`：带稳定 ID、目标、操作、快照和来源的事件补丁；
- `constraints[]`：目标、规则和严重度明确的硬约束；
- `unresolved[]`：字段、原因、下一动作、复核时间、入口和严重度；
- `source_ids[]`：已归档来源。

`event_bindings[].operation` 只允许 `merge`、`append_reference` 或 `invalidate`。交通、住宿等库存候选用 `inventory_refs[]` 绑定 `snapshot_id`、`offer_id` 和 `role`。存在 blocking unresolved 时不能提交 `complete`；存在 quote 快照却没有投影候选时提交应失败。

## Shared entity 规则

- 只有跨任务消费的稳定身份、地址、坐标、POI、站点或关联键进入 `shared_entities[]`。
- 排队、价格、库存、营业、评分等动态字段留在任务实体和快照中。
- merge 按 `entity_id` 合并互补字段；冲突字段保留双方值、任务与处理记录，再采用较新的有效提交。
- 子 Agent 不直接修改 `state/research.json`，也不把整份研究报告放入 shared state。
