# 旅行规划 Skill 修改规划

## 实施状态（2026-09-22）

本轮已完成第二批渐进披露重构，并把旧入口集中到兼容目录：

- 已完成阶段 0 的基线验证；实施前全量测试为 189 项通过。
- 已完成阶段 1 的两轮目录拆分与主 `SKILL.md` 路由化；`references/` 根目录只保留总 `index.md`。
- 编排、workspace、实时工具与 output 已按“当前动作”继续拆分，每个目录入口列出全部关联文件、读取时机和不读取场景。
- 旧规划流水线、研究工作流、餐厅研究、来源策略和行前检查只在 `references/compat/` 保留短迁移指针，不再承载规范正文。
- 已完成阶段 2、3 的模块注册表、profile resolver、assignment 固化及输入摘要绑定。
- 已完成阶段 4 的首批 `self_drive`、`car_rental`、`rail` 接入；road-trip 实体可进入生成、装配与跨实体 audit。
- 已建立阶段 5、6 的 reference 与模块激活入口；专用字段级阻断校验仍待后续批次完成。
- 已建立阶段 7 的新 domain、模板和旧名称兼容映射；旧 domain 尚未删除。

因此，本文件后文仍保留完整长期计划；“首个实施批次”是已执行状态，阶段 5、6 和兼容层清理是下一批工作，不应被误读为已经全部完成。

## 1. 范围与原则

本规划把当前以大篇 reference 和少量固定 domain 为主的结构，迁移为“主 Skill 路由、领域 index、运行时 core 模块、可组合 profiles、机器注册表、assignment 固化、按 profile 校验”的结构。`index.md` 是人工阅读入口，`*.core` 是机器模块 ID，二者不再共用 `core.md` 这一含混文件名。

实施时遵循：

- 先建立等价结构，再增加新能力；
- 每个阶段都能独立验证和回退；
- 不破坏现有 workspace 和成品行程读取；
- 文档、模板、schema、脚本和测试同步修改；
- 当前工作区已有未提交修改，实施时必须按文件逐项核对，不能覆盖或重置。

## 2. 当前文件到目标模块的映射

| 当前文件或区域 | 目标位置 | 处理方式 |
| --- | --- | --- |
| `SKILL.md` | `SKILL.md` | 缩短为边界、阶段入口和模块路由，不保留领域长清单 |
| `planning-pipeline.md` | `references/core/planning-pipeline.md`、`orchestration/`、`workspace/` | 阶段、编排和命令分开读取；旧名只留兼容指针 |
| `source-strategy.md` | `references/core/evidence-policy.md` 与 `tools/` | 证据判断和工具失败分开；旧名只留兼容指针 |
| `research-workspace.md` | `references/workspace/*.md` | 生命周期、assignment、提交和装配按动作拆分 |
| `agent-orchestration.md` | `references/orchestration/*.md` | 任务域、波次与完成门槛分开读取 |
| `trip-readiness.md` | `references/core/readiness.md` 加各 scenario profile | 公共复核保留，方式专项内容移到对应 profile |
| `research-workflow.md` 景点部分 | `references/attractions/index.md` | 作为领域公共契约和子文件路由，再增加类型 profiles |
| `research-workflow.md` 交通部分 | `references/transport/index.md` | 作为领域公共契约和方式路由，方式细节分流 |
| `restaurant-research.md` | `references/dining/*.md` | 保留三阶段依赖，按 discovery/operations/route/ranking 拆文档 |
| `live-data-tools.md` | `references/tools/*.md` 与各工具 Skill | 预检、供应商快照、地图社区、fallback 分开读取 |
| `itinerary-schema.md` | `references/output/plan-contract.md`、`itinerary-contract.md`、`evidence-and-actions.md` | 计划、最终结构和证据操作分开 |
| `interactive-page.md` | `references/output/page-structure.md`、`page-interactions.md`、`browser-acceptance.md` | 内容结构、交互和浏览器验收分开 |
| `route-data.json` 模板 | 交通基础模板及 profile 扩展 | 先兼容，后按字段所有权拆分 |
| `stay-food.json` 模板 | `lodging` 与 `meal-windows` | 移除住宿 Agent 对最终餐厅方案的所有权 |

## 3. 实施阶段

### 阶段 0：冻结基线

目标：在重构前记录当前可用契约和未提交状态。

任务：

1. 保存当前 `git status --short` 和相关文件 diff 清单。
2. 运行现有旅行规划测试，记录总数、通过数和已知失败。
3. 选择三个兼容样本：城市公共交通、航班加高铁、多日包车或自驾候选。
4. 保存样本的 assignment、merge state、itinerary、audit 摘要和渲染关键字段。

