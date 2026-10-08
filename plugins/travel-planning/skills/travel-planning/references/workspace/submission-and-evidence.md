# 结果提交与证据归档

## 何时读取

研究任务准备写结果、保存来源、落动态快照、中途归档资料或执行 submit 时读取。

## 结果结构

结果从 assignment 的 `result_template` 复制，不自行发明外层结构。`summary` 不超过 200 字；结构化内容写入 `source_snapshot_ids[]`、`entities`、`shared_entities[]`、`event_bindings[]`、`constraints[]`、`unresolved[]` 与 `source_ids[]`。

只有其他 Agent、排程、确定性校验或页面需要的稳定实体进入 `shared_entities[]`。动态评分、报价、营业、排队与库存留在任务实体和标准快照。

## 标准快照

正式飞猪或飞常准查询同时传入 `--workspace` 与已分配的 `--task-id`，标准快照进入 `snapshots/<task_id>/`。结果只引用 snapshot ID；采用的交通或住宿候选用 `inventory_refs[]` 绑定 `snapshot_id + offer_id + role`。

提交时脚本重新校验快照、offer、来源 ID、HTTPS 链接、模板摘要、输入版本和领域 completion checks。

## 提交

```bash
python3 skills/travel-planning/scripts/research_workspace.py submit \
  --workspace ".travel-research/hangzhou-2026-10" \
  --task-id "transport-intercity" \
  --result-file "/tmp/transport-intercity-result.json" \
  --sources-file "/tmp/transport-intercity-sources.json"
```

`--sources-file` 接受临时 JSON 对象或数组，提交后写为 `sources/<task_id>.jsonl`。每条来源至少包含任务前缀 ID、标题、HTTPS URL、来源类型与查询时间；脚本同时生成不可覆盖的 `evidence/<task_id>/<source_id>.json`。

## 中途归档

发现后续可能引用的来源时立即归档，不依赖聊天上下文：

```bash
python3 skills/travel-planning/scripts/research_workspace.py archive \
  --workspace ".travel-research/hangzhou-2026-10" \
  --record-id "hangzhou-tourism-notices" \
  --task-id main --kind link \
  --title "杭州文旅公告入口" \
  --url "https://wgly.hangzhou.gov.cn/" \
  --source-kind official --location "杭州" --topic "文旅公告" \
  --tag hangzhou --tag official \
  --summary "用于复核大型活动和临时关闭" \
  --freshness dynamic
```

允许归档 PDF、HTML、Markdown、文本、JSON、CSV、DOCX、XLSX 和常见图片，单文件上限 25 MiB；记录原名、大小与 SHA-256。原临时文件是否删除由调用方决定。

## 新鲜度与状态

- `dynamic`：价格、库存、时刻、天气和临时公告，在购买、出发或使用节点复核；
- `seasonal`：季节玩法和装备，只作相同季节候选；
- `stable`：官方入口、地理背景和长期规则，关键事实仍按适用日期复核。

认证失败、限流、网络错误与成功空结果必须区分。凭证、Cookie、授权头、身份证件和订单信息不得进入结果、来源、证据或快照。
