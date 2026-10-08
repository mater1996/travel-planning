# 开源旅行规划 Skill 对标记录

核验日期：2026-09-20。本文用于维护 Skill，不是每次规划都要读取的运行时说明。

## 对标项目

- [skywain/trip-planner-skill](https://github.com/skywain/trip-planner-skill)：阶段式研究、行前简报、严格自检、路线/日照/ICS/KML 工具最完整。借鉴其行前就绪、行李衔接、时区、分开出票风险、复核阶梯和“动态事实必须带来源与日期”的思路。
- [tczyliu/china-travel-kit](https://github.com/tczyliu/china-travel-kit)：中国旅行数据源分层、双语地名、无障碍/老人儿童/饮食、季节装备和官方实时复核边界清晰。借鉴其安全与新鲜度分层，以及把 OpenStreetMap 只作为候选数据、再回到官方实时复核的边界。
- [mtnrabi/travel-agent-skills](https://github.com/mtnrabi/travel-agent-skills)：通过独立航班/酒店接口返回实时价格与链接，强调调用成本、空结果与服务故障的区分、红眼航班和酒店日期对齐。借鉴错误语义、调用成本披露和入住夜校验；不默认引入 RapidAPI、代理或付费密钥。
- [XiaoiYuyao/travel-agent-skill](https://github.com/XiaoiYuyao/travel-agent-skill)：中文交通、住宿、餐饮、预算和 Word/网页输出流程较直观。可借鉴多格式交付，但其来源与动态信息契约不足以替代本 Skill。
- [chaoliuzhu65-tech/universal-travel-planner-skill](https://github.com/chaoliuzhu65-tech/universal-travel-planner-skill)：覆盖 12306 MCP、高德、酒店比价和多格式输出。其非官方 12306 自动化与猜测式平台深链不采用；只保留业务差旅预算、平台对比和多格式输出的思路。
- [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)：Apache-2.0 许可的非官方 Streamable HTTP MCP，使用自己管理的独立浏览器提供认证、搜索、详情、主页、发布和互动能力。插件固定 `v2.5.2` / commit `8eae4eb22ca1135e53f3e2da6c449fdfe5b492ff`，按 GitHub Release SHA256 安装；旅行规划默认只读，写操作必须来自用户明确请求。
- [SciPhi-AI/agent-search](https://github.com/SciPhi-AI/agent-search)：通用 Bing/AgentSearch RAG 编排器，最后代码活动较早且依赖 OpenAI 0.27.x；不提供小红书连接能力，所以不作为本项目数据源。

## 已补入本 Skill

- 国际旅行的签证/入境/过境、官方安全健康提示、保险、货币支付、通信和时区。
- 节假日之外的地方节庆、赛事、宗教时段、季节停运和景点维护检查。
- 红眼航班与酒店入住夜对齐，分开出票、自行托运、机场/航站楼和行李额度风险。
- 行李从退房到入住、换乘和景区游览的完整路径。
- 老人儿童、无障碍、饮食过敏、海拔/高温耐受和季节装备。
- `book_now` / `book_when_open` / `recheck_later` / `optional` 的预订优先级，以及 T-14/T-7/T-3/T-1 复核阶梯。
- 境外地点的低频 Nominatim/OpenStreetMap 查询；中国境内仍优先高德，入口开放状态仍回到景区官方确认。
- 小红书标准 HTTP MCP 集成、独立浏览器登录、旅行场景只读约束、临时令牌不归档与手动降级入口。

## 明确不采用

- 未获授权的 12306 私有接口、验证码绕过、网页抓取或声称可稳定返回实时余票的 MCP。
- 猜测携程酒店/机票详情 URL，把平台首页或拼接链接冒充为实际查询结果。
- 轮换 UA/IP、住宅代理、隐藏自动化或其他规避平台风控的方法。
- 将 Google Flights 缓存、聚合平台价格或单篇社区笔记写成可购买库存或官方事实。
- 未在 Skill 中评估并声明价格、请求范围和数据发送边界的付费第三方 API。

## 可后续按需增加

- 经单独评估后接入有正式授权、清晰计费和可审计错误状态的新航班/酒店 API；已配置的只读来源运行时不重复请求用户同意。
- 从 `booking_tasks[]` 生成 ICS 提醒，以及从已核验坐标生成 KML/GPX 离线地图。
- 独立严格校验器，检查动态事实的来源、日期、复核链接、跨时区日期和行程时间冲突。
- Word/PDF 等派生交付物；`itinerary.json` 仍应是唯一结构化事实源。
