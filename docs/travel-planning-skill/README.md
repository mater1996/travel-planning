# 旅行规划 Skill 模块化设计

本文档集定义 `travel-planning` Skill 的目标结构、领域研究规则和迁移计划。它服务于 Skill 维护与实现，不是旅行者行程页面，也不替代当前运行时契约。

## 文档状态

- 当前实现基线：以 `plugins/travel-planning/skills/travel-planning/` 下的 Skill、references、schemas、scripts 和 tests 为准。
- 已完成第二批文档闭环：`references/` 根目录只保留 `index.md`，编排、工作区、实时工具与输出契约分别进入独立目录，旧大文件不再作为权威入口。
- 每个 reference 领域现在使用 `index.md` 作为人工入口，列出关联文件、使用时机、依赖顺序和不应读取的场景；运行时公共模块仍保留 `*.core` ID，两者职责分开。
- 餐饮 stage guide 已进入机器注册表，assignment 会按 discovery、route evaluation、ranking 自动下发对应文档，而不是依赖 Agent 自行猜测。
- 自驾与租车已进入 submit、计划生成、装配和 audit；仅有地图 `mode=car` 不能替代 road-trip 契约。
- 景点类型和餐饮场景 profile 已可被解析并下发 guide/check 名称，但阶段 5、6 的全部专用字段强校验仍是后续实施项。
- 旧 `route-data`、`stay-food` 在兼容期继续可用；旧 reference 名称仅在 `references/compat/` 保存短迁移指针，新任务不得把兼容文件写入 `required_guides`。
- 实施原则：先保持现有输出兼容，再逐步引入机器可读路由和按 profile 校验，不能通过搬文件暗中改变旅行研究语义。

## 文档导航

- 架构设计
  - [渐进读取架构](architecture/progressive-reading.md)：目标目录、模块模型、激活规则、assignment 契约和读取顺序。
  - [领域研究分类](architecture/domain-research.md)：交通、景点、餐饮、住宿及横切场景分别需要研究什么。
- 实施计划
  - [模块化迁移计划](plans/modularization-migration.md)：从当前结构迁移到目标结构的阶段、文件映射、测试和完成门槛。

## 目标

目标是在保持一个主 `travel-planning` Skill 的前提下，让 Agent 只读取当前阶段和当前任务真正需要的材料，并让这些读取要求进入 assignment 和验证流程，而不是依赖 Agent 自行判断。

目标读取链为：

```text
主 Skill 边界
  → 当前规划阶段
  → 当前任务领域 index（承载运行时 core 契约和子文件路由）
  → 被本次行程激活的 mode/type/scenario profiles
  → 结果模板与 schema
  → 对应 completion checks
```

例如，租车自驾进入山岳景区时，交通任务读取 `transport.core`、`transport.self_drive`、`transport.car_rental`，景点任务读取 `attractions.core`、`attractions.mountain_outdoor`。普通城市地铁行程不会加载租车、补能、山路或异地还车规则。

## 核心判断

### 保留一个主 Skill

航班、高铁、自驾、租车、景点和餐厅仍属于一次完整行程的共同决策图。它们共享路线确认、证据分级、workspace、稳定 ID、合并、审查和页面交付规则，不应拆成互相独立、容易产生冲突的顶层规划 Skills。

高德、飞猪、飞常准和小红书继续作为工具型 Skills。主 Skill 负责判断什么时候使用它们、如何解释结果、怎样写入本次旅行的结构化状态。

### 文档模块与 Agent 任务不是一回事

文档可以按交通方式和景点类型细分，以便按需读取；Agent 任务只在字段所有权、依赖关系或可并行性确实不同的时候拆分。不能因为有十个 reference，就机械创建十个 Agent。

### Profile 必须可验证

只有拆分 Markdown 文件但不改变 assignment 和 submit/audit 校验，渐进读取仍然只是约定。目标结构要求每个被激活的 profile 同时声明：

- 触发条件和依赖模块；
- 必读 reference；
- 可写实体和 schema；
- 完成门槛；
- 失败与降级状态；
- 动态事实的复核时点。

## 原结构的主要缺口与当前处理

- 根级 `research-workflow.md` 已移除，兼容指针位于 `references/compat/`；领域规则位于 `references/attractions/`、`transport/`、`dining/` 和 `lodging/`。
- 原 `agent-orchestration.md`、`research-workspace.md`、`live-data-tools.md`、`itinerary-schema.md` 与 `interactive-page.md` 已拆为目录入口和动作级文件，Agent 不再为一个局部问题加载整份大文档。
- `route-data` 已增加 `transport-intercity`、`transport-local` 和 `road-trip` 细分入口，旧名称暂不删除。
- `stay-food` 已增加 `lodging` 与 `meal-windows` 替代入口，旧名称暂不删除。
- assignment 已由注册表生成 `required_modules`、`required_guides`、`schema_refs` 和 `completion_checks`，并把 profile 和 guides 纳入输入版本摘要。
- 尚待补齐的是景点类型、餐饮横切场景的完整字段级 validator，以及旧 domain 的最终退场迁移。

## 本轮非目标

- 不为了目录整齐改变现有行程 JSON 的事实语义。
- 不把实时查询结果、平台报价或社区体验升级为已确认库存和官方事实。
- 不为每个细小场景创建永久模块；只有出现独立触发条件、字段或审查门槛时才新增 profile。
