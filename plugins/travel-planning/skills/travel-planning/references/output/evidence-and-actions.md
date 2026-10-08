# 证据、动态状态与操作入口

## 何时读取

最终行程需要投影来源、快照、动态 claim、预约与购买入口、天气入口或图片时读取。

## 来源与 Claims

- 会变化的事实通过 `source_ids` 或 snapshot 引用来源；估算值明确写“估算”“预计”或“约”。
- `sources[].kind` 使用 official、transport_official、booking_platform、community、map 等支持当前字段的类型。
- `claims[]` 保存会影响执行的重要字段级证据；状态使用 `verified`、`platform_reported`、`community_consensus`、`estimated` 或 `to_recheck`。
- 社区体验不能单独证明开放、价格、营业、资质、安全或库存。

## 标准快照

动态交通与住宿进入 `planning.source_snapshots[]`，遵守 `travel-source-snapshot/v1`。候选通过 `inventory_refs[]` 的 snapshot、offer 和 role 关联；role 使用 `candidate_quote`、`operational_check` 或 `station_lookup`。

`platform_reported` 表示本次返回记录，`no_results` 表示成功空结果。错误使用 `travel-source-error/v1`，不得伪装成空快照。价格同时保留 amount、currency、basis 与原始 display；只有供应商实际返回的 HTTPS 地址可进入 action link。

实时时效窗口不使查询记录失效，也不阻断规划交付；购买、出发或使用前按 `refresh_before` 复核价格、库存与运行状态。

## 操作链接

`to_recheck` 至少提供一个真实可执行的 HTTPS `action_links[]`，标签写明平台、对象、日期、站点或待核字段，disclaimer 说明缺口与复核时间。

常用类型包括：

- `map`、`weather`、`weather_warning`；
- `official_homepage`、`official_notice`、`official_booking`、`official_wechat`；
- `ticket`、`train`、`bus`、`hotel`、`restaurant`；
- `guide`、`image_source` 与 `source`。

官网、公告、网页预约和微信公众号说明不可混用。没有直接预约入口时提供官方说明、复制公众号名或平台搜索入口，不猜测详情深链、不生成二维码。

## 图片

- 可展示图片来自用户、商家或机构明确允许素材，或开放许可图片；记录 alt、作者或机构、许可、原始页面与查询时间。
- checkpoint 图片必须对应当前节点。
- 无合法图片时省略图片，或用 link preview 指向官方相册、地图详情或社区原帖。
- 不复制临时 CDN、无来源菜品图、截图或通用占位图；大图不使用 Data URL。

## 面向旅行者的边界

- 报价候选不写成已锁价、有票、有房或已预订。
- 页面按钮只负责跳转，不自动选座、填乘客、提交订单、付款或修改订单。
- 内部 module、快照结构、评分拆解与研究过程不进入默认页面。
- 价格附近显示查询时间与“最终以平台为准”。
