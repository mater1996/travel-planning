# 渐进读取架构

## 1. 设计原则

目标结构采用四层组合，而不是按业务名词平铺：

1. 运行时 `*.core` 模块定义所有同领域任务必须满足的公共规则；其人工入口统一命名为 `index.md`，同时承担目录路由。
2. `mode` 或 `type` 定义交通方式、景点类型等对象差异。
3. `scenario` 定义租车、儿童、无障碍、境外、极端天气等横切条件。
4. `contract` 定义结果模板、schema、提交和审查门槛。

同一任务可以组合多个 profile。租车是车辆取得方式，自驾是交通执行方式，两者不能合并成一个互斥枚举；租车自驾必须同时激活二者。

## 2. 目标目录

```text
skills/travel-planning/                    # 旅行规划主 Skill
├── SKILL.md                               # 总入口、边界、阶段和模块路由
├── references/                            # Agent 按需读取的研究规范
│   ├── index.md                           # 全部 reference 的总路由与阶段选择
│   ├── core/                              # 跨领域公共规则
│   │   ├── index.md                       # 通用规则路由与读取时机
│   │   ├── planning-pipeline.md           # 标准规划阶段与依赖顺序
│   │   ├── evidence-policy.md             # 来源等级、冲突和动态事实规则
│   │   └── readiness.md                   # 行前准备与分阶段复核
│   ├── orchestration/                     # 多 Agent 任务编排与验收
│   │   ├── index.md                       # 编排文档路由与触发条件
│   │   ├── task-domains.md                # 任务域、字段所有权和结果合同
│   │   ├── execution-waves.md             # 依赖波次、失效和修补规则
│   │   └── completion-gates.md            # 各任务域完成门槛与停止条件
│   ├── workspace/                         # 单次旅行工作区生命周期
│   │   ├── index.md                       # 工作区动作路由
│   │   ├── lifecycle.md                   # 初始化、路线确认和目录职责
│   │   ├── assignments.md                 # Assignment 创建与版本绑定
│   │   ├── submission-and-evidence.md     # 结果提交、快照和证据归档
│   │   └── merge-and-assembly.md          # 合并、计划、装配和审查
│   ├── attractions/                       # 景点研究模块
│   │   ├── index.md                       # 景点公共契约、类型路由与读取条件
│   │   ├── museum-venue.md                # 博物馆、展馆和室内场馆
│   │   ├── scenic-area.md                 # 大型景区、多入口和景交
│   │   ├── mountain-outdoor.md            # 山岳、徒步和户外风险
│   │   ├── theme-park.md                  # 主题乐园、排队和项目限制
│   │   └── performance-night.md           # 演出、夜游和固定场次
│   ├── transport/                         # 交通研究模块
│   │   ├── index.md                       # 交通公共契约、方式路由与读取条件
│   │   ├── flight.md                      # 航班、机场和行李规则
│   │   ├── rail.md                        # 高铁、铁路和车站衔接
│   │   ├── public-transit.md              # 公交、地铁和公共接驳
│   │   ├── self-drive.md                  # 自驾执行、停车和补能
│   │   ├── car-rental.md                  # 租车、保险和取还车
│   │   ├── charter-driver.md              # 包车司机、合同和费用边界
│   │   └── coach-ferry.md                 # 长途大巴、轮渡和船班
│   ├── dining/                            # 餐饮研究模块
│   │   ├── index.md                       # 餐饮公共契约、阶段路由与依赖顺序
│   │   ├── discovery.md                   # 门店发现与旅行价值判断
│   │   ├── operations.md                  # 营业、预约、排队和停车
│   │   ├── route-evaluation.md            # 基准路线和候选双腿路线
│   │   ├── ranking.md                     # 主选、备选和切换条件
│   │   └── constrained-scenarios.md       # 机场、景区、深夜等受限场景
│   ├── lodging/                           # 住宿研究模块
│   │   ├── index.md                       # 住宿公共契约与专项读取条件
│   │   └── inventory-and-occupancy.md     # 报价库存与入住容量核验
│   ├── tools/                             # 实时来源调用与标准化
│   │   ├── index.md                       # 工具文档路由与来源选择
│   │   ├── preflight.md                   # MCP 与上游真实健康检查
│   │   ├── provider-snapshots.md          # 供应商查询、快照和 offer 绑定
│   │   ├── maps-weather-community.md      # 地图、天气、小红书和境外地点
│   │   └── fallback-and-errors.md         # 手工入口、错误与降级规则
│   ├── output/                            # 行程装配和页面交付规范
│   │   ├── index.md                       # 计划、结构、页面和验收路由
│   │   ├── plan-contract.md               # Base、decisions 与摘要绑定
│   │   ├── itinerary-contract.md          # 最终行程集合、事件和引用
│   │   ├── evidence-and-actions.md        # 证据、动态状态和操作入口
│   │   ├── page-structure.md              # 页面信息层级和三种视图
│   │   ├── page-interactions.md           # 交互、地图、降级和打印
│   │   └── browser-acceptance.md          # 桌面、移动和交付验收
│   └── compat/                            # 一个迁移周期的旧名称指针
│       ├── index.md                       # 兼容范围和退场规则
│       ├── planning-pipeline.md           # 旧流水线入口迁移指针
│       ├── research-workflow.md           # 旧领域工作流迁移指针
│       ├── restaurant-research.md         # 旧餐厅研究入口迁移指针
│       ├── source-strategy.md              # 旧来源策略入口迁移指针
│       └── trip-readiness.md               # 旧行前检查入口迁移指针
├── registries/                            # 机器可读的模块注册信息
│   └── research-modules.json              # 模块触发、依赖和校验注册表
├── schemas/                               # 结构化数据 JSON Schema
├── assets/agent-templates/                # 各任务域的结果模板
└── scripts/                               # 创建、合并、审查和渲染脚本
```

