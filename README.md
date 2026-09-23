# Travel Planning Plugin

面向 Codex 的旅行研究与行程交付插件。它会先比较路线并让用户确认，再按需查询地图、交通、住宿、天气和社区体验，最后生成带来源的 `itinerary.json` 与可独立打开的响应式 `itinerary.html`。

## 在线 Demo

[查看兰州一日游示例](https://starlit-tartufo-3b4ce4.netlify.app/)，可直接体验最终行程页面的路线图、逐日时间轴、关键信息一览和移动端布局。

Demo 用于展示插件的页面交付形态，其中的开放时间、价格、天气和交通状态属于生成时的快照，不能作为当前出行确认依据。

插件不会代订、占座、付款、发送消息或修改订单。价格、余票、库存、开放时间和天气等动态信息只表示查询时点的快照，最终下单前仍需回到官方或供应商页面确认。

当前已验证的安装主路径是 Codex 本地 marketplace。仓库同时保留 Claude Code 与通用宿主所需的清单，方便后续适配，但不把它们表述成已经验收的一键安装流程。

## 能力概览

| 能力 | 数据源与实现 | 是否需要凭证 |
| --- | --- | --- |
| 完整行程规划 | `travel-planning` Skill、结构化研究工作区、审查器和响应式页面渲染器 | 否 |
| 中国境内地点与路线 | 高德地图官方 MCP | `AMAP_API_KEY` |
| 航班、火车、酒店和旅行产品 | 飞猪 FlyAI 官方 CLI | `FLYAI_API_KEY` |
| 航班运行、价格、铁路和空铁联运 | 飞常准 Aviation 与 Tripmatch MCP | `VARIFLIGHT_API_KEY` |
| 近期玩法、美食和避坑 | 固定版本 `xpzouying/xiaohongshu-mcp`，本机独立浏览器 | 需要用户本人扫码登录 |
| 境外地点与近期天气 | OpenStreetMap、Open-Meteo | 否 |

插件统一的是安装、能力发现、权限边界和旅行编排。各数据源仍使用最合适的官方 CLI、MCP 或公开 API，并不会为了形式统一而重写成同一种协议。

## 快速接入 Codex

### 1. 准备运行环境

请先准备：

- 支持 `codex plugin` 命令的 Codex CLI
- Python 3.10 或更高版本
- Node.js 22.14.0 或更高版本，并确保 `npm`、`npx` 可用
- 一个不会被临时清理的仓库目录或解压目录

Node.js 22.14.0 覆盖了高德、飞猪和飞常准三个 Node Provider 的运行要求。小红书的预编译工具目前支持 macOS Apple Silicon 和 Linux x86_64；不使用小红书时不影响其他能力。

### 2. 注册 marketplace 并安装插件

拿到本仓库或发布包并进入它的根目录。该目录下应同时存在 `.agents/plugins/marketplace.json` 和 `plugins/travel-planning/`。

```bash
cd /absolute/path/to/travel-planning
codex plugin marketplace add "$PWD" --json
codex plugin add travel-planning@local --json
```

检查安装结果：

```bash
codex plugin list
```

列表中应出现 `travel-planning@local`，状态为 `installed, enabled`。安装或升级后请新建一个 Codex 会话，让新 Skill 与 MCP 配置从干净上下文加载。

如果 `local` marketplace 已经注册，无需重复执行 `marketplace add`。拉取新版仓库或替换发布包后，重新执行 `codex plugin add travel-planning@local --json`，然后新建会话即可。

### 3. 配置需要的数据源

数据源按需启用，不必一次配齐。OpenStreetMap 和 Open-Meteo 无需 Key；高德、飞猪和飞常准分别只接收自己的凭证。

推荐把配置放在用户目录，避免凭证进入仓库或分发包：

```bash
mkdir -p ~/.config/travel-planning
cp plugins/travel-planning/config/sources.example.env \
  ~/.config/travel-planning/sources.local.env
chmod 600 ~/.config/travel-planning/sources.local.env
```

编辑 `~/.config/travel-planning/sources.local.env`，只填写需要启用的项目：

```dotenv
AMAP_API_KEY=
FLYAI_API_KEY=
VARIFLIGHT_API_KEY=
```

凭证申请入口：

- 高德 Web 服务 Key：<https://console.amap.com/dev/flow/detail?type=0>
- 飞猪 FlyAI：<https://flyai.open.fliggy.com/console>
- 飞常准：<https://ai.variflight.com/keys>

如需使用其他文件，可在启动 Codex 前设置 `TRAVEL_SOURCES_CONFIG=/absolute/path/to/sources.local.env`。源码开发时也可使用 `plugins/travel-planning/config/sources.local.env`；该文件已被 Git 忽略，且不会进入安装包。

### 4. 可选启用小红书

小红书使用固定版本的本机 HTTP MCP 和独立浏览器，不依赖 Chrome 扩展。首次使用时运行：

```bash
cd plugins/travel-planning
python3 skills/xiaohongshu/scripts/setup.py install
python3 skills/xiaohongshu/scripts/setup.py login
python3 skills/xiaohongshu/scripts/setup.py start
python3 skills/xiaohongshu/scripts/setup.py status
```

`login` 会打开上游登录工具，扫码和账号确认必须由用户本人完成。二进制、Cookie、日志与进程状态保存在 `~/.local/share/travel-planning/xiaohongshu-mcp/`，不会写入插件源码。

后续常用命令：

```bash
python3 skills/xiaohongshu/scripts/setup.py start
python3 skills/xiaohongshu/scripts/setup.py stop
python3 skills/xiaohongshu/scripts/setup.py logs
```

### 5. 运行接入检查

先查看本机具备哪些来源，再执行一次真实协议和上游探测：

```bash
python3 plugins/travel-planning/skills/travel-planning/scripts/research_sources.py capabilities
python3 plugins/travel-planning/skills/travel-planning/scripts/research_sources.py preflight \
  --city "上海"
```

未配置的可选来源会明确显示为不可用或降级，不会阻止其他来源工作。若某次行程必须依赖特定来源，可重复添加 `--require`；任何必需来源失败时，命令都会以非零状态退出。

```bash
python3 plugins/travel-planning/skills/travel-planning/scripts/research_sources.py preflight \
  --city "上海" \
  --require amap-maps \
  --require xiaohongshu
```

`capabilities` 只用于了解配置，不能代替 `preflight`。后者会实际执行 MCP `initialize`、`tools/list` 和只读上游探测。

### 6. 在新会话中使用

完整行程优先调用主 Skill：

```text
使用 $travel-planning 帮我规划 10 月 1 日到 10 月 6 日从北京出发的成都、重庆行程。
2 人，预算 12000 元，偏好美食和历史，节奏不要太赶。先给我 2～3 个路线方案，等我确认后再深度调研并生成页面。
```

也可以直接调用单一数据源：

```text
使用 $amap-maps 比较成都东站到宽窄巷子的地铁和打车路线。
使用 $flyai 查询指定日期北京到成都的航班候选，只做只读比较。
使用 $variflight 核验 3U8882 的运行与舒适度信息。
使用 $xiaohongshu 搜索近期成都早餐体验，不发布、不点赞、不评论。
```

主 Skill 默认先确认路线，再进行深度研究。路线确认后，对已配置来源的只读查询无需逐次授权；登录、验证码、付费凭证、预订、付款和任何外部写操作仍由用户掌控。

## 规划与交付流程

```text
旅行需求
  → 2～3 个路线方案
  → 用户确认路线
  → 数据源 preflight
  → 分来源研究与证据归档
  → 合并本次行程的共享实体
  → itinerary-plan.json
  → itinerary.json 审查
  → itinerary.html 渲染
```

每次行程的数据都保存在当前项目的 `.travel-research/<trip-id>/`，不会建立跨行程缓存。最终交付位于：

```text
.travel-research/<trip-id>/artifacts/itinerary.json
.travel-research/<trip-id>/artifacts/audit.json
.travel-research/<trip-id>/artifacts/itinerary.html
```

页面内联交互脚本和样式，可直接打开或作为单个 HTML 文件分享。JavaScript 被附件预览禁用时，页面仍可通过纯 CSS 完成主要视图切换。

## 仓库结构

```text
.
├── .agents/plugins/marketplace.json       # Codex marketplace 入口
├── .codex/config.toml                     # 当前仓库的开发启用配置
├── plugins/travel-planning/
│   ├── .codex-plugin/plugin.json          # Codex 插件清单
│   ├── .claude-plugin/plugin.json         # Claude Code 兼容清单
│   ├── plugin.json                        # 可移植清单
│   ├── .mcp.json                          # MCP Server 声明
│   ├── config/sources.example.env         # 凭证模板
│   ├── scripts/providers/                 # Provider 启动器
│   ├── skills/                            # 主 Skill 与数据源 Skills
│   └── web/                               # Vue/Vite 页面前端
├── scripts/package_plugin.py
└── Makefile
```

插件按任务域暴露五个 Skill：`travel-planning` 负责跨来源编排，`xiaohongshu`、`flyai`、`amap-maps`、`variflight` 负责对应数据源。插件清单注册高德、飞常准 Aviation、飞常准 Tripmatch 和小红书四个 MCP Server；FlyAI 由主 Skill 通过固定版本 CLI 调用。

## 开发与验证

修改 Vue 页面资源后先构建前端，再校验插件和测试：

```bash
make frontend
python3 /absolute/path/to/plugin-creator/scripts/validate_plugin.py \
  plugins/travel-planning
(cd plugins/travel-planning && python3 -m unittest discover -s tests -p 'test_*.py')
```

`make frontend` 会把兼容转译后的脚本和样式写入 `skills/travel-planning/assets/frontend/`，Python 渲染器再将它们内联进最终页面。若本机没有 `plugin-creator`，至少运行测试，并确认三个插件清单、marketplace 路径和 Skill 名称保持一致。

## 打包与分发

```bash
make package
```

默认产物为 `output/travel-planning-marketplace.zip`：

```text
travel-planning-marketplace/
├── .agents/plugins/marketplace.json
├── plugins/travel-planning/
└── README.md
```

接收方需要先把 ZIP 解压到持久目录，再按照“快速接入 Codex”中的命令注册该目录并安装 `travel-planning@local`。Codex CLI 接收的是 marketplace 目录，不是 ZIP 文件本身。

打包清单由 Git 规则生成。已跟踪文件和未被忽略的新文件会进入 ZIP；`.gitignore`、`.git/info/exclude` 和全局 Git ignore 命中的文件不会进入产物。因此 `sources.local.env`、研究工作区、浏览器截图和本机缓存不会被分发。

如需覆盖默认路径：

```bash
make package \
  PLUGIN_DIR=plugins/travel-planning \
  PACKAGE_OUTPUT=output/custom-name.zip \
  BUNDLE_NAME=custom-marketplace
```

## 常见问题

`codex plugin list` 中看不到插件

确认执行 `marketplace add` 时传入的是包含 `.agents/plugins/marketplace.json` 的根目录，而不是 `plugins/travel-planning/`。然后重新执行 `codex plugin add travel-planning@local --json`。

插件已安装，但当前会话找不到 Skill 或 MCP

安装或升级后新建 Codex 会话。旧会话不会可靠地重新加载插件能力。

Provider 提示缺少 Key

确认文件位于 `~/.config/travel-planning/sources.local.env`、变量名与模板一致，并且等号后没有多余引号或空格。也可以显式设置 `TRAVEL_SOURCES_CONFIG`。

小红书返回 `login_required`

先执行 `setup.py stop`，再执行 `setup.py login` 并由用户完成扫码，最后执行 `setup.py start`。不要在多个进程中同时操作同一个账号的登录态。

预检显示 `degraded`

先看具体来源的原因。未被 `--require` 声明的来源允许降级；行程仍可使用其他实时来源或生成带官方入口、查询条件和复核时间的手动检查项。

## 许可证

本项目原创内容采用 [PolyForm Noncommercial License 1.0.0](LICENSE)，允许个人学习、研究、实验和其他非商业用途，禁止未经授权的商业使用。

项目引用或调用的第三方组件仍适用各自的许可证和版权声明，不因本项目许可证而改变。
