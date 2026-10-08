# Assignment 创建与版本

## 何时读取

路线确认后创建任务、建立依赖、解释 `required_guides`，或因输入变化重新分配任务时读取。

## 创建任务

```bash
python3 skills/travel-planning/scripts/research_workspace.py assign \
  --workspace ".travel-research/hangzhou-2026-10" \
  --task-id "transport-intercity" \
  --domain "transport-intercity" \
  --instructions "比较城际方案与关键门到门交通边"
```

带依赖和阶段的任务：

```bash
python3 skills/travel-planning/scripts/research_workspace.py assign \
  --workspace ".travel-research/hangzhou-2026-10" \
  --task-id "restaurant-ranking" \
  --domain "restaurant-research" \
  --stage "restaurant_ranking" \
  --depends-on "restaurant-discovery" \
  --depends-on "meal-route-evaluation" \
  --instructions "完成证据化比较、主备排序和切换条件"
```

依赖任务必须已按可接受状态提交。未形成稳定景点出口、住宿锚点和餐窗时，不提前创建餐厅路线评估。

## Assignment 固化内容

脚本生成并固定：

- `input_paths` 与 `read_first`；
- 只读 `dependency_paths`；
- `owned_paths` 与 `forbidden_paths`；
- domain、stage、字段所有权和来源 ID 前缀；
- `required_modules`、`module_reasons` 与 `required_guides`；
- `schema_refs` 与 `completion_checks`；
- 结果模板、模板摘要、`input_revision` 和 submit 命令。

Agent 先读 assignment 本身，再按顺序读 `read_first`、`required_guides`、依赖结果、结果模板和 schema。总入口仅用于人工判断，不替代 assignment，也不应触发全目录扫描。

## Revision 契约

`input_revision` 必须覆盖输入文件、依赖结果、结果模板、模块注册表、required guides 和 schemas。任一内容变化后：

1. 旧结果拒绝 submit 或 merge；
2. 主 Agent 判断影响范围；
3. 只刷新受影响任务和下游任务；
4. Agent 重新读取 assignment 指定内容。

不得通过手改 revision 绕过重研，也不得把旧 workspace 结果复制到新旅行。

## 写入边界

研究 Agent 只能写 assignment 声明的结果、来源、快照与证据路径。不能修改其他任务结果、`selected-route.json`、`state/`、`artifacts/`、Skill 文档或最终页面。
