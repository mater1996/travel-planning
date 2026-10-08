# 工作区生命周期

## 何时读取

首次建档、生成路线方案、确认路线、判断能否进入深度研究，或检查工作区目录职责时读取。

## 初始化

```bash
python3 skills/travel-planning/scripts/research_workspace.py init \
  --trip-id "hangzhou-2026-10" \
  --destination "杭州" \
  --date-range "2026-10-03 至 2026-10-05" \
  --travelers "2 位成人" \
  --origin "上海" \
  --budget "中等" \
  --preferences "人文" \
  --preferences "慢节奏"
```

## 目录职责

```text
.travel-research/<trip-id>/
|-- manifest.json                 # 工作区身份与版本
|-- brief.json                    # 用户需求与硬约束
|-- route-context.json            # 路线前轻量社区信号
|-- route-proposals.json          # 待确认路线候选
|-- selected-route.json           # 唯一已确认路线
|-- research-profile.json         # 本次激活模块与原因
|-- assignments/                  # 任务合同与模板
|-- results/                      # 每个任务的结构化结果
|-- sources/                      # 每个任务的来源记录
|-- snapshots/<task_id>/          # 动态供应商标准快照
|-- evidence/main/                # 主 Agent 证据
|-- evidence/<task_id>/           # 任务不可覆盖证据
|-- state/                        # 合并状态与装配计划
`-- artifacts/                    # itinerary、audit 与 HTML
```

## 路线前与路线确认

主 Agent 先把有上限的小红书轻量预研写入 `route-context.json`，只保存公开原帖引用、查询时间、路线信号、地方美食主题、冲突、推广风险和置信度。不可用时记录失败类型与建议查询词，不保存临时令牌，也不以搜索摘要冒充原帖。

结合 brief 生成 2 至 3 个 `route-proposals.json` 方案。用户确认后执行：

```bash
python3 skills/travel-planning/scripts/research_workspace.py select-route \
  --workspace ".travel-research/hangzhou-2026-10" \
  --route-file "/tmp/selected-route.json"
```

深度研究 assignment 只能在 `selected-route.json` 存在后创建。`select-route` 同时生成 `research-profile.json`；路线的 `research_features` 应声明 `transport_modes[]`、`attraction_types[]` 和 `scenarios[]`。采用老街、古城、市场、步行街或多节点 Citywalk 时，`attraction_types[]` 必须写 `urban_walk`。旧路线没有结构化特征时显式进入 `legacy_core_only`，不能猜测加载全部 profile。

## 状态变化

- 日期、人数、出发地或路线改变时更新路线输入，并使受影响 assignment 及下游结果失效。
- 路线未变化时不要为追逐新热门内容反复重开确认。
- `status` 命令可检查任务、revision 和合并准备度；它不替代领域完成门槛。

## 数据安全

不把 API Key、Cookie、授权头、账号密码、身份证件、乘车人证件、保单号、订单号或支付信息写入 workspace。只归档官方公开、用户授权或许可证允许的内容。
