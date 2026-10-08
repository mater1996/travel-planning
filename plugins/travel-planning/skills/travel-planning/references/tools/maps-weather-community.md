# 地图、天气与社区研究

## 何时读取

路线前小红书轻量预研，或路线确认后查询天气、POI、坐标、本地路线、境外地点与具体体验证据时读取。

## 路线前小红书轻量预研

若小红书已配置且当前登录态可用，在 2 至 3 个路线方案前执行一次有上限的只读扫描：

1. 查询“目的地 + 行程长度”和“目的地 + 必吃/美食”；只有季节改变体验时再增加月份或季节。
2. 每类只读取少量高相关原帖，覆盖不同作者、时间和路线取舍，不按互动数机械取前几名。
3. 提取反复出现的景点组合、推荐时段、排队与绕行、地方菜品主题，并记录冲突、疑似推广与样本不足。
4. 写入 `route-context.json`。美食主题不能证明具体门店有售、营业或值得专程绕行。

服务未启动、未登录、触发验证或查询失败时，记录状态与建议查询词后继续路线方案；不在路线确认阶段安装、扫码、反复重试，也不以搜索摘要冒充原帖。

## 天气

近期天气使用 Open-Meteo；中国天气预警保留官方入口：

```bash
python3 skills/travel-planning/scripts/research_sources.py weather \
  --location "杭州" --days 7
```

远期天气只能作为风险信号。页面保留查询时间、状态、复核节点和实际天气入口；影响必须转成事件或 checkpoint 动作。

## 中国境内地图

中国境内 POI 与路线遵循 `$amap-maps`：

```bash
python3 skills/travel-planning/scripts/research_sources.py amap-place \
  --city "杭州" --keywords "西湖风景区 曲院风荷入口"

python3 skills/travel-planning/scripts/research_sources.py amap-route \
  --origin "120.130210,30.259002" \
  --destination "120.144590,30.243710" \
  --mode walking
```

地图耗时不等于门到门时间；还要加入口步行、等待、换乘、安检与缓冲。入口开放、营业与预约回到相应官方来源核验。

## 境外地点

境外地点可用 Nominatim/OpenStreetMap 低频发现坐标候选：

```bash
python3 skills/travel-planning/scripts/research_sources.py osm-place \
  --query "Kiyomizu-dera Niomon, Kyoto, Japan" \
  --countrycodes jp --limit 3
```

一次一个请求，不并发扫点或批量抓取。坐标只是候选，入口名与开放状态仍需官方和实际地图平台确认；同一组路线不混用 GCJ-02 与 WGS84。

## 路线确认后的社区研究

搜索、详情与登录遵循 `$xiaohongshu`，默认只读。可复用 `route-context.json` 的查询词和主题，但必须重新核验具体景点或门店、适用日期、位置与经营信息；路线前样本不能重复计入门店口碑。

临时令牌只保存在权限受限的用户缓存。workspace 只保存公开原帖链接、必要短摘要、作者、发布时间、查询时间、用途、冲突和推广风险。
