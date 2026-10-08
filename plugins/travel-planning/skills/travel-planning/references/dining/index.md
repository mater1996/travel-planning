# 餐饮研究入口

本文件既是 `dining.core` 的公共契约，也是餐厅三阶段流程的路由页。餐厅研究必须围绕已经形成的餐窗和空间锚点进行，不能先搜热门榜单再硬塞进路线。

## 关联文件与读取条件

| 文件 | 谁读取 | 何时读取 | 产出 |
| --- | --- | --- | --- |
| [discovery.md](discovery.md) | restaurant-discovery | 餐窗、前后锚点和搜索边界稳定后 | 餐厅实体、动态快照、逐餐候选集和旅行价值判断 |
| [operations.md](operations.md) | discovery，必要时 ranking 复核 | 每个候选需要判断适用餐窗能否执行时 | 营业、预约、排队、菜单、人均、停车等动态覆盖 |
| [route-evaluation.md](route-evaluation.md) | meal-route-evaluation | discovery 完整提交且主 Agent 已处理 route-worthy 影响后 | 每餐基准路线与全部候选的双腿路线 |
| [ranking.md](ranking.md) | restaurant-ranking | discovery 与 route evaluation 集合完全一致后 | 连续排名、主选、备选与切换条件 |
| [constrained-scenarios.md](constrained-scenarios.md) | discovery 与 ranking | 机场、封闭景区、服务区、深夜或偏远地确实候选不足时 | 受限证明、应急补给和下一可用餐点 |

## 前置输入

- 每个正式餐窗的日期、餐别、开始结束时间和预计用餐时长。
- 前一锚点与下一锚点的名称、具体地址、坐标和事件 ID。
- 默认交通方式、最大额外绕行、人数、预算、忌口、过敏、儿童老人和停车约束。
- 用餐意图：`destination`、`experience` 或 `convenience`。

缺少这些输入时先补餐窗或等待上游任务，不能以“市中心附近”“景点周边”代替准确锚点。

## 阶段依赖

```text
餐窗与锚点
  → discovery + operations
  → 主 Agent 处理 route_worthy 路线影响
  → route-evaluation
  → ranking
  → meal_options 进入日程
```

三个阶段必须使用同一候选集合。路线评估和排序不得静默新增、删除或替换门店；运营失效时退回 discovery 更新候选集并重新执行后续阶段。

## 公共完成门槛

- 正常餐窗有 2 至 3 个真实、去重、可定位到具体分店的候选。
- 受限餐窗说明搜索范围、限制原因、唯一候选证据与应急补给。
- 主选与备选均在适用日期和餐窗内有运营依据，并绑定可执行切换条件。
- 门店身份、社区旅行价值、动态运营和路线耗时分别有对应来源，不混成一个无出处总分。
- 旅行者页面不暴露内部评分、研究阶段或快照结构，只展示会影响选择和执行的信息。
