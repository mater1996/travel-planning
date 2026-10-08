---
name: travel-planning
description: 调研和规划需要可靠动态信息的旅行，比较路线与交通，生成可执行的逐日行程、结构化 JSON 和响应式 HTML。适用于多日或多城市行程、详细路线研究及可分享页面；不用于代订、付款或修改订单。
---

# 旅行规划

将旅行需求转化为可执行的逐日事件流，并交付可独立打开的响应式 HTML 页面和对应 JSON。

## 路线确认门槛

1. 只收集会显著改变方案的出发地、目的地、日期或天数、人数、预算、节奏、兴趣、住宿位置和硬性限制。日期、目的地或无障碍安全风险之外的缺失信息可用明确的低风险假设补齐。
2. 小红书已配置且可用时，路线候选前执行一次有上限的目的地轻量预研，只提取近期反复出现的玩法、时段、避坑和地方美食主题。来源不可用时记录原因并继续。
3. 深度调研前给出 2 至 3 个路线方案，说明城市顺序、停留、主要交通、预算、节奏、亮点和风险。
4. 等待用户选择、合并或调整。只有用户明确要求直接采用推荐路线时才跳过等待。
5. 路线确认前不虚构班次、余票、库存或实时价格，不启动逐景点、逐门店研究。

路线候选阶段只读取[标准规划流水线](references/core/planning-pipeline.md)的路线阶段和[地图、天气与社区研究](references/tools/maps-weather-community.md)的小红书轻量预研部分。

## 渐进读取

路线确认后，`research_workspace.py select-route` 生成本次 `research-profile.json`。Assignment 根据 `registries/research-modules.json` 自动固化 `required_modules`、`required_guides`、`schema_refs` 和 `completion_checks`。

需要人工判断文档入口时先看[参考资料总入口](references/index.md)。每个领域用 `index.md` 说明目录内所有关联文件、读取条件和依赖顺序；运行时模块 ID 仍使用 `*.core`，它表示领域公共契约，不表示文件名必须叫 `core.md`。

Agent 按以下顺序读取，不遍历无关 reference：

1. assignment 的 `read_first`；
2. `required_guides` 中的领域基础模块；
3. 本次激活的方式、类型和场景 profile；
4. 依赖任务结果、结果模板和 `schema_refs`。

| 当前任务 | 必读入口 |
| --- | --- |
| 景点身份、运营、入口出口和内部顺序 | [景点研究入口](references/attractions/index.md)，再读 assignment 激活的景点类型 profile |
| 老街、古城、市场、街区串游或 Citywalk | [城市漫游](references/attractions/urban-walk.md)；路线的 `research_features.attraction_types[]` 必须包含 `urban_walk` |
| 城际或本地交通 | [交通研究入口](references/transport/index.md)，再读 flight、rail、public-transit、self-drive、charter 等已激活 profile |
| 租车自驾 | 同时读取 [自驾](references/transport/self-drive.md)与[租车](references/transport/car-rental.md)；租车是车辆取得，自驾是执行方式 |
| 正餐研究 | [餐饮研究入口](references/dining/index.md)，再按 discovery、operations、route-evaluation、ranking 阶段读取对应文件 |
| 住宿 | [住宿研究入口](references/lodging/index.md)；动态报价和多间容量再读 inventory-and-occupancy |
| 来源冲突和动态事实 | [证据与动态事实](references/core/evidence-policy.md) |
| workspace、任务提交和合并 | [研究工作区入口](references/workspace/index.md)，只读当前动作对应文件 |
| 行前与横切风险 | [行前就绪](references/core/readiness.md) |
| 多 Agent 拆分、波次或验收 | [Agent 编排入口](references/orchestration/index.md) |
| 最终装配和数据结构 | [输出与交付入口](references/output/index.md)，先读 plan contract，再按需读 itinerary contract |
| 页面渲染或页面问题 | [输出与交付入口](references/output/index.md)，只读 structure、interactions 或 browser acceptance 中相关文件 |

查询航班、铁路、住宿、地图、天气或小红书时先读[实时数据工具入口](references/tools/index.md)，再只读取对应 provider 或 fallback 文件。飞猪通用发现使用 `$flyai`，中国境内地点与路线使用 `$amap-maps`，航班运行、价格、铁路和空铁联运使用 `$variflight`，小红书体验研究使用 `$xiaohongshu`。

## 深度研究

路线确认后先运行真实数据源预检，并为本次必需来源传入 `--require`：

