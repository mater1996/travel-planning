# 最终行程合同

## 何时读取

运行 assemble、编辑最终结构、增加新集合，或排查 audit 的 ID、引用和字段错误时读取。页面样式调整不需要本文件。

## 顶层结构

```json
{
  "trip": {},
  "workflow": {},
  "route_proposals": [],
  "planning": {
    "research_profile": {},
    "source_snapshots": [],
    "readiness": [],
    "attractions": [],
    "transport_edges": [],
    "daily_routes": [],
    "intercity_options": [],
    "vehicles": [],
    "road_trip_plans": [],
    "rental_options": [],
    "parking_locations": [],
    "lodging_options": [],
    "restaurants": [],
    "restaurant_snapshots": [],
    "meal_baseline_routes": [],
    "meal_route_evaluations": [],
    "meal_options": [],
    "weather": [],
    "booking_tasks": []
  },
  "days": [],
  "sources": [],
  "claims": []
}
```

`planning.*` 保存规范化研究集合与跨实体关系；`days[].events[]` 保存旅行者实际执行顺序。最终页面不能要求用户回到研究区自行拼接信息。

## 基础字段与引用

- 必填 `trip.title`、`days[]`、`day.date`、`event.id`、`event.time`、`event.type` 和 `event.title`。
- confirmed/final 阶段的事件 ID 全局稳定且唯一；时间使用目的地当地时间。
- 事件类型只允许 `attraction`、`transport`、`meal`、`lodging`、`rest` 或 `note`。
- 景点事件通过 `attraction_id`，交通通过 `route_id`，住宿通过 `lodging_id`，餐饮通过 `meal_id` 引用 planning 集合。
- `planning.research_profile` 供 audit 判断激活契约，属于内部控制信息，不在旅行者页面展示。

## 活动、提示与展示字段

- `note` 只表示某一时刻的提醒、背景或操作说明，不得带 `end_time` 占据持续时间窗。
- 没有具体安排的自由留白使用 `rest`；有明确地点、看点或动作的持续活动使用对应实体事件。
- 老街、古城、市场、步行街或串联两个以上命名地点的 Citywalk 使用 `attraction`，对应实体标记 `attraction_type=urban_walk`，并按城市漫游 profile 提供至少两个 checkpoints。
- 事件可展示正文只使用 `subtitle`、`details[]`、`tips[]` 和类型专属结构。禁止写 renderer 不读取的 `description`，避免数据存在但页面静默丢失。

## 景点与预约

- 景点实体分开保存实体地址、官网、公告、预约入口与核验时间；微信公众号预约另存公众号名、菜单路径与可选官方说明文章。
- 事件保存 `execution.entry`、`execution.exit` 与按序 `checkpoints[]`。入口投影到首节点，出口和最晚离开投影到末节点，不重复展示。
- checkpoint 至少有稳定 ID、顺序、起止时间、kind、名称、必达状态和动作；讲解、图片、移动、内部交通、途中餐饮、链接与失败备选按需增加。
- `urban_walk` 的每个 checkpoint 还必须有 `narration` 说明现场具体看点，并以 `instruction` 说明旅行者动作或去下一站的方向；首节点从入口开始，末节点覆盖退出与后续衔接。
- `reservation_required=true` 时引用 booking task；book now 或 book when open 必须有 HTTPS 操作入口。

## 交通、自驾与住宿

- 每条 `transport_edges[]` 记录出口到入口的门到门路线，不只保存地图耗时。
- 跨城事件可引用 `intercity_options[]`；动态候选必须闭合到 snapshot 与 offer。
- 激活 `transport.self_drive` 时必须有 `road_trip_plans[]`；激活 `transport.car_rental` 时还必须有 `rental_options[]`。地图 car route 不能代替车辆、驾驶、停车、补能和应急合同。
- 住宿候选保存实际入住夜、人数、房间、床型、报价状态、行李与下一站衔接；未验证多间库存时只称报价候选。

## 餐饮

- `restaurants[]` 保存稳定门店身份，`restaurant_snapshots[]` 保存本次动态覆盖。
- `meal_baseline_routes[]` 保存每餐唯一基准，`meal_route_evaluations[]` 保存逐候选两腿路线和额外绕行。
- `meal_options[]` 保存餐窗、候选集合、`selected_candidate_id`、`fallback_candidate_ids` 和切换条件。
- 时间轴事件的时间覆盖展示时间；只有研究餐窗本身改变时才改合同餐窗并重新核验快照。

## 每日路线

`planning.daily_routes[]` 每日期最多一条，含 `id`、`date`、`title`、`mode` 与执行顺序的 `stops[]`。完整旅行日覆盖住宿出发点、实际景点、主选正餐和结束点；每站有名称、GCJ-02 坐标，并尽量用 `event_id` 绑定事件。

首末站成为高德 `from`/`to`，中间最多 16 站按序成为 `via[n]`。不能只复制 transport 事件，也不能让移动端简化链接丢失途经点。

## 逐日空间连续性

- 每个 `day` 声明 `start_anchor` 与 `end_anchor`，均含名称、具体地址或定位说明和坐标。它们是详细时间轴的执行边界，不由页面猜测。
- 景点位置取采用实体的入口与出口；餐饮位置取主选餐厅；住宿取采用酒店；带持续时间的休息取事件 `location`。
- 相邻地点活动的前一出口与后一入口不相同，就必须在两者之间插入 `transport` 事件。交通事件的 route 起终点必须分别匹配两个活动锚点。
- 只有坐标与身份均指向同一现场时才可直接衔接；“很近”“同片区”或路线图上相邻不能替代步行交通节点。
- 交通实体至少含起终点名称与坐标、`distance_meters`、方式、门到门时长、地图链接、费用口径和失败备选。页面同时显示起终点、距离和时长。
- 住宿日的 `end_anchor` 必须是当晚住宿；最后一个异地活动后仍需独立返店交通事件。离境日则闭合到车站、机场或用户声明的终点。
- `planning.daily_routes[]` 是总览投影：所有地点活动必须由 stop 的 `event_id` 覆盖，但它不能替代详细时间轴中的交通事件。

## 费用与预算

- 事件 `cost_items[]` 区分基础门票、必选景交、可选体验、互斥套票、交通、住宿和餐饮。
- 每项保存单价、数量、小计、币种、按人或全体、required、status 和来源。
- 套票与同组单票不能同时计入基线。
- 页面预算从事件费用派生；保留聚合预算时注明生成时间与范围，不维护第二套真值。

字段级机器约束以 `schemas/`、assembler 与 audit 为准；完整成品形态只在排查 renderer 时读取 `assets/example-itinerary.json`。