`references/` 根目录只保留 `index.md`。`SKILL.md` 只保留触发范围、路线确认门槛、不可违反的边界、阶段入口和模块选择方式；编排、工作区、工具与输出都先进入各自 `index.md`，再读取当前动作对应文件。

## 3. 模块注册表

`registries/research-modules.json` 是渐进读取的机器入口。每个模块至少声明：

```json
{
  "id": "transport.self_drive",
  "kind": "profile",
  "domain": "transport",
  "depends_on": ["transport.core"],
  "guide": "references/transport/self-drive.md",
  "triggers": {
    "transport_modes": ["self_drive"]
  },
  "schema_refs": [
    "schemas/self-drive-plan.schema.json"
  ],
  "completion_checks": [
    "driver_eligibility",
    "driving_duration",
    "road_restrictions",
    "parking_coverage",
    "fuel_or_charging_plan"
  ]
}
```

注册表不保存某次旅行的数据，也不直接决定采用哪种交通方式。它只把已经确认的路线特征转换为所需规则和校验器。

阶段型流程通过注册表的 `stage_guides` 补充路由。例如 `restaurant_discovery` 自动加入 `dining/discovery.md` 与 `dining/operations.md`，`restaurant_ranking` 只加入 `dining/ranking.md`，避免每个餐饮任务读取整个目录。

## 4. 本次旅行的 Research Profile

路线确认后，主 Agent 根据 `brief.json` 和 `selected-route.json` 生成 `research-profile.json`。该文件属于本次 workspace，并进入任务 input revision。

示例：

```json
{
  "schema_version": "travel-research-profile/v1",
  "selected_route_id": "route-a",
  "modules": [
    "attractions.core",
    "attractions.mountain_outdoor",
    "transport.core",
    "transport.rail",
    "transport.self_drive",
    "transport.car_rental",
    "dining.core",
    "dining.driving_parking",
    "lodging.core"
  ],
  "reasons": {
    "transport.self_drive": "第 3 至第 5 日采用自驾",
    "transport.car_rental": "车辆在目的地机场取还",
    "attractions.mountain_outdoor": "采用山岳徒步景点"
  },
  "generated_at": "2026-09-22T12:00:00+08:00"
}
```

