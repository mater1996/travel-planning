# 输出与交付入口

本目录只在研究合并后读取。领域研究 Agent 不加载输出实现细节；装配、页面和验收也分开读取，避免一次载入完整 schema 与 UI 规则。

## 文件路由

| 文件 | 何时读取 | 解决的问题 |
| --- | --- | --- |
| [plan-contract.md](plan-contract.md) | merge 后生成候选 plan 或编辑 decisions | base、decisions、物化 plan、摘要绑定与复核状态 |
| [itinerary-contract.md](itinerary-contract.md) | assemble 或排查实体引用 | 最终顶层结构、collections、事件、景点、交通、住宿与预算 |
| [evidence-and-actions.md](evidence-and-actions.md) | 处理来源、动态状态、预约入口、图片或操作链接 | evidence、snapshot、claim、action link 与展示边界 |
| [page-structure.md](page-structure.md) | 设计页面信息层级或修改 renderer 结构 | 顶部、时间轴、一览、路线图与卡片内容 |
| [page-interactions.md](page-interactions.md) | 修改切换、筛选、折叠、地图、轮播或外链 | 可逆交互、渐进增强、键盘触控与降级 |
| [browser-acceptance.md](browser-acceptance.md) | renderer 或前端资源发生变化后 | 语法、真实浏览器、移动端、打印与交付验收 |

## 推荐顺序

研究 merge → `plan-contract.md` → 主 Agent 复核 decisions → `itinerary-contract.md` → assemble → audit。只有 renderer、页面结构或交互变化时，才继续读取三个页面文件。

不要为单次目的地创建专用装配脚本。schema、assembler、audit 与 renderer 是最终机器权威；文档解释何时读取和为何失败。
