# 实时数据工具入口

本目录只说明跨来源预检、标准快照和本 Skill 包装命令。供应商具体参数、安装与登录分别遵循 `$flyai`、`$variflight`、`$amap-maps` 与 `$xiaohongshu`。

除路线前小红书轻量预研外，只在路线确认并进入深度研究后读取相关文件。

## 文件路由

| 文件 | 何时读取 | 解决的问题 |
| --- | --- | --- |
| [preflight.md](preflight.md) | 路线确认后、分配依赖实时来源的任务前 | 真实健康检查、required provider 与能力边界 |
| [provider-snapshots.md](provider-snapshots.md) | 查询航班、铁路、酒店等动态候选 | 包装命令、标准快照、offer 绑定与状态语义 |
| [maps-weather-community.md](maps-weather-community.md) | 查询 POI、路线、天气、小红书或境外地点 | 坐标、体验证据和路线前轻量研究 |
| [fallback-and-errors.md](fallback-and-errors.md) | 自动查询失败、需要手工入口或错误分类时 | fallback、不可得状态、敏感信息和合并规则 |

## 选择原则

- 只做路线候选：最多读取 `maps-weather-community.md` 的“路线前轻量预研”。
- 航班、铁路、酒店任务：先 `preflight.md`，再 `provider-snapshots.md`。
- 景点、本地交通或餐厅定位：读取 `maps-weather-community.md`。
- 任一工具失败：只追加 `fallback-and-errors.md`，不回读其他供应商文件。

配置存在或 `capabilities` 可见不等于服务可用；实时健康必须以本次 initialize、tools/list 和只读探测为准。
