# 执行波次与依赖

## 何时读取

复杂行程需要并行研究、餐厅三阶段需要排序、依赖变化导致任务失效，或槽位不足需要排队时读取。

## 标准波次

1. 主 Agent 创建唯一 workspace，确认路线，并生成 `research-profile.json`。
2. 第一波并行启动 `attractions`、`transport-intercity` 与 `lodging`；已确认自驾时同时创建 `road-trip`。
3. 城际方案稳定后启动 `transport-local` 与 `readiness`；初始事件骨架形成后生成 `meal-windows`。
4. 景点入口出口、住宿锚点和餐窗稳定后创建 `restaurant-discovery`。同时可启动 `weather-risk`。
5. discovery 若输出 `route_influence.status=review_route`，主 Agent 先复核同日路线，必要时更新活动和锚点。
6. 路线决定稳定后创建 `meal-route-evaluation`，最后创建 `restaurant-ranking`。三阶段结果分别保存，不相互覆盖，候选集合必须一致。
7. 所有任务提交后 merge，共享实体进入 canonical state；生成计划、复核 decisions、assemble，再运行一次确定性 audit。

兼容任务名 `route-data-meals` 可在旧 workspace 使用，但新任务应显式区分 discovery、route evaluation 与 ranking。

## Assignment 创建规则

依赖未完成时不提前创建下游 assignment。每个 assignment 至少包含：

- workspace 绝对路径、`task_id`、`domain` 和可选 `stage`；
- `read_first`、只读依赖和输入版本；
- `required_modules`、`required_guides`、`schema_refs` 与 `completion_checks`；
- `owned_paths`、`forbidden_paths` 与来源 ID 前缀；
- 结果模板、模板摘要和 submit 命令。

Agent 按 `read_first` → `required_guides` → 依赖结果 → schema 的顺序读取，不从总入口遍历全部 references。

## 失效与修补

- `input_revision` 必须包含依赖内容、模板、guide、schema 与注册表版本；任一变化后旧结果不能提交。
- 日期、人数、出发地、路线或住宿锚点变化时，只失效受影响的任务与下游任务。
- 硬时间候选流出现冲突时，先重排，再按换交通、缩短次要景点、取消次要活动降级；仍缺字段时创建 `gap-<domain>-vN`。
- 槽位不足时按波次排队，主 Agent 不串行替代全部研究。
- audit 失败后修补对应研究或决策并重跑，不启动独立审查 Agent。

## 并行边界

只有输入独立且字段所有权不重叠的任务才能并行。餐厅路线评估依赖稳定锚点，ranking 依赖 discovery 与路线评估；本地交通依赖景点入口出口和住宿锚点。这些依赖不能为追求并行而省略。