`reasons` 用于审查误激活或漏激活，不进入旅行者页面。

## 5. Assignment 扩展

任务 assignment 应新增以下字段：

```json
{
  "required_modules": [
    "transport.core",
    "transport.self_drive",
    "transport.car_rental"
  ],
  "required_guides": [
    "references/transport/index.md",
    "references/transport/self-drive.md",
    "references/transport/car-rental.md"
  ],
  "schema_refs": [
    "schemas/transport-edge.schema.json",
    "schemas/self-drive-plan.schema.json",
    "schemas/car-rental-option.schema.json"
  ],
  "completion_checks": [
    "door_to_door_route",
    "parking_coverage",
    "rental_pickup_return"
  ]
}
```

这些字段应由 assignment 生成器根据注册表计算，不允许调用方手写任意路径。模块 ID、依赖闭包、文件存在性和 schema 引用都应在创建任务时校验。

## 6. Agent 读取顺序

### 路线候选阶段

只读取：

1. `SKILL.md` 的路线确认门槛；
2. `core/planning-pipeline.md` 的路线阶段；
3. 路线前轻量社区预研规则；
4. 与路线比较直接相关的交通 profile 摘要。

此时不读取逐景点、逐门店和库存研究细则。

### 深度研究阶段

每个 Agent 严格按 assignment 读取：

1. workspace 的 `manifest.json`、`brief.json`、`route-context.json`、`selected-route.json` 和 `research-profile.json`；
2. assignment 声明的领域 `index.md`，它承载运行时 `*.core` 模块的公共契约和子文件路由；
3. `required_modules` 对应的 profile；
4. 依赖任务结果；
5. 结果模板和 schema。

不为当前任务读取 output renderer、其他领域 profile 或完整示例行程。

### 编排与交付阶段

主 Agent 读取合并状态、planning decisions 和输出 contract。只有修改 renderer 或排查页面问题时才读取页面实现细节与完整示例。

## 7. 激活与校验

模块的生命周期为：

```text
路线特征
  → profile 解析
  → 依赖闭包
  → assignment 固化
  → Agent 研究
  → submit 按 profile 校验
  → merge 保留 profile 来源
  → audit 检查跨领域约束
```

校验职责分为三层：

- `submit` 检查单任务字段完整性、证据绑定和 profile completion checks。
- `merge` 检查字段所有权、稳定 ID、冲突与 input revision。
- `audit` 检查跨领域可执行性，例如自驾停车点是否与景点入口一致、餐厅停车是否覆盖、租车还车时间是否早于航班缓冲。

## 8. 文档拆分与任务拆分边界

交通 reference 可以细分为多个 profile，但任务域不宜完全按方式拆散。建议的任务层级是：

- `transport-intercity`：同一城际边上的航班、铁路、大巴和自驾候选比较。
- `transport-local`：住宿、景点、餐厅之间的本地交通边。
- `road-trip`：车辆从取得到归还的连续生命周期，仅在自驾时创建。
- `meal-route-evaluation`：继续作为餐厅研究的独立依赖任务。

这样既能并行，又避免两个 Agent 分别推荐航班和高铁、却没有人负责同口径取舍。

## 9. 兼容策略

- 第一阶段保留旧 reference 文件作为入口，内容改为新模块索引和兼容说明。
- 旧 domain 名称在一个兼容周期内继续接受，并映射到新 domain/profile。
- 现有 `travel-research-result/v2` 不立即废弃；新增字段先可选，待所有生成器和测试迁移后再提升版本。
- 旧 workspace 没有 `research-profile.json` 时使用明确的 legacy profile，不能猜测为全模块启用。
- schema、模板和 assignment 版本必须一起升级，禁止只更新文档不更新 template digest。