完成门槛：有可重复的基线命令和结果；所有后续阶段都能判断是结构变化还是语义回归。

### 阶段 1：文档等价拆分

目标：只重组 reference，不改变 schema 和运行结果。

任务：

1. 创建 `references/core`、`attractions`、`transport`、`dining`、`lodging`、`output`。
2. 将现有规则迁移到领域 `index.md` 和餐厅阶段文档；每个 index 说明全部关联文件及读取时机。
3. 旧 reference 暂时保留为兼容入口，指向新位置并说明废弃计划。
4. 更新 `SKILL.md` 的路由表，确保任何旧场景都能找到等价规则。
5. 增加文档链接检查和“主 Skill 不重复领域细节”测试。

完成门槛：现有测试结果不变；所有相对链接可解析；新旧入口的规范内容没有冲突。

### 阶段 2：模块注册表与 Profile 解析

目标：让渐进读取从文字约定变成机器可计算结果。

任务：

1. 新增 `registries/research-modules.json` 及其 JSON Schema。
2. 定义 module ID、kind、domain、depends_on、guide、triggers、schema refs 和 completion checks。
3. 新增 profile resolver，根据 brief 和 selected route 生成 `research-profile.json`。
4. 校验未知模块、循环依赖、缺失 guide、错误 schema 路径和无法解释的激活。
5. 将 research profile 纳入 workspace manifest 和 input revision。

首批模块只覆盖：

- `attractions.core`
- `transport.core`
- `transport.flight`
- `transport.rail`
- `transport.self_drive`
- `transport.car_rental`
- `transport.charter_driver`
- `dining.core`
- `lodging.core`

完成门槛：给定同一 brief 与 selected route，profile 结果确定且排序稳定；自有车、租车自驾和包车能得到不同模块集合。

### 阶段 3：Assignment 固化渐进读取

目标：每个 Agent 明确知道必须读什么、产出什么和如何验收。

任务：

1. 扩展 assignment，增加 `required_modules`、`required_guides`、`schema_refs` 和 `completion_checks`。
2. 由注册表自动生成这些字段，禁止任意路径注入。
3. 把 required guides 和 research profile 加入 revision digest。
4. submit 时校验任务实际 domain 是否允许使用这些模块。
5. assignment 状态输出中展示激活原因，便于主 Agent 发现误判。

兼容规则：旧 workspace 没有 profile 时显式使用 `legacy.default`；不能默认为加载全部模块。

完成门槛：修改 guide、profile 或依赖结果会使旧任务失效；无关 profile 的变化不会使任务失效。

### 阶段 4：交通 Profile 与 Road-trip 契约

目标：补齐自驾与租车，同时让航班、铁路和包车有独立完成门槛。

任务：

1. 增加 transport edge 基础 schema。
2. 增加 flight、rail、self-drive、car-rental、charter-driver schemas 或受控子结构。
3. 增加车辆、驾驶员、取还车、停车、补能和费用结构。
4. 把 `trip-readiness.md` 中的方式专项规则迁入对应 profile。
5. 扩展 source snapshot 产品类型和 inventory ref 角色时，保持供应商私有字段隔离。
6. 在 submit 中实现单任务 completion checks。
7. 在 audit 中实现跨实体检查。

自驾首批阻断检查：

- 每个主要停靠点有停车或明确不可停车后的替代接驳；
- 连续驾驶时长、休息和夜驾风险有处理；
- 油车有加油方案，新能源车有充电与失败备选；
- 限行、景区车辆管制和道路关闭有适用日期来源或复核任务；
- 租车时取还车时间与航班、铁路和住宿事件不冲突；
- 租金、保险、押金、油电、路桥、停车和异地还车的预算口径不重复。

完成门槛：`map_route.mode=car` 不能单独通过自驾审查；租车自驾、开自有车和包车司机三种样本都能正确通过或阻断。

### 阶段 5：景点类型 Profiles

目标：避免所有景点共用一套最小字段，提升复杂景区的可执行性。

任务：

1. 先实现 `museum_venue`、`scenic_area` 和 `mountain_outdoor`。
2. 根据景点标签、官方描述和采用活动激活 profile，由主 Agent复核。
3. 增加类型专用完成门槛，例如闭馆日、索道与最晚下撤。
4. checkpoint schema 支持 profile 所需的内部交通、体力和天气失败分支。
5. 再按真实需求增加 theme park、performance/night 和 neighborhood walk。

完成门槛：普通城市景点不被要求填写山岳字段；山岳景区缺少最晚下撤或恶劣天气备选时不能进入最终规划。

### 阶段 6：餐饮文档模块化与场景 Profiles

