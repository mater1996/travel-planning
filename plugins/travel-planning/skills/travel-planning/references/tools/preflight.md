# 数据源预检

## 何时读取

路线已确认，准备创建依赖地图、交通、住宿、天气或社区来源的 assignment 时读取。离线文档编辑或页面样式修改不需要预检。

## 命令

```bash
python3 skills/travel-planning/scripts/research_sources.py preflight \
  --city "杭州" \
  --airport HGH \
  --require amap-maps \
  --require flyai \
  --require open-meteo \
  --require xiaohongshu
```

`preflight` 对插件 MCP 执行真实 `initialize`、`tools/list`、工具契约检查和只读上游探测。状态使用 `ready`、`degraded` 或 `unavailable`；只有本次 `--require` 的来源未就绪时返回非零。

`--skip-upstream` 只用于离线诊断，不能证明服务可用于深度研究。配置文件、凭证存在或 capabilities 声明都不能代替协议与上游探测。

## 何时 require

| 来源 | 触发条件 |
| --- | --- |
| `amap-maps` | 中国境内 POI、本地路线、自驾、餐厅或停车研究 |
| `flyai` | 航班、铁路、酒店、景点或旅行产品的通用平台发现 |
| `variflight-aviation` | 航班号、运行状态、价格、舒适度或机场天气 |
| `variflight-tripmatch` | 铁路、站点或空铁联运候选 |
| `open-meteo` | 近期天气与逐日风险 |
| `xiaohongshu` | 路线前社区轻量预研或具体景点、餐厅体验研究 |

只 require 本次实际需要的来源。未涉及航班时不要求 Aviation，未涉及铁路或空铁联运时不要求 Tripmatch。

## 处理结果

- `ready`：可继续只读查询，不代表未来库存或价格已确认。
- `degraded`：核对缺失能力是否影响本任务；不影响时记录限制后继续。
- `unavailable`：依赖任务不能假装已查询。修复服务、使用合法替代来源，或生成手工复核入口。

预检不授权预订、占座、付款、发布、互动或订单修改。新增工具、付费凭证或写操作需要用户明确授权。