```bash
python3 skills/travel-planning/scripts/research_sources.py preflight \
  --city "<首个目的地>" \
  --require <source>
```

预检必须完成 MCP `initialize`、`tools/list`、只读上游探测、天气请求及适用的小红书运行态检查；静态 capabilities 不能代替。必需来源失败时先修复或声明合法 fallback。

复杂行程按[Agent 编排入口](references/orchestration/index.md)分波次执行。子 Agent 只提交 assignment 允许的实体、快照引用、事件绑定、约束、未解决项和来源；主 Agent 独占城市顺序、采用决策、冲突裁决、最终 JSON 和页面。

老街、古城、市场和连续街区不是一句“慢走”即可交付的自由文本。只要它占用一个游览时间窗或串联两个以上命名地点，就按 `urban_walk` 景点研究，落为 `attraction` 事件并给出入口、出口、按序 checkpoints、每站看什么或做什么、站间移动、可跳过项和退出条件。若无法研究出这些内容，应缩短为无结束时间的提示或明确的自由休息，不得用 `note` 填满大段时间。

逐日事件流必须空间闭合。每天声明可定位的 `start_anchor` 与 `end_anchor`；每个有地点的活动都要能从前一活动抵达。前一活动出口与后一活动入口不是同一坐标时，两者之间必须有独立 `transport` 事件，包含准确起终点、距离、方式、门到门时间、地图链接和备选。餐厅候选的 `from_previous` / `to_next` 与顶部每日路线图只是研究和总览，不能代替时间轴中的交通事件；住宿日最后一个活动后必须明确回到住宿。

餐厅研究保持 discovery → route evaluation → ranking 三阶段。值得专程前往的门店先由主 Agent 判断是否重排活动或改变交通，再计算最终双腿路线。

自驾不能只提供高德 `car` 路线。`road-trip` 任务必须覆盖车辆、驾驶员、道路限制、驾驶时长、停车、补能和应急；租车时再覆盖取还车、证件、押金、保险、里程和油电政策。

## 不可违反的边界

- 开放、价格、库存、班次、天气、签证和交通规则等动态事实必须记录查询时间、来源和适用日期，并区分官方事实、平台快照、社区体验与估算。
- 景区官网、运营方或政府确认开放、价格、入口和安全；社区内容不能单独证明这些事实。
- 飞猪、飞常准等完整结果先转换为 `travel-source-snapshot/v1`；采用候选通过 `snapshot_id + offer_id` 绑定，不把供应商私有字段写入行程层。
- 中国铁路最终回到 12306；酒店未核验多间同房型库存时只称报价候选。
- 登录、验证码、设备验证或风控出现时停止该来源，由用户本人处理。
- 不输出或归档凭证、Cookie、二维码、授权头和临时令牌。
- 未经用户确认具体项目、日期、数量、价格及乘客或入住人，不下单、占座、付款、发送消息或修改预订。
- 不虚构预订结果、实时价格、库存、开放状态或来源；所有估算明确标记。

## 合并、审查与交付

任务完成后先 `merge`，再生成候选计划。主 Agent 只在 `planning-decisions.json` 中复核实体采用、事件顺序、覆盖、删除、补充和降级策略；确认后将 `workflow.plan_status` 设为 `reviewed`。

```bash
python3 skills/travel-planning/scripts/generate_itinerary_plan.py --workspace ".travel-research/<trip-id>"
python3 skills/travel-planning/scripts/assemble_itinerary.py --workspace ".travel-research/<trip-id>"
python3 skills/travel-planning/scripts/audit_itinerary.py ".travel-research/<trip-id>/artifacts/itinerary.json" --output ".travel-research/<trip-id>/artifacts/audit.json"
python3 skills/travel-planning/scripts/render_itinerary.py ".travel-research/<trip-id>/artifacts/itinerary.json" ".travel-research/<trip-id>/artifacts/itinerary.html"
```

只有 `blocking=[]` 才渲染。普通行程沿用已验收 renderer；只有 renderer、前端资源、可见 DOM/交互发生变化，或用户报告页面问题时才执行完整浏览器验收。仅调整研究说明、输出合同、schema 或 audit 而没有改变实际页面输出时，不做浏览器验收。

最终页面只保留会改变旅行者时间、地点、动作、费用或备选的信息，优先回答几点到、从哪里进、按什么顺序、最晚何时离开、何时预约、花多少钱、下一段怎么走以及失败时如何调整。