目标：保留现有成熟三阶段流程，同时降低每个 Agent 的无关阅读量。

任务：

1. 将现有餐厅规则拆为 core、discovery、operations、route evaluation、ranking。
2. 保持三个 stage、候选集合一致性和现有 validator 语义不变。
3. 新增 driving/parking、dietary/allergy、large group 和 constrained venue profiles。
4. completion checks 只在相应场景激活。
5. 确保旅行者页面继续隐藏内部评分和研究过程。

完成门槛：现有餐厅相关测试和浏览器交互全部通过；自驾餐窗缺少停车执行信息时能被准确指出，而公共交通餐窗不受影响。

### 阶段 7：拆分任务域与清理兼容层

目标：字段所有权与文档领域一致，移除不自然的 `route-data` 和 `stay-food` 聚合。

任务：

1. 将 `route-data` 迁移为 `transport-intercity`、`transport-local`，自驾时增加 `road-trip`。
2. 将 `stay-food` 迁移为 `lodging`；餐窗由 `meal-windows` 或主 Agent 生成。
3. 保留 `meal-route-evaluation` 的明确依赖关系。
4. 更新 domain templates、shared entity types、inventory products 和 ownership checks。
5. 提供旧 domain 到新 domain 的一个版本兼容映射。
6. 所有活跃样本和文档迁移后删除旧入口。

完成门槛：没有任务同时拥有住宿实体与最终餐厅方案；没有单一 transport task 同时无条件承担库存、所有本地边和餐厅路线。

## 4. 代码修改清单

预计涉及：

- `skills/travel-planning/SKILL.md`
- `skills/travel-planning/references/**`
- `skills/travel-planning/registries/research-modules.json`
- `skills/travel-planning/schemas/**`
- `skills/travel-planning/assets/agent-templates/**`
- `skills/travel-planning/scripts/research_workspace.py`
- `skills/travel-planning/scripts/generate_itinerary_plan.py`
- `skills/travel-planning/scripts/assemble_itinerary.py`
- `skills/travel-planning/scripts/audit_itinerary.py`
- `skills/travel-planning/scripts/render_itinerary.py`，仅当新增旅行者展示字段时修改
- `plugins/travel-planning/tests/**`

不应在此重构中改动 provider 凭证、自动预订边界或插件身份。

## 5. 测试规划

### 单元测试

- module registry schema、唯一 ID、依赖闭包和循环检测；
- route features 到 profiles 的确定性映射；
- assignment required guides 和 revision digest；
- 每个 profile 的 submit completion checks；
- legacy workspace 兼容；
- domain ownership 和 snapshot 产品限制。

### 契约测试

- 自有车只激活 self-drive；
- 租车自驾同时激活 self-drive 与 car-rental；
- 包车司机只激活 charter-driver；
- 高铁加本地地铁只激活 rail 与 public-transit；
- 山岳景区激活 mountain-outdoor，普通博物馆不激活；
- 自驾餐饮激活 driving-parking，普通步行餐饮不激活。

### 回归样本

至少维护：

1. 城市公共交通短途行程；
2. 航班加高铁的多城市行程；
3. 自有车公路行程；
4. 机场租车并异地还车行程；
5. 包车加司机的偏远景点行程；
6. 含山岳景区和受限餐饮场景的行程。

### 最终验证

每阶段至少运行：

```bash
python3 -m unittest discover -s plugins/travel-planning/tests -p 'test_*.py'
git diff --check
```

涉及前端资源、renderer 或页面结构时，额外运行生成 JavaScript 语法检查和桌面、390px 浏览器交互验收。

## 6. 版本与发布

- 文档等价拆分不单独提升研究结果 schema 版本。
- assignment 新增可选字段时先保留向后兼容；变为必填前提升 workspace 或 assignment 版本。
- 新实体或旧字段语义变化必须提升对应 JSON Schema 版本。
- 删除旧 domain、旧 reference 入口或 legacy profile 属于破坏性变更，需要迁移说明和插件版本更新。
- 完成全部测试后再更新 cachebuster 并重装本地插件，不能手工修改安装缓存。

## 7. 建议的首个实施批次

首批不要同时改完所有领域。建议按以下最小闭环推进：

1. 文档等价拆分；
2. module registry 与 research profile；
3. assignment required modules；
4. `transport.core`、`self_drive`、`car_rental`、`rail` 四个 profile；
5. 对应 submit/audit 校验；
6. 三个交通样本回归。

这个批次能够直接解决当前暴露的自驾和租车缺口，同时验证渐进读取架构是否有效。确认稳定后，再迁移景点类型与餐饮场景 profiles。
