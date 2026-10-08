# 降级、错误与合并规则

## 何时读取

自动获取失败、来源不可用、需要生成手工复核入口，或不确定错误能否写成空结果时读取。

## 手工查询降级

```bash
python3 skills/travel-planning/scripts/research_sources.py fallback --kind train \
  --origin "北京南" --destination "上海虹桥" --date "2026-10-03" \
  --fields "车次、时刻、二等座票价和余票"

python3 skills/travel-planning/scripts/research_sources.py fallback --kind ctrip \
  --product "酒店" --city "杭州" --date "2026-10-03 至 2026-10-05" \
  --travelers "2 位成人·1 间房"

python3 skills/travel-planning/scripts/research_sources.py fallback --kind map \
  --city "杭州" --keywords "西湖风景区 曲院风荷入口"

python3 skills/travel-planning/scripts/research_sources.py fallback --kind xiaohongshu \
  --keywords "西湖 10月 日落 入口 避坑"
```

景区 fallback 必须使用已经核对的官方 URL。手工入口只代表 `to_recheck`；平台首页或搜索页不能写成已核验详情。

## 错误分类

- 成功且为空：`no_results`；
- 未认证或凭证缺失：authentication；
- 无权限或授权失败：authorization；
- 额度、频率或风控：rate/verification；
- 上游、网络、超时或解析：分别保留原类型；
- 工具契约不匹配：capability/contract error。

不要把失败改写成“无票、无房、无班次或无餐厅”。停止高频重试，记录缺失字段、失败原因、建议复核时间和可执行入口。

## 来源与合法边界

- 不绕过验证码、风控、频率限制或付费墙，不启用未经授权的私有接口、代理或隐藏自动化。
- 新增供应商、安装工具、配置付费凭证或执行写操作前，核对授权、许可证、数据外发、费用、限额与失败行为，并取得用户明确同意。
- 临时令牌、Cookie、身份证件、订单、支付和授权头不得写入 workspace、日志或页面。

## 合并到行程

- 标准快照进入 `planning.source_snapshots[]`；页面展示 provider、查询时间、刷新提示和供应商实际返回的 HTTPS 入口。
- 机场、车站、酒店等稳定身份可进入本次 `shared_entities[]`；动态报价、库存、班次、营业和地图耗时不跨旅行缓存。
- 地图和天气结果使用 `platform_reported`，人工查询入口使用 `to_recheck`。
- 中国铁路最终回到 12306；聚合平台不替代出票前复核。境外铁路回到对应运营方。
