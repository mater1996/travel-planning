# Agent 编排入口

本目录定义“何时拆任务、谁拥有字段、任务按什么依赖顺序执行、什么状态才算完成”。只在主 Agent 需要创建或协调多个 assignment 时读取；单一研究任务以 assignment 的 `required_guides` 为准，不需要加载本目录。

## 文件路由

| 文件 | 解决的问题 | 何时读取 | 不读取的情况 |
| --- | --- | --- | --- |
| [task-domains.md](task-domains.md) | 任务域、字段所有权和统一结果包 | 决定拆成哪些任务，或出现字段冲突时 | 已有 assignment 且字段所有权明确 |
| [execution-waves.md](execution-waves.md) | 依赖、波次、餐厅三阶段和失效规则 | 多领域任务需要并行或排序时 | 单任务独立执行 |
| [completion-gates.md](completion-gates.md) | 各域最低完成门槛与停止条件 | 分配任务、验收结果或创建 gap task 时 | 只做路线候选，不做深度研究 |

## 触发编排

协作能力可用且存在两个以上独立研究域时使用编排。以下任一情况通常应拆任务：

- 多城市或超过 3 天；
- 超过 8 个候选景点；
- 同时涉及铁路、航班、大巴、租车、自驾或包车中的多个方式；
- 餐厅研究需要 discovery、路线评估和 ranking；
- 用户明确要求 Agent 派发。

路线尚未确认时只创建路线候选任务，不启动逐景点、逐门店、库存或完整交通边研究。

## 主 Agent 独占职责

主 Agent 独占城市顺序、路线采用、跨域冲突裁决、`planning-decisions.json`、最终 `itinerary.json` 和页面。研究 Agent 只提交 assignment 允许的实体、共享实体、事件绑定、约束、未解决项、来源与快照引用。

## 推荐读取顺序

1. 先用 `task-domains.md` 选择域并确定字段所有者。
2. 再用 `execution-waves.md` 建立依赖与波次。
3. 创建 assignment 时抄入对应的 completion checks。
4. 收到结果后只读取相关域在 `completion-gates.md` 的门槛，不扫描其他域。
