# 参考资料总入口

这是 `references/` 根目录唯一的 Markdown 文件，只回答“下一步进入哪个目录”。已有 assignment 时直接按 `required_guides` 读取，不从本页遍历全部文档。

## 阶段路由

| 当前阶段或问题 | 目录入口 | 到目录后怎么选 |
| --- | --- | --- |
| 比较城市顺序、天数与主要交通 | [通用规划](core/index.md) | 只读 planning pipeline；需要判断证据再读 evidence policy |
| 创建 workspace、任务、提交或合并 | [研究工作区](workspace/index.md) | 按 lifecycle、assignments、submission、merge 当前动作选一个文件 |
| 拆分多 Agent、确定波次或验收任务 | [Agent 编排](orchestration/index.md) | 分别选择 task domains、execution waves 或 completion gates |
| 研究景点 | [景点研究](attractions/index.md) | 只读本次激活的景点类型 |
| 比较或落实交通 | [交通研究](transport/index.md) | 只读 flight、rail、self-drive、car-rental 等已激活方式 |
| 研究正餐 | [餐饮研究](dining/index.md) | 按 discovery → operations / route evaluation → ranking 阶段读取 |
| 研究住宿 | [住宿研究](lodging/index.md) | 动态报价、多房容量或晚到时再读专项文件 |
| 调用地图、天气、社区或供应商 | [实时数据工具](tools/index.md) | 先 preflight，再只读对应 provider；失败才读 fallback |
| 生成 plan、JSON 或页面 | [输出与交付](output/index.md) | plan、itinerary、evidence、page structure、interaction、acceptance 分开读取 |
| 做出发前复核 | [行前就绪](core/readiness.md) | 再追加实际激活领域的动态复核项 |

## 目录职责

- `core/`：跨领域阶段、证据和横切风险，不保存领域细节。
- `workspace/`：状态与命令，不决定任务域和研究内容。
- `orchestration/`：任务所有权、依赖波次和完成门槛，不重复 CLI。
- `attractions/`、`transport/`、`dining/`、`lodging/`：领域研究合同与 profiles。
- `tools/`：供应商调用、快照和错误，不决定业务采用。
- `output/`：研究完成后的计划、最终结构、页面和验收。
- [`compat/`](compat/index.md)：旧文件名到新入口的迁移指针；新任务不得读取。

## 渐进读取规则

1. `SKILL.md` 判断当前阶段与不可违反的边界。
2. 目录 `index.md` 列出所有关联文件、读取条件和不该读取的场景。
3. 专项文件给出输入、动作、产出、证据与完成门槛。
4. schema、模板和完整示例只在实际写结果或排错时读取。
5. 无法判断 profile 时，先检查 `research-profile.json` 和 assignment 的 `module_reasons`，不要猜测加载全部。

`registries/research-modules.json` 是机器路由，目录 `index.md` 是人工路由。新增、改名或删除文件时必须同步注册表、SKILL、目录入口和布局测试。
