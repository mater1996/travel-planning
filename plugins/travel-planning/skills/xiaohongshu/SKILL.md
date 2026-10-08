---
name: xiaohongshu
description: 通过插件固定版本的 xpzouying/xiaohongshu-mcp 使用小红书搜索、笔记详情、用户主页、登录，以及用户明确要求时的发布和互动能力。服务使用独立浏览器，不依赖 Chrome 扩展；旅行研究默认只读。
---

# 小红书 MCP

本 Skill 路由已注册的 `xiaohongshu-mcp` Streamable HTTP 工具。上游是非官方自动化项目，固定为 `v2.5.2`；它自带独立浏览器，不读取或控制用户的 Chrome。

## 首次使用

在插件根目录运行：

```bash
python3 skills/xiaohongshu/scripts/setup.py install
python3 skills/xiaohongshu/scripts/setup.py start
python3 skills/xiaohongshu/scripts/setup.py status
```

安装器只下载上游 GitHub Release 的服务与登录二进制，并按锁定的 SHA256 校验。首次启动还会由上游下载并校验约 150 MB 的独立浏览器。如果 `check_login_status` 返回未登录，先停止服务，再启动登录工具：

```bash
python3 skills/xiaohongshu/scripts/setup.py stop
python3 skills/xiaohongshu/scripts/setup.py login
python3 skills/xiaohongshu/scripts/setup.py start
```

登录工具会打开上游自己的可见浏览器窗口，由用户本人用小红书 App 扫码。不得索要 Cookie、密码、短信验证码或浏览器配置文件。

## 执行规则

1. 先调用 `check_login_status`。未登录时只说明上述登录流程；不要自行调用 `delete_cookies`。
2. 旅行研究只调用 `list_feeds`、`search_feeds`、`get_feed_detail`、`user_profile` 和其他明确标注只读的工具。
3. `publish_content`、`publish_with_video`、评论、回复、点赞、收藏和删除 Cookie 都会改变外部状态，只有用户明确要求对应动作时才调用。
4. 搜索得到的 `xsec_token` 只在后续详情读取中传递；不得写入旅行 workspace、最终 JSON、HTML、日志或回答。
5. 只归档公开原帖链接、标题、作者、发布时间、必要摘要和查询时间；不复制整篇笔记、评论全集、未授权图片或临时媒体地址。
6. 控制请求频率。遇到验证码、设备验证、风控或账号提示立即停止，由用户本人处理，不重试绕过。
7. 同一小红书账号不要同时登录其他网页端，否则上游保存的登录态可能被挤下线；手机 App 可正常使用。
8. `v2.5.2` 的网页筛选浮层不可靠地支持一次连续点击多个条件。搜索时省略页面默认值，只传一个真正需要的非默认筛选；旅行轻量预研默认仅传 `publish_time=半年内`，保留页面默认综合排序与不限类型。需要比较其他维度时拆成有上限的独立查询，不在一次 `filters` 中叠加。

工具名和参数边界见 `references/tool-routing.md`；版本、发布包校验值和许可证见 `references/upstream.lock.json` 与 `references/NOTICE.md`。
