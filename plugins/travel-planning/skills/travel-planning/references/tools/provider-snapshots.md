# 供应商查询与标准快照

## 何时读取

航班、铁路、空铁联运或酒店研究需要实时平台候选并写入 workspace 时读取。

## 落盘边界

- 路线确认后的已配置只读查询可直接执行，不逐次请求同意。
- 正式查询同时传入 `--workspace` 与已分配的 `--task-id`。
- 飞猪与飞常准响应由 `scripts/source_adapters.py` 转换为 `travel-source-snapshot/v1`；错误使用 `travel-source-error/v1`。
- 快照写入 `snapshots/<task_id>/`，结果只提交 `source_snapshot_ids[]`。
- 采用候选用 `inventory_refs[]` 绑定 `snapshot_id + offer_id + role`，不能透传供应商私有响应。

## 航班、铁路与酒店

通用发现先使用 `$flyai`，运行状态、指定航班、铁路与空铁联运补充使用 `$variflight`。开放式航班和铁路候选必须覆盖最早、最晚、时长、价格和推荐排序，不能用一次低价榜推断全天没有合适班次。

```bash
python3 skills/travel-planning/scripts/research_sources.py flyai-flight-coverage \
  --origin "北京" --destination "上海" --date 2026-10-03 \
  --workspace ".travel-research/example-trip" --task-id transport-intercity

python3 skills/travel-planning/scripts/research_sources.py flyai-train-coverage \
  --origin "北京南" --destination "上海虹桥" --date 2026-10-03 \
  --workspace ".travel-research/example-trip" --task-id transport-intercity

python3 skills/travel-planning/scripts/research_sources.py flyai-hotel \
  --destination "杭州" --poi "西湖" \
  --check-in 2026-10-03 --check-out 2026-10-05 \
  --adults 4 --rooms 2 --bed-type "双床房" \
  --workspace ".travel-research/example-trip" --task-id lodging
```

商圈酒店查询只用于发现。采用前按酒店全名再次查询，并用地图核对城市、行政区、地址、坐标和目标锚点。供应商没有校验多间同房型库存时，只能标为报价候选。

飞常准包装命令包括 `variflight-flight`、`variflight-flight-number`、`variflight-flight-price`、`variflight-flight-comfort`、`variflight-train`、`variflight-train-stations` 和 `variflight-air-rail`。IATA 使用三位城市或机场代码；价格和空铁联运只接受城市代码。

## 状态语义

- `platform_reported`：供应商在查询时返回，不是未来承诺。
- `no_results`：请求成功但结果为空，不等于供应商故障。
- 认证、授权、额度、网络、解析、空结果和供应商故障分别记录，不统一写成“没有班次”。
- quote、operational、lookup 的实时窗口只描述供应商新鲜度；快照永久保留为查询记录，购买或出发前按 `refresh_before` 复核。

## 安全

原始供应商私有字段、凭证、Cookie、授权头和临时令牌不得进入 workspace、JSON、HTML 或日志。原始响应最多保留 SHA-256 哈希。
