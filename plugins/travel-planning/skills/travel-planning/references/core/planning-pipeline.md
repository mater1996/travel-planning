# 标准规划流水线

## 何时读取

新建多日或多城市行程、判断研究先后顺序、决定是否可以进入深度研究或交付阶段时读取。已有 assignment 的单一研究 Agent 不需要重新推演全部流水线。

## 阶段与出口条件

### 1. 需求边界

只收集会改变路线的出发地、目的地、日期、人数、预算、节奏、兴趣、住宿位置和硬限制。缺少低风险偏好时可以明确假设，日期、目的地或安全相关信息不清楚时不能猜。

出口：已能形成 2 至 3 个路线级方案。

### 2. 路线前轻量预研

在来源可用时做有上限的近期社区研究，只提取反复出现的玩法、时段、避坑和地方美食主题。此时不研究逐景点开放、逐餐厅营业或库存。

出口：获得能影响城市顺序、停留天数或片区选择的信号。

### 3. 路线候选与确认

比较城市顺序、停留、主要交通、预算、节奏、亮点和风险，并在候选中显式记录 `research_features`。正式采用老街、古城、市场、步行街或多节点 Citywalk 时，`attraction_types[]` 必须包含 `urban_walk`。等待用户选择、合并或调整；只有用户明确要求直接采用推荐路线时才跳过等待。

出口：存在唯一 `selected-route.json`，路线状态明确确认。

### 4. Profile 与数据源预检

`select-route` 生成 `research-profile.json`。对本次必需的地图、航班、铁路、住宿、天气或社区来源做真实 initialize/tools/list 与只读探测。

出口：激活模块可解释，必需来源可用或有明确 fallback。

### 5. 分域研究

先研究会决定空间时间骨架的景点、交通、住宿和天气。餐厅等待景点出口、住宿锚点、交通骨架与餐窗稳定后执行 discovery → route evaluation → ranking。

出口：所有 assignment 已 complete，或 partial/blocked 已由主 Agent明确接受。

### 6. 合并与规划决策

`research_workspace.py merge` 只合并实体、来源、快照和状态。生成器产出候选 plan，主 Agent只在 `planning-decisions.json` 中复核采用、顺序、覆盖、删除、补充和降级。

出口：`workflow.plan_status=reviewed`，研究摘要与 plan 绑定一致。

### 7. 装配、审查与交付

通用 assembler 生成 itinerary，audit 检查跨实体引用和可执行性，blocking 清空后再 render。研究或 renderer 变化后按风险执行单元、语法、浏览器与移动端验收。

出口：JSON、audit 与 HTML 一致，旅行者能按事件流执行。

## 禁止的跳跃

- 路线未确认前启动逐景点、逐餐厅或库存研究。
- 将数据源 capabilities 当作真实可用性。
- 研究 Agent直接写最终 `state/` 或页面。
- 为单次目的地创建专用 Python 装配脚本。
- audit 有 blocking 时仍渲染成“最终行程”。

需要实际创建、提交、合并或装配命令时，按当前动作进入[研究工作区入口](../workspace/index.md)；多任务域与波次进入[Agent 编排入口](../orchestration/index.md)。
