#!/usr/bin/env python3
"""Query approved travel data sources and build manual verification fallbacks."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
PLUGIN_ROOT = Path(__file__).resolve().parents[3]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from source_adapters import (  # noqa: E402
    PROVIDERS,
    AdapterError,
    adapter,
    call_mcp_http,
    call_mcp_stdio,
    probe_mcp_http,
    probe_mcp_stdio,
    provider_capabilities,
    provider_command,
    run_json_cli,
)
from research_workspace import WorkspaceError, store_source_snapshot  # noqa: E402
from scripts.providers.amap_mcp import (  # noqa: E402
    command as amap_mcp_command,
    load_config as load_amap_environment,
)
from scripts.runtime_env import (  # noqa: E402
    SOURCE_KEYS,
    SourceEnvironmentError,
    load_source_environment,
    source_config_file,
)


OPEN_METEO_GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
AMAP_API = "https://restapi.amap.com"
AMAP_DOCS = "https://lbs.amap.com/api/webservice/guide/api/direction"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "travel-planning/1.0 (read-only public API client)"
SKILL_ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG_FILE = source_config_file(os.environ)
XHS_DEFAULT_URL = "http://127.0.0.1:18060/mcp"
XHS_DEFAULT_DATA_ROOT = Path.home() / ".local" / "share" / "travel-planning" / "xiaohongshu-mcp"
XHS_DATA_ROOT = Path(
    os.environ.get(
        "TRAVEL_XHS_MCP_HOME",
        str(XHS_DEFAULT_DATA_ROOT),
    )
).expanduser().resolve()
XHS_TOKEN_CACHE = XHS_DATA_ROOT / "state" / "search-tokens.json"
ALLOWED_LOCAL_CONFIG_KEYS = SOURCE_KEYS

TRANSPORT_COVERAGE_SORTS = (6, 7, 4, 3, 2)
TRANSPORT_SORT_LABELS = {
    2: "recommended",
    3: "price_asc",
    4: "duration_asc",
    6: "departure_early",
    7: "departure_late",
}

PREFLIGHT_SOURCES = (
    "amap-maps",
    "variflight-aviation",
    "variflight-tripmatch",
    "flyai",
    "open-meteo",
    "xiaohongshu",
)

WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    56: "轻微冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻微冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴强冰雹",
}


def weather_icon_code(code: int | None) -> str:
    if code == 0:
        return "clear_day"
    if code in {1, 2}:
        return "partly_cloudy"
    if code == 3:
        return "cloudy"
    if code in {45, 48}:
        return "fog"
    if code in {51, 53, 55, 56, 57}:
        return "drizzle"
    if code in {61, 63, 66, 80, 81}:
        return "rain"
    if code in {65, 67, 82}:
        return "heavy_rain"
    if code in {71, 73, 75, 77, 85, 86}:
        return "snow"
    if code in {95, 96, 99}:
        return "thunderstorm"
    return "unknown"


class SourceError(RuntimeError):
    """A source is unavailable or returned an invalid response."""


def load_local_config(path: Path = LOCAL_CONFIG_FILE) -> None:
    """Load the plugin-level allowlisted provider environment into this process."""
    try:
        environment = load_source_environment(
            os.environ,
            allowed_keys=ALLOWED_LOCAL_CONFIG_KEYS,
            config_path=path,
        )
    except SourceEnvironmentError as error:
        raise SourceError(str(error)) from error
    for key in ALLOWED_LOCAL_CONFIG_KEYS:
        if environment.get(key) and key not in os.environ:
            os.environ[key] = environment[key]


load_local_config()


def checked_at() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def request_json(base_url: str, params: dict[str, Any], timeout: int = 20) -> Any:
    clean = {key: value for key, value in params.items() if value not in (None, "")}
    url = f"{base_url}?{urlencode(clean, doseq=True)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise SourceError(f"HTTP {error.code}: {base_url}") from error
    except URLError as error:
        raise SourceError(f"无法访问 {base_url}: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise SourceError(f"来源未返回有效 JSON: {base_url}") from error


def post_json(url: str, payload: dict[str, Any], timeout: int = 180) -> Any:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        message = f"HTTP {error.code}: {url}"
        try:
            body = json.loads(error.read().decode("utf-8"))
            detail = body.get("error") or body.get("message")
            code = body.get("code")
            if detail:
                message += f" · {code + ': ' if code else ''}{detail}"
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        raise SourceError(message) from error
    except URLError as error:
        raise SourceError(f"无法访问 {url}: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise SourceError(f"来源未返回有效 JSON: {url}") from error


def xhs_base_url() -> str:
    raw = os.environ.get("XHS_READONLY_URL", XHS_DEFAULT_URL).rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SourceError("小红书只读服务只允许本机 loopback HTTP 地址")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SourceError("XHS_READONLY_URL 不能包含凭证、查询参数或片段")
    return raw


def xhs_token_cache_path() -> Path:
    custom = os.environ.get("XHS_TOKEN_CACHE")
    return Path(custom).expanduser().resolve() if custom else XHS_TOKEN_CACHE


def read_token_cache() -> dict[str, Any]:
    path = xhs_token_cache_path()
    if not path.exists():
        return {"version": 1, "notes": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceError(f"无法读取小红书临时令牌缓存：{path}") from error
    if not isinstance(data, dict) or not isinstance(data.get("notes", {}), dict):
        raise SourceError(f"小红书临时令牌缓存格式无效：{path}")
    return data


def cache_xhs_tokens(feeds: list[dict[str, Any]], query: str) -> None:
    cache = read_token_cache()
    notes = cache.setdefault("notes", {})
    captured = checked_at()
    for feed in feeds:
        note_id = feed.get("id")
        token = feed.get("xsecToken")
        if note_id and token:
            notes[str(note_id)] = {
                "xsec_token": token,
                "source_url": feed.get("sourceUrl"),
                "query": query,
                "captured_at": captured,
            }
    path = xhs_token_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def unwrap_xhs_response(data: Any) -> Any:
    if not isinstance(data, dict):
        raise SourceError("小红书只读服务返回了无效响应")
    if data.get("success") is not True:
        code = data.get("code") or "UNKNOWN"
        message = data.get("error") or data.get("message") or "请求失败"
        raise SourceError(f"小红书只读服务 {code}: {message}")
    return data.get("data")


def xhs_health(_: argparse.Namespace) -> dict[str, Any]:
    url = f"{xhs_base_url()}/health"
    data = request_json(url, {}, timeout=3)
    service = unwrap_xhs_response(data)
    return {
        "status": "available",
        "provider": "小红书本机只读服务（非官方）",
        "service": service,
        "login_url": f"{xhs_base_url()}/login",
        "checked_at": checked_at(),
    }


def xhs_login_status(_: argparse.Namespace) -> dict[str, Any]:
    data = unwrap_xhs_response(post_json(f"{xhs_base_url()}/api/v1/login/status", {}))
    return {
        "status": "authenticated" if data.get("is_logged_in") else "login_required",
        "provider": "小红书本机只读服务（非官方）",
        "session": data,
        "login_url": f"{xhs_base_url()}/login",
        "checked_at": checked_at(),
    }


def normalize_xhs_feed(feed: dict[str, Any]) -> dict[str, Any]:
    note = feed.get("noteCard") or {}
    user = note.get("user") or {}
    interactions = note.get("interactInfo") or {}
    return {
        "note_id": feed.get("id"),
        "title": note.get("displayTitle"),
        "author": user.get("nickname") or user.get("nickName"),
        "note_type": note.get("type"),
        "interactions": {
            "likes": interactions.get("likedCount"),
            "comments": interactions.get("commentCount"),
            "collections": interactions.get("collectedCount"),
            "shares": interactions.get("sharedCount"),
        },
        "source_url": feed.get("sourceUrl"),
    }


def xhs_search(args: argparse.Namespace) -> dict[str, Any]:
    filters = {
        "sort_by": args.sort_by,
        "note_type": args.note_type,
        "publish_time": args.publish_time,
        "search_scope": args.search_scope,
        "location": args.location,
    }
    response = post_json(
        f"{xhs_base_url()}/api/v1/feeds/search",
        {"keyword": args.keyword, "filters": filters},
    )
    data = unwrap_xhs_response(response) or {}
    feeds = data.get("feeds") or []
    cache_xhs_tokens(feeds, args.keyword)
    normalized = [normalize_xhs_feed(feed) for feed in feeds[: args.limit]]
    return {
        "status": "community_reported",
        "provider": "小红书本机只读服务（非官方）",
        "query": {"keyword": args.keyword, "filters": filters},
        "results": normalized,
        "count": len(normalized),
        "checked_at": checked_at(),
        "source": {
            "title": "小红书公开笔记搜索",
            "url": "https://www.xiaohongshu.com/explore",
            "kind": "community_search",
        },
        "disclaimer": "社区内容只用于体验、路线与避坑判断；开放、票价、预约、安全和交通规则必须回到官方来源核验。",
    }


def unix_time(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp > 10_000_000_000:
        timestamp //= 1000
    try:
        return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def xhs_detail(args: argparse.Namespace) -> dict[str, Any]:
    cached = read_token_cache().get("notes", {}).get(args.note_id)
    if not cached or not cached.get("xsec_token"):
        raise SourceError("未找到该笔记的临时访问令牌；请先用 xhs-search 搜索，再读取详情")
    response = post_json(
        f"{xhs_base_url()}/api/v1/feeds/detail",
        {
            "feed_id": args.note_id,
            "xsec_token": cached["xsec_token"],
            "load_all_comments": False,
        },
    )
    data = unwrap_xhs_response(response) or {}
    detail = data.get("data") or {}
    note = detail.get("note") or {}
    user = note.get("user") or {}
    interactions = note.get("interactInfo") or {}
    return {
        "status": "community_reported",
        "provider": "小红书本机只读服务（非官方）",
        "note": {
            "note_id": note.get("noteId") or args.note_id,
            "title": note.get("title"),
            "description": note.get("desc"),
            "note_type": note.get("type"),
            "published_at": unix_time(note.get("time")),
            "ip_location": note.get("ipLocation"),
            "author": user.get("nickname") or user.get("nickName"),
            "interactions": {
                "likes": interactions.get("likedCount"),
                "comments": interactions.get("commentCount"),
                "collections": interactions.get("collectedCount"),
                "shares": interactions.get("sharedCount"),
            },
            "source_url": note.get("sourceUrl") or cached.get("source_url"),
        },
        "checked_at": checked_at(),
        "disclaimer": "未读取或归档完整评论、图片和临时媒体地址；关键事实需与官方来源交叉核验。",
    }


def xhs_mcp_url() -> str:
    raw = os.environ.get("XHS_MCP_URL", XHS_DEFAULT_URL).rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SourceError("XHS_MCP_URL 只允许本机 loopback HTTP 地址")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SourceError("XHS_MCP_URL 不能包含凭证、查询参数或片段")
    if not parsed.path.endswith("/mcp"):
        raise SourceError("XHS_MCP_URL 必须指向 /mcp 端点")
    return raw


def xhs_mcp_call(tool: str, arguments: dict[str, Any], timeout: int = 180) -> Any:
    return call_mcp_http(
        xhs_mcp_url(),
        tool,
        arguments,
        timeout,
        os.environ.get("XHS_MCP_AUTH_TOKEN"),
    )


def xhs_mcp_token_cache_path() -> Path:
    custom = os.environ.get("XHS_TOKEN_CACHE")
    return Path(custom).expanduser().resolve() if custom else XHS_TOKEN_CACHE


def cache_xhs_mcp_tokens(feeds: list[dict[str, Any]], query: str) -> None:
    original = os.environ.get("XHS_TOKEN_CACHE")
    os.environ["XHS_TOKEN_CACHE"] = str(xhs_mcp_token_cache_path())
    try:
        cache_xhs_tokens(feeds, query)
    finally:
        if original is None:
            os.environ.pop("XHS_TOKEN_CACHE", None)
        else:
            os.environ["XHS_TOKEN_CACHE"] = original


def read_xhs_mcp_token_cache() -> dict[str, Any]:
    original = os.environ.get("XHS_TOKEN_CACHE")
    os.environ["XHS_TOKEN_CACHE"] = str(xhs_mcp_token_cache_path())
    try:
        return read_token_cache()
    finally:
        if original is None:
            os.environ.pop("XHS_TOKEN_CACHE", None)
        else:
            os.environ["XHS_TOKEN_CACHE"] = original


def xhs_health(_: argparse.Namespace) -> dict[str, Any]:
    transport = probe_mcp_http(
        xhs_mcp_url(),
        15,
        {"check_login_status", "search_feeds", "get_feed_detail"},
        os.environ.get("XHS_MCP_AUTH_TOKEN"),
    )
    return {
        "status": "ready",
        "provider": "xpzouying/xiaohongshu-mcp",
        "transport": transport,
        "checked_at": checked_at(),
    }


def xhs_login_status(args: argparse.Namespace) -> dict[str, Any]:
    data = xhs_mcp_call("check_login_status", {}, timeout=getattr(args, "timeout", 60))
    text = data.get("text", "") if isinstance(data, dict) else str(data)
    logged_in = "未登录" not in text and ("已登录" in text or "logged in" in text.lower())
    return {
        "status": "authenticated" if logged_in else "login_required",
        "provider": "xpzouying/xiaohongshu-mcp（非官方）",
        "session": {"logged_in": logged_in},
        "checked_at": checked_at(),
    }


def normalize_xhs_mcp_feed(feed: dict[str, Any]) -> dict[str, Any]:
    note = feed.get("noteCard") or {}
    user = note.get("user") or {}
    interactions = note.get("interactInfo") or {}
    note_id = feed.get("id")
    return {
        "note_id": note_id,
        "title": note.get("displayTitle"),
        "author": user.get("nickname") or user.get("nickName"),
        "note_type": note.get("type"),
        "interactions": {
            "likes": interactions.get("likedCount"),
            "comments": interactions.get("commentCount"),
            "collections": interactions.get("collectedCount"),
            "shares": interactions.get("sharedCount"),
        },
        "source_url": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else None,
    }


def xhs_excerpt(value: Any, limit: int = 320) -> str | None:
    if not isinstance(value, str):
        return None
    clean = re.sub(r"\s+", " ", value).strip()
    return clean if len(clean) <= limit else clean[:limit].rstrip() + "…"


def xhs_search(args: argparse.Namespace) -> dict[str, Any]:
    value_map = {
        "sort_by": {
            "relevance": "综合", "latest": "最新", "most_liked": "最多点赞",
            "most_commented": "最多评论", "most_collected": "最多收藏",
        },
        "note_type": {"all": "不限", "video": "视频", "image": "图文"},
        "publish_time": {"all": "不限", "day": "一天内", "week": "一周内", "half_year": "半年内"},
        "search_scope": {"all": "不限", "viewed": "已看过", "unviewed": "未看过", "following": "已关注"},
        "location": {"all": "不限", "same_city": "同城", "nearby": "附近"},
    }
    filters = {
        "sort_by": args.sort_by,
        "note_type": args.note_type,
        "publish_time": args.publish_time,
        "search_scope": args.search_scope,
        "location": args.location,
    }
    upstream_filters = {
        key: value_map[key][value]
        for key, value in filters.items()
        if value not in {"all", "relevance"}
    }
    arguments: dict[str, Any] = {"keyword": args.keyword}
    if upstream_filters:
        arguments["filters"] = upstream_filters
    data = xhs_mcp_call(
        "search_feeds",
        arguments,
    )
    if not isinstance(data, dict):
        raise SourceError("xiaohongshu-mcp 搜索返回格式无效")
    feeds = [feed for feed in (data.get("feeds") or []) if isinstance(feed, dict)]
    for feed in feeds:
        if feed.get("id") and not feed.get("sourceUrl"):
            feed["sourceUrl"] = f"https://www.xiaohongshu.com/explore/{feed['id']}"
    cache_xhs_mcp_tokens(feeds, args.keyword)
    normalized = [normalize_xhs_mcp_feed(feed) for feed in feeds[: args.limit]]
    return {
        "status": "community_reported",
        "provider": "xpzouying/xiaohongshu-mcp（非官方）",
        "query": {"keyword": args.keyword, "filters": filters},
        "results": normalized,
        "count": len(normalized),
        "checked_at": checked_at(),
        "source": {
            "title": "小红书公开笔记搜索",
            "url": "https://www.xiaohongshu.com/explore",
            "kind": "community_search",
        },
        "disclaimer": "临时令牌只用于详情读取；社区内容必须与官方来源交叉核验。",
    }


def xhs_detail(args: argparse.Namespace) -> dict[str, Any]:
    cached = read_xhs_mcp_token_cache().get("notes", {}).get(args.note_id)
    if not cached or not cached.get("xsec_token"):
        raise SourceError("未找到该笔记的临时访问令牌；请先用 xhs-search 搜索，再读取详情")
    data = xhs_mcp_call(
        "get_feed_detail",
        {
            "feed_id": args.note_id,
            "xsec_token": cached["xsec_token"],
            "load_all_comments": False,
        },
    )
    if not isinstance(data, dict):
        raise SourceError("xiaohongshu-mcp 详情返回格式无效")
    detail = data.get("data") if isinstance(data.get("data"), dict) else data
    note = detail.get("note") or {}
    user = note.get("user") or {}
    interactions = note.get("interactInfo") or {}
    return {
        "status": "community_reported",
        "provider": "xpzouying/xiaohongshu-mcp（非官方）",
        "note": {
            "note_id": note.get("noteId") or args.note_id,
            "title": note.get("title"),
            "description_excerpt": xhs_excerpt(note.get("desc") or note.get("body")),
            "note_type": note.get("type"),
            "published_at": unix_time(note.get("time")),
            "ip_location": note.get("ipLocation"),
            "author": user.get("nickname") or user.get("nickName"),
            "interactions": {
                "likes": interactions.get("likedCount"),
                "comments": interactions.get("commentCount"),
                "collections": interactions.get("collectedCount"),
                "shares": interactions.get("sharedCount"),
            },
            "source_url": cached.get("source_url"),
        },
        "checked_at": checked_at(),
        "disclaimer": "未归档评论、图片或临时令牌；关键事实需与官方来源交叉核验。",
    }


def get_amap_key() -> str | None:
    return os.environ.get("AMAP_API_KEY") or os.environ.get("AMAP_MAPS_API_KEY")


def output(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def capabilities(_: argparse.Namespace) -> dict[str, Any]:
    return {
        "attraction_official": {
            "adapter_available": True,
            "live_query_available": False,
            "integration": "公共搜索定位官方页 + 证据归档 + 官方 HTTPS 复核链接",
            "fields": ["门票", "开放时间", "停止入场", "预约", "入口", "临时公告"],
        },
        "weather": {
            "available": True,
            "provider": "Open-Meteo",
            "credential_required": False,
            "fields": ["近期预报", "降雨", "风速", "紫外线", "日出", "日落", "图标代码", "天气查看入口", "预警复核入口"],
            "warning_fallback": "https://www.nmc.cn/publish/alarm.html",
        },
        "map": {
            "available": True,
            "providers": [
                {
                    "name": "高德开放平台",
                    "available": bool(get_amap_key()),
                    "scope": "中国境内 POI 与路径",
                    "credential_required": True,
                    "transport": "官方 stdio MCP + Web 服务 API",
                    "mcp_server": "amap-maps",
                    "mcp_package": "@amap/amap-maps-mcp-server@0.0.8",
                    "skill": "$amap-maps",
                },
                {"name": "Nominatim / OpenStreetMap", "available": True, "scope": "境外地点与入口候选检索", "credential_required": False},
            ],
            "accepted_env": ["AMAP_API_KEY", "AMAP_MAPS_API_KEY"],
            "local_config_file": str(LOCAL_CONFIG_FILE),
            "embed_map": {
                "available": True,
                "credential_required": False,
                "provider": "按设备切换的高德消费端路线页 iframe",
                "caveat": "桌面使用通用路线页，移动端驾车使用 carmap；首次登录提示关闭后由高德保存展示状态",
            },
            "fields": ["POI/入口", "步行", "公交/地铁", "驾车", "门到门基础耗时"],
        },
        "train": {
            "adapter_available": True,
            "live_query_available": provider_capabilities()["fliggy_flyai"]["live_query_available"],
            "provider": "飞猪 FlyAI / 飞常准 Tripmatch；12306 最终复核",
            "integration": "授权平台只读查询 + 12306 官方查询页用户会话交接",
            "reason": "不调用或逆向 12306 非公开接口；平台结果不能替代 12306 最终余票与出票确认",
            "manual_url": "https://www.12306.cn/index/",
        },
        "ctrip": {
            "adapter_available": True,
            "live_query_available": False,
            "provider": "携程",
            "integration": "平台查询页用户会话交接",
            "reason": "未配置获授权的官方数据接口",
            "manual_url": "https://www.ctrip.com/",
        },
        "travel_inventory": {
            "snapshot_schema": "travel-source-snapshot/v1",
            "providers": provider_capabilities(),
            "consent_required_per_query": False,
            "query_policy": "已配置的只读供应商查询在深度规划中直接执行，不逐次请求用户确认",
            "boundary": "只读查询；不提交订单、不占座、不付款；价格、库存和运行状态需在下单前复核",
            "generic_flyai_skill": "$flyai（航班、火车、酒店、景点、活动和旅行产品）",
        },
        "xiaohongshu": {
            "adapter_available": True,
            "live_query_requires": ["固定版本本地 MCP 已安装并启动", "用户本人已扫码登录"],
            "provider": "xpzouying/xiaohongshu-mcp（非官方，固定 v2.5.2）",
            "transport": "MCP Streamable HTTP + 独立无头浏览器",
            "fields": ["近期玩法", "昼夜体验", "入口体验", "拥挤与避坑", "包车和行李体验"],
            "setup": "python3 skills/xiaohongshu/scripts/setup.py install",
            "start": "python3 skills/xiaohongshu/scripts/setup.py start",
            "endpoint": xhs_mcp_url(),
            "travel_default": "read_only",
        },
        "checked_at": checked_at(),
    }


def _preflight_failure(
    source_id: str,
    kind: str,
    required: bool,
    error: Exception,
    started_at: float,
) -> dict[str, Any]:
    failure_kind = error.failure_kind if isinstance(error, AdapterError) else "unavailable"
    return {
        "source_id": source_id,
        "kind": kind,
        "required": required,
        "status": "unavailable",
        "failure_kind": failure_kind,
        "message": str(error),
        "latency_ms": round((time.monotonic() - started_at) * 1000),
    }


def _mcp_preflight(
    *,
    source_id: str,
    command: list[str],
    environment: dict[str, str],
    expected_tools: set[str],
    smoke_tool: str,
    smoke_arguments: dict[str, Any],
    required: bool,
    timeout: int,
    skip_upstream: bool,
) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        transport = probe_mcp_stdio(command, environment, timeout, expected_tools)
        if skip_upstream:
            upstream = {"status": "skipped", "reason": "--skip-upstream"}
            status = "degraded"
        else:
            call_mcp_stdio(command, smoke_tool, smoke_arguments, environment, timeout)
            upstream = {"status": "ready", "tool": smoke_tool}
            status = "ready"
        return {
            "source_id": source_id,
            "kind": "mcp_stdio",
            "required": required,
            "status": status,
            "transport": transport,
            "upstream": upstream,
            "latency_ms": round((time.monotonic() - started_at) * 1000),
        }
    except (AdapterError, OSError, RuntimeError, SourceEnvironmentError) as error:
        return _preflight_failure(source_id, "mcp_stdio", required, error, started_at)


def _amap_preflight(args: argparse.Namespace, required: bool) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        environment = load_amap_environment(os.environ.copy())
        if not environment.get("AMAP_MAPS_API_KEY"):
            raise AdapterError("credential_missing", "未配置 AMAP_MAPS_API_KEY 或 AMAP_API_KEY")
        command = amap_mcp_command()
    except (AdapterError, OSError, RuntimeError, SourceEnvironmentError) as error:
        return _preflight_failure("amap-maps", "mcp_stdio", required, error, started_at)
    return _mcp_preflight(
        source_id="amap-maps",
        command=command,
        environment=environment,
        expected_tools={"maps_weather", "maps_text_search"},
        smoke_tool="maps_weather",
        smoke_arguments={"city": args.city},
        required=required,
        timeout=args.timeout,
        skip_upstream=args.skip_upstream,
    )


def _variflight_preflight(
    args: argparse.Namespace,
    provider_id: str,
    source_id: str,
    expected_tools: set[str],
    smoke_tool: str,
    smoke_arguments: dict[str, Any],
    required: bool,
) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        provider = adapter(provider_id)
        environment = provider.environment()
        spec = PROVIDERS[provider_id]
        if spec.credential_env and not environment.get(spec.credential_env):
            raise AdapterError("credential_missing", f"未配置 {spec.credential_env}")
        command = provider_command(spec)
    except (AdapterError, OSError, RuntimeError, SourceEnvironmentError) as error:
        return _preflight_failure(source_id, "mcp_stdio", required, error, started_at)
    return _mcp_preflight(
        source_id=source_id,
        command=command,
        environment=environment,
        expected_tools=expected_tools,
        smoke_tool=smoke_tool,
        smoke_arguments=smoke_arguments,
        required=required,
        timeout=args.timeout,
        skip_upstream=args.skip_upstream,
    )


def _flyai_preflight(args: argparse.Namespace, required: bool) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        provider = adapter("fliggy_flyai")
        environment = provider.environment()
        command = provider_command(PROVIDERS["fliggy_flyai"])
        if args.skip_upstream:
            upstream = {"status": "skipped", "reason": "--skip-upstream"}
            status = "degraded"
        else:
            run_json_cli(
                command + ["keyword-search", "--query", f"{args.city} 景点"],
                environment,
                args.timeout,
            )
            upstream = {"status": "ready", "command": "keyword-search"}
            status = "ready"
        return {
            "source_id": "flyai",
            "kind": "cli_to_vendor_mcp_api",
            "required": required,
            "status": status,
            "runtime": {"status": "ready", "pinned_version": PROVIDERS["fliggy_flyai"].version},
            "upstream": upstream,
            "latency_ms": round((time.monotonic() - started_at) * 1000),
        }
    except (AdapterError, OSError, RuntimeError, SourceEnvironmentError) as error:
        return _preflight_failure("flyai", "cli_to_vendor_mcp_api", required, error, started_at)


def _weather_preflight(args: argparse.Namespace, required: bool) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        if args.skip_upstream:
            return {
                "source_id": "open-meteo",
                "kind": "public_api",
                "required": required,
                "status": "degraded",
                "upstream": {"status": "skipped", "reason": "--skip-upstream"},
                "latency_ms": round((time.monotonic() - started_at) * 1000),
            }
        payload = request_json(
            OPEN_METEO_FORECAST,
            {
                "latitude": 39.9042,
                "longitude": 116.4074,
                "daily": "weather_code",
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=args.timeout,
        )
        if not isinstance(payload, dict) or not payload.get("daily"):
            raise SourceError("Open-Meteo 健康探测未返回 daily 数据")
        return {
            "source_id": "open-meteo",
            "kind": "public_api",
            "required": required,
            "status": "ready",
            "upstream": {"status": "ready"},
            "latency_ms": round((time.monotonic() - started_at) * 1000),
        }
    except (OSError, RuntimeError, SourceError) as error:
        return _preflight_failure("open-meteo", "public_api", required, error, started_at)


def _xiaohongshu_preflight(args: argparse.Namespace, required: bool) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        transport = probe_mcp_http(
            xhs_mcp_url(),
            args.timeout,
            {"check_login_status", "search_feeds", "get_feed_detail"},
            os.environ.get("XHS_MCP_AUTH_TOKEN"),
        )
        if args.skip_upstream:
            session = {"status": "skipped", "reason": "--skip-upstream"}
            status = "degraded"
        else:
            session = xhs_login_status(argparse.Namespace(timeout=args.timeout))
            if session.get("status") != "authenticated":
                raise SourceError("xiaohongshu-mcp 已连接，但用户尚未扫码登录")
            status = "ready"
        return {
            "source_id": "xiaohongshu",
            "kind": "mcp_streamable_http",
            "required": required,
            "status": status,
            "transport": transport,
            "session": session,
            "latency_ms": round((time.monotonic() - started_at) * 1000),
        }
    except (AdapterError, OSError, RuntimeError, SourceError) as error:
        return _preflight_failure(
            "xiaohongshu", "mcp_streamable_http", required, error, started_at
        )


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    required = set(args.require or [])
    checks = [
        _amap_preflight(args, "amap-maps" in required),
        _variflight_preflight(
            args,
            "variflight_aviation",
            "variflight-aviation",
            {"getFutureWeatherByAirport", "searchFlightsByDepArr"},
            "getFutureWeatherByAirport",
            {"airport": args.airport},
            "variflight-aviation" in required,
        ),
        _variflight_preflight(
            args,
            "variflight_tripmatch",
            "variflight-tripmatch",
            {"searchTrainStations", "searchTrainTicketsByCity"},
            "searchTrainStations",
            {"query": args.city},
            "variflight-tripmatch" in required,
        ),
        _flyai_preflight(args, "flyai" in required),
        _weather_preflight(args, "open-meteo" in required),
        _xiaohongshu_preflight(args, "xiaohongshu" in required),
    ]
    required_failures = [
        check["source_id"]
        for check in checks
        if check["required"] and check["status"] != "ready"
    ]
    if required_failures:
        status = "unavailable"
    elif any(check["status"] != "ready" for check in checks):
        status = "degraded"
    else:
        status = "ready"
    return {
        "schema_version": "travel-source-preflight/v1",
        "status": status,
        "required_sources": sorted(required),
        "required_failures": required_failures,
        "checks": checks,
        "checked_at": checked_at(),
    }


def provider_query(
    args: argparse.Namespace,
    provider_id: str,
    product_type: str,
    tool: str,
    arguments: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    snapshot = adapter(provider_id).query(
        product_type=product_type,
        tool=tool,
        arguments=arguments,
        query=query,
        timeout=args.timeout,
        limit=getattr(args, "limit", None),
    )
    workspace = getattr(args, "workspace", None)
    task_id = getattr(args, "task_id", None)
    if bool(workspace) != bool(task_id):
        raise AdapterError("invalid_response", "--workspace 和 --task-id 必须同时提供")
    if workspace and task_id:
        try:
            store_source_snapshot(Path(workspace), task_id, snapshot)
        except WorkspaceError as error:
            raise AdapterError("workspace_error", f"无法写入研究 workspace：{error}") from error
    return snapshot


def flyai_flight(args: argparse.Namespace) -> dict[str, Any]:
    values = {
        "origin": args.origin,
        "destination": args.destination,
        "dep_date": args.date,
        "back_date": args.return_date,
        "journey_type": args.journey_type,
        "seat_class_name": args.seat_class,
        "max_price": args.max_price,
        "sort_type": args.sort_type,
    }
    return provider_query(args, "fliggy_flyai", "flight", "search-flight", values, values)


def provider_coverage_query(
    args: argparse.Namespace,
    handler: Any,
    product_type: str,
) -> dict[str, Any]:
    """Run the standard feasibility-first sort coverage and persist every snapshot."""
    snapshots = []
    for sort_type in TRANSPORT_COVERAGE_SORTS:
        query_args = argparse.Namespace(**vars(args))
        query_args.sort_type = sort_type
        snapshots.append(handler(query_args))
    return {
        "schema_version": "travel-source-snapshot-batch/v1",
        "status": "platform_reported",
        "product_type": product_type,
        "coverage": [
            {"sort_type": value, "purpose": TRANSPORT_SORT_LABELS[value]}
            for value in TRANSPORT_COVERAGE_SORTS
        ],
        "snapshot_ids": [snapshot["snapshot_id"] for snapshot in snapshots],
        "snapshots": snapshots,
        "checked_at": checked_at(),
        "disclaimer": "多排序查询用于覆盖时间与价格边界；结果不代表库存持续有效或已经预订。",
    }


def flyai_flight_coverage(args: argparse.Namespace) -> dict[str, Any]:
    return provider_coverage_query(args, flyai_flight, "flight")


def flyai_train(args: argparse.Namespace) -> dict[str, Any]:
    values = {
        "origin": args.origin,
        "destination": args.destination,
        "dep_date": args.date,
        "journey_type": args.journey_type,
        "seat_class_name": args.seat_class,
        "transport_no": args.train_number,
        "max_price": args.max_price,
        "sort_type": args.sort_type,
    }
    return provider_query(args, "fliggy_flyai", "train", "search-train", values, values)


def flyai_train_coverage(args: argparse.Namespace) -> dict[str, Any]:
    return provider_coverage_query(args, flyai_train, "train")


def flyai_hotel(args: argparse.Namespace) -> dict[str, Any]:
    values = {
        "dest_name": args.destination,
        "key_words": args.keywords,
        "poi_name": args.poi,
        "hotel_types": args.hotel_type,
        "sort": args.sort,
        "check_in_date": args.check_in,
        "check_out_date": args.check_out,
        "hotel_stars": args.stars,
        "hotel_bed_types": args.bed_type,
        "max_price": args.max_price,
    }
    query = {
        **values,
        "requested_occupancy": {
            "adults": getattr(args, "adults", None),
            "rooms": getattr(args, "rooms", None),
        },
        "supplier_capacity_filter_supported": False,
    }
    return provider_query(args, "fliggy_flyai", "hotel", "search-hotel", values, query)


def variflight_flight_search(args: argparse.Namespace) -> dict[str, Any]:
    arguments = {
        "depcity" if args.origin_kind == "city" else "dep": args.origin,
        "arrcity" if args.destination_kind == "city" else "arr": args.destination,
        "date": args.date,
    }
    query = {
        "origin": args.origin,
        "origin_kind": args.origin_kind,
        "destination": args.destination,
        "destination_kind": args.destination_kind,
        "date": args.date,
    }
    return provider_query(
        args, "variflight_aviation", "flight", "searchFlightsByDepArr", arguments, query
    )


def variflight_flight_number(args: argparse.Namespace) -> dict[str, Any]:
    values = {"fnum": args.flight_number, "date": args.date, "dep": args.origin, "arr": args.destination}
    return provider_query(
        args, "variflight_aviation", "flight", "searchFlightsByNumber", values, values
    )


def variflight_flight_price(args: argparse.Namespace) -> dict[str, Any]:
    arguments = {"dep_city": args.origin, "arr_city": args.destination, "dep_date": args.date}
    return provider_query(
        args, "variflight_aviation", "flight", "getFlightPriceByCities", arguments, arguments
    )


def variflight_flight_comfort(args: argparse.Namespace) -> dict[str, Any]:
    values = {"fnum": args.flight_number, "date": args.date, "dep": args.origin, "arr": args.destination}
    return provider_query(
        args, "variflight_aviation", "flight", "flightHappinessIndex", values, values
    )


def variflight_train(args: argparse.Namespace) -> dict[str, Any]:
    arguments = {"from": args.origin, "to": args.destination, "date": args.date}
    return provider_query(
        args, "variflight_tripmatch", "train", "searchTrainTicketsByCity", arguments, arguments
    )


def variflight_train_stations(args: argparse.Namespace) -> dict[str, Any]:
    arguments = {"query": args.query}
    return provider_query(
        args, "variflight_tripmatch", "train_station", "searchTrainStations", arguments, arguments
    )


def variflight_air_rail(args: argparse.Namespace) -> dict[str, Any]:
    arguments = {"depcity": args.origin, "arrcity": args.destination, "depdate": args.date}
    return provider_query(
        args,
        "variflight_tripmatch",
        "air_rail_transfer",
        "getFlightAndTrainTransferInfo",
        arguments,
        arguments,
    )


def resolve_location(name: str) -> dict[str, Any]:
    data = request_json(
        OPEN_METEO_GEOCODING,
        {"name": name, "count": 1, "language": "zh", "format": "json"},
    )
    results = data.get("results") or []
    if not results:
        raise SourceError(f"未找到地点：{name}")
    result = results[0]
    return {
        "name": result.get("name"),
        "admin1": result.get("admin1"),
        "country": result.get("country"),
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "timezone": result.get("timezone"),
    }


def weather(args: argparse.Namespace) -> dict[str, Any]:
    if args.location:
        location = resolve_location(args.location)
        latitude, longitude = location["latitude"], location["longitude"]
    else:
        if args.latitude is None or args.longitude is None:
            raise SourceError("必须提供 --location，或同时提供 --latitude 和 --longitude")
        latitude, longitude = args.latitude, args.longitude
        location = {
            "name": args.name or f"{latitude},{longitude}",
            "latitude": latitude,
            "longitude": longitude,
        }

    daily_fields = [
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "wind_speed_10m_max",
        "wind_gusts_10m_max",
        "uv_index_max",
        "sunrise",
        "sunset",
    ]
    data = request_json(
        OPEN_METEO_FORECAST,
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(daily_fields),
            "timezone": "auto",
            "forecast_days": args.days,
        },
    )
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    forecasts = []
    for index, date in enumerate(dates):
        row = {"date": date}
        for field in daily_fields:
            values = daily.get(field) or []
            row[field] = values[index] if index < len(values) else None
        row["summary"] = WEATHER_CODES.get(row["weather_code"], f'天气代码 {row["weather_code"]}')
        row["icon_code"] = weather_icon_code(row["weather_code"])
        forecasts.append(row)
    location_label = location.get("name") or f"{latitude},{longitude}"
    return {
        "status": "platform_reported",
        "provider": "Open-Meteo",
        "location": location,
        "timezone": data.get("timezone"),
        "daily_units": data.get("daily_units") or {},
        "forecasts": forecasts,
        "checked_at": checked_at(),
        "action_links": [
            {
                "type": "weather",
                "label": f"在 Windy 查看{location_label}天气",
                "provider": "Windy",
                "url": "https://www.windy.com/",
                "checked_at": checked_at(),
                "disclaimer": f"在站内定位 {latitude},{longitude}；出发前48小时复核",
            },
            {
                "type": "weather_warning",
                "label": "查看中央气象台预警",
                "provider": "中央气象台",
                "url": "https://www.nmc.cn/publish/alarm.html",
                "checked_at": checked_at(),
                "disclaimer": "中国境内预警以官方发布为准",
            },
        ],
        "sources": [
            {"title": "Open-Meteo Forecast API", "url": "https://open-meteo.com/en/docs", "kind": "weather_api"},
            {"title": "中央气象台预警", "url": "https://www.nmc.cn/publish/alarm.html", "kind": "manual_warning_check"},
        ],
        "disclaimer": "预报会变化；出发前 48 小时复核，中国境内预警以官方气象机构为准。",
    }


def amap_request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    key = get_amap_key()
    if not key:
        raise SourceError("未配置高德 Key；请设置 AMAP_API_KEY 或 AMAP_MAPS_API_KEY")
    data = request_json(f"{AMAP_API}{path}", {"key": key, **params})
    if str(data.get("status")) != "1":
        raise SourceError(f'高德 API 返回错误：{data.get("info") or "unknown"}')
    return data


def amap_place(args: argparse.Namespace) -> dict[str, Any]:
    data = amap_request(
        "/v5/place/text",
        {"keywords": args.keywords, "region": args.city, "page_size": args.limit, "show_fields": "business"},
    )
    places = []
    for poi in (data.get("pois") or [])[: args.limit]:
        name = poi.get("name")
        location = poi.get("location")
        marker_url = None
        if name and location:
            marker_url = "https://uri.amap.com/marker?" + urlencode(
                {
                    "position": location,
                    "name": name,
                    "src": "travel-planning",
                    "coordinate": "gaode",
                    "callnative": 0,
                }
            )
        places.append(
            {
                "id": poi.get("id"),
                "name": name,
                "address": poi.get("address"),
                "location": location,
                "type": poi.get("type"),
                "business": poi.get("business"),
                "map_url": marker_url,
            }
        )
    return {
        "status": "platform_reported",
        "provider": "高德开放平台",
        "query": {"keywords": args.keywords, "city": args.city},
        "places": places,
        "checked_at": checked_at(),
        "source": {"title": "高德地图 Web 服务 API", "url": "https://lbs.amap.com/api/webservice/guide/api-advanced/newpoisearch"},
        "disclaimer": "景区入口名称与开放状态仍需景区官方来源确认。",
    }


def osm_place(args: argparse.Namespace) -> dict[str, Any]:
    """Low-volume overseas place lookup through the public Nominatim endpoint."""
    data = request_json(
        NOMINATIM_SEARCH,
        {
            "q": args.query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": args.limit,
            "accept-language": args.language,
            "countrycodes": args.countrycodes,
        },
    )
    if not isinstance(data, list):
        raise SourceError("Nominatim 未返回有效地点列表")
    places = []
    for item in data[: args.limit]:
        lat, lon = item.get("lat"), item.get("lon")
        map_url = None
        if lat and lon:
            map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"
        places.append(
            {
                "osm_type": item.get("osm_type"),
                "osm_id": item.get("osm_id"),
                "name": item.get("name") or item.get("display_name"),
                "display_name": item.get("display_name"),
                "latitude": lat,
                "longitude": lon,
                "category": item.get("category"),
                "type": item.get("type"),
                "address": item.get("address") or {},
                "map_url": map_url,
            }
        )
    return {
        "status": "platform_reported",
        "provider": "Nominatim / OpenStreetMap",
        "query": {"text": args.query, "countrycodes": args.countrycodes},
        "places": places,
        "checked_at": checked_at(),
        "source": {"title": "OpenStreetMap Nominatim", "url": "https://nominatim.org/release-docs/latest/api/Search/"},
        "disclaimer": "仅用于低频地点候选检索；名称和坐标需与景区官网或地图平台交叉核对，入口开放状态以景区官方为准。",
    }


def route_options(mode: str, data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    route = data.get("route") or {}
    raw_options = route.get("transits") if mode == "transit" else route.get("paths")
    options = []
    for item in (raw_options or [])[:limit]:
        option = {
            "distance_meters": item.get("distance"),
            "duration_seconds": item.get("duration"),
        }
        if mode == "transit":
            option.update(
                {
                    "cost": item.get("cost"),
                    "walking_distance_meters": item.get("walking_distance"),
                    "nightflag": item.get("nightflag"),
                    "segments": item.get("segments") or [],
                }
            )
        else:
            option.update(
                {
                    "strategy": item.get("strategy"),
                    "tolls": item.get("tolls"),
                    "steps": [
                        {
                            "instruction": step.get("instruction"),
                            "road": step.get("road"),
                            "distance_meters": step.get("distance"),
                            "duration_seconds": step.get("duration"),
                        }
                        for step in item.get("steps") or []
                    ],
                }
            )
        options.append(option)
    return options


def amap_route(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode == "transit" and not args.city:
        raise SourceError("公交/地铁路线必须提供 --city（城市名或 citycode）")
    path = {
        "walking": "/v3/direction/walking",
        "driving": "/v3/direction/driving",
        "transit": "/v3/direction/transit/integrated",
    }[args.mode]
    data = amap_request(
        path,
        {"origin": args.origin, "destination": args.destination, "city": args.city, "extensions": "all"},
    )
    navigation_url = "https://uri.amap.com/navigation?" + urlencode(
        {
            "from": f"{args.origin},起点",
            "to": f"{args.destination},终点",
            "mode": {"walking": "walk", "driving": "car", "transit": "bus"}[args.mode],
            "policy": 0,
            "src": "travel-planning",
            "callnative": 0,
        }
    )
    return {
        "status": "platform_reported",
        "provider": "高德开放平台",
        "query": {
            "mode": args.mode,
            "origin": args.origin,
            "destination": args.destination,
            "city": args.city,
        },
        "options": route_options(args.mode, data, args.limit),
        "navigation_url": navigation_url,
        "checked_at": checked_at(),
        "source": {"title": "高德路径规划 API", "url": AMAP_DOCS},
        "disclaimer": "时间是平台查询时估算；出发时用实时导航复核。",
    }


def manual_link(label: str, url: str, provider: str, disclaimer: str) -> dict[str, Any]:
    return {
        "type": "source",
        "label": label,
        "provider": provider,
        "url": url,
        "checked_at": checked_at(),
        "disclaimer": disclaimer,
        "manual_required": True,
    }


def fallback(args: argparse.Namespace) -> dict[str, Any]:
    conditions = {
        "date": args.date,
        "origin": args.origin,
        "destination": args.destination,
        "city": args.city,
        "keywords": args.keywords,
        "travelers": args.travelers,
        "fields": args.fields,
    }
    summary = "、".join(str(value) for value in conditions.values() if value)
    links: list[dict[str, Any]] = []
    if args.kind == "train":
        label = f"在 12306 查询：{args.origin or '出发站'} → {args.destination or '到达站'}"
        if args.date:
            label += f"·{args.date}"
        links.append(manual_link(label, "https://www.12306.cn/index/", "12306", f"核对车次、时刻、席别价格和查询时余票；{args.recheck}"))
    elif args.kind == "ctrip":
        product = args.product or "旅行产品"
        links.append(manual_link(f"在携程查询{product}：{summary or '请填写查询条件'}", "https://www.ctrip.com/", "携程", f"库存与价格以平台当时显示为准；{args.recheck}"))
    elif args.kind == "map":
        query = args.keywords or args.destination or args.city or "目的地"
        if args.map_provider == "google":
            url = "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query})
            links.append(manual_link(f"在 Google Maps 查询：{summary or query}", url, "Google Maps", f"复核入口、路线和实时耗时；{args.recheck}"))
        else:
            url = "https://uri.amap.com/search?" + urlencode(
                {"keyword": query, "city": args.city or "", "src": "travel-planning", "callnative": 0}
            )
            links.append(manual_link(f"在高德地图查询：{summary or query}", url, "高德地图", f"复核入口、路线和实时耗时；{args.recheck}"))
    elif args.kind == "weather":
        links.append(manual_link(f"在中国天气网查询：{summary or '目的地与日期'}", "https://www.weather.com.cn/", "中国天气网", f"复核预报、降雨和紫外线；{args.recheck}"))
        links.append(manual_link("查看中央气象台当前预警", "https://www.nmc.cn/publish/alarm.html", "中央气象台", f"确认是否存在有效预警；{args.recheck}"))
    elif args.kind == "attraction":
        if not args.url:
            raise SourceError("景区手动复核必须提供已定位的官方 --url，不能猜测首页或深链")
        links.append(manual_link(f"查看景区官方信息：{summary or args.keywords or '开放与票务'}", args.url, "景区官方", f"核对门票、开放/停止入场、预约、入口和临时公告；{args.recheck}"))
    elif args.kind == "xiaohongshu":
        query = args.keywords or args.destination or args.city or "目的地 当季 入口 避坑"
        links.append(manual_link(f"在小红书搜索：{query}", "https://www.xiaohongshu.com/explore", "小红书", f"需登录后输入该检索词；社区经验须与官方来源交叉核验；{args.recheck}"))
    return {
        "status": "to_recheck",
        "kind": args.kind,
        "query_conditions": {key: value for key, value in conditions.items() if value},
        "action_links": links,
        "checked_at": checked_at(),
    }


def iso_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期必须是 YYYY-MM-DD") from error
    return value


def iata_code(value: str) -> str:
    code = value.upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise argparse.ArgumentTypeError("IATA 代码必须是 3 个英文字母")
    return code


def flight_number(value: str) -> str:
    number = value.upper()
    if not re.fullmatch(r"[A-Z0-9]{2,3}[0-9]{1,4}", number):
        raise argparse.ArgumentTypeError("航班号格式无效，例如 MU2157")
    return number


def add_external_query_options(command: argparse.ArgumentParser, default_limit: int = 10) -> None:
    command.add_argument("--limit", type=int, default=default_limit, choices=range(1, 51), metavar="1-50")
    command.add_argument("--timeout", type=int, default=45, choices=range(5, 181), metavar="5-180")
    command.add_argument(
        "--consent-external-data",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    command.add_argument("--workspace", help="可选：将标准快照直接写入本次研究 workspace")
    command.add_argument("--task-id", help="与 --workspace 同时使用；必须是已分配的 route-data 或 stay-food 任务")


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return number


def add_flyai_flight_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--origin", required=True, help="出发城市或机场")
    command.add_argument("--destination", required=True, help="到达城市或机场")
    command.add_argument("--date", required=True, type=iso_date)
    command.add_argument("--return-date", type=iso_date)
    command.add_argument("--journey-type", type=int, choices=[1, 2], default=1, help="1 直达，2 中转")
    command.add_argument("--seat-class")
    command.add_argument("--max-price", type=float)
    command.add_argument("--sort-type", type=int, choices=range(1, 9), default=2)
    add_external_query_options(command)


def add_flyai_train_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--origin", required=True, help="出发城市或车站")
    command.add_argument("--destination", required=True, help="到达城市或车站")
    command.add_argument("--date", required=True, type=iso_date)
    command.add_argument("--journey-type", type=int, choices=[1, 2], default=1, help="1 直达，2 中转")
    command.add_argument("--seat-class")
    command.add_argument("--train-number")
    command.add_argument("--max-price", type=float)
    command.add_argument("--sort-type", type=int, choices=range(1, 9), default=2)
    add_external_query_options(command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    command = subparsers.add_parser("capabilities", help="检查当前可用的数据源")
    command.set_defaults(handler=capabilities)

    command = subparsers.add_parser(
        "preflight",
        help="真实探测 MCP、供应商 API、天气与小红书运行态",
    )
    command.add_argument(
        "--require",
        action="append",
        choices=PREFLIGHT_SOURCES,
        help="本次行程必须可用的数据源；可重复传入，失败时命令返回非零",
    )
    command.add_argument("--city", default="北京", help="只读 smoke query 使用的城市")
    command.add_argument("--airport", default="PEK", type=iata_code, help="航空 smoke query 使用的机场 IATA 码")
    command.add_argument("--timeout", type=int, default=30, choices=range(5, 181), metavar="5-180")
    command.add_argument(
        "--skip-upstream",
        action="store_true",
        help="只检查本地运行时和 MCP 握手，不访问供应商上游；结果记为 degraded",
    )
    command.set_defaults(handler=preflight)

    command = subparsers.add_parser("weather", help="查询近期天气、降雨、紫外线和日出日落")
    command.add_argument("--location", help="城市或地点名")
    command.add_argument("--latitude", type=float)
    command.add_argument("--longitude", type=float)
    command.add_argument("--name", help="坐标对应的显示名称")
    command.add_argument("--days", type=int, default=7, choices=range(1, 17), metavar="1-16")
    command.set_defaults(handler=weather)

    command = subparsers.add_parser("xhs-health", help="检查本机小红书 HTTP MCP 协议和工具契约")
    command.set_defaults(handler=xhs_health)

    command = subparsers.add_parser("xhs-login-status", help="检查小红书本机登录态")
    command.set_defaults(handler=xhs_login_status)

    command = subparsers.add_parser("xhs-search", help="搜索小红书公开笔记并脱敏输出")
    command.add_argument("--keyword", required=True)
    command.add_argument("--sort-by", choices=["relevance", "latest", "most_liked", "most_commented", "most_collected"], default="relevance")
    command.add_argument("--note-type", choices=["all", "video", "image"], default="all")
    command.add_argument("--publish-time", choices=["all", "day", "week", "half_year"], default="half_year")
    command.add_argument("--search-scope", choices=["all", "viewed", "unviewed", "following"], default="all")
    command.add_argument("--location", choices=["all", "same_city", "nearby"], default="all")
    command.add_argument("--limit", type=int, default=10, choices=range(1, 21), metavar="1-20")
    command.set_defaults(handler=xhs_search)

    command = subparsers.add_parser("xhs-detail", help="读取已搜索到的小红书笔记详情")
    command.add_argument("--note-id", required=True)
    command.set_defaults(handler=xhs_detail)

    command = subparsers.add_parser("amap-place", help="查询高德 POI 或景区入口")
    command.add_argument("--keywords", required=True)
    command.add_argument("--city", required=True)
    command.add_argument("--limit", type=int, default=5, choices=range(1, 26), metavar="1-25")
    command.set_defaults(handler=amap_place)

    command = subparsers.add_parser("osm-place", help="通过 OpenStreetMap 查询境外地点或入口候选")
    command.add_argument("--query", required=True, help="尽量包含当地语言名称、城市和国家")
    command.add_argument("--countrycodes", help="可选 ISO 3166-1 alpha-2 国家码，如 jp、fr")
    command.add_argument("--language", default="zh-CN,en")
    command.add_argument("--limit", type=int, default=3, choices=range(1, 6), metavar="1-5")
    command.set_defaults(handler=osm_place)

    command = subparsers.add_parser("amap-route", help="查询高德步行、公交/地铁或驾车路线")
    command.add_argument("--origin", required=True, help="起点经纬度，lon,lat")
    command.add_argument("--destination", required=True, help="终点经纬度，lon,lat")
    command.add_argument("--mode", choices=["walking", "transit", "driving"], required=True)
    command.add_argument("--city", help="城市名或 citycode；公交/地铁必填")
    command.add_argument("--limit", type=int, default=3, choices=range(1, 6), metavar="1-5")
    command.set_defaults(handler=amap_route)

    command = subparsers.add_parser("flyai-flight", help="通过飞猪 FlyAI 查询航班候选")
    add_flyai_flight_options(command)
    command.set_defaults(handler=flyai_flight)

    command = subparsers.add_parser(
        "flyai-flight-coverage",
        help="按最早、最晚、时长、价格和推荐排序查询航班可行性边界",
    )
    add_flyai_flight_options(command)
    command.set_defaults(handler=flyai_flight_coverage)

    command = subparsers.add_parser("flyai-train", help="通过飞猪 FlyAI 查询火车候选")
    add_flyai_train_options(command)
    command.set_defaults(handler=flyai_train)

    command = subparsers.add_parser(
        "flyai-train-coverage",
        help="按最早、最晚、时长、价格和推荐排序查询火车可行性边界",
    )
    add_flyai_train_options(command)
    command.set_defaults(handler=flyai_train_coverage)

    command = subparsers.add_parser("flyai-hotel", help="通过飞猪 FlyAI 查询酒店候选")
    command.add_argument("--destination", required=True, help="国家、省、市或区")
    command.add_argument("--check-in", required=True, type=iso_date)
    command.add_argument("--check-out", required=True, type=iso_date)
    command.add_argument("--keywords")
    command.add_argument("--poi", help="附近景点或地标")
    command.add_argument("--hotel-type", choices=["酒店", "民宿", "客栈"])
    command.add_argument("--stars", help="逗号分隔星级，例如 4,5")
    command.add_argument("--bed-type", choices=["大床房", "双床房", "多床房"])
    command.add_argument("--adults", type=positive_int, help="本次入住成人数；用于记录需求，不代表供应商已按人数校验库存")
    command.add_argument("--rooms", type=positive_int, help="本次所需房间数；用于记录需求，不代表供应商已确认多间同房型库存")
    command.add_argument("--max-price", type=float)
    command.add_argument("--sort", choices=["distance_asc", "rate_desc", "price_asc", "price_desc", "no_rank"], default="no_rank")
    add_external_query_options(command)
    command.set_defaults(handler=flyai_hotel)

    command = subparsers.add_parser("variflight-flight", help="通过飞常准 Aviation MCP 查询航班运行候选")
    command.add_argument("--origin", required=True, type=iata_code)
    command.add_argument("--origin-kind", choices=["city", "airport"], default="city")
    command.add_argument("--destination", required=True, type=iata_code)
    command.add_argument("--destination-kind", choices=["city", "airport"], default="city")
    command.add_argument("--date", required=True, type=iso_date)
    add_external_query_options(command)
    command.set_defaults(handler=variflight_flight_search)

    command = subparsers.add_parser("variflight-flight-number", help="通过飞常准查询指定航班")
    command.add_argument("--flight-number", required=True, type=flight_number)
    command.add_argument("--date", required=True, type=iso_date)
    command.add_argument("--origin", type=iata_code, help="可选出发机场 IATA 代码")
    command.add_argument("--destination", type=iata_code, help="可选到达机场 IATA 代码")
    add_external_query_options(command)
    command.set_defaults(handler=variflight_flight_number)

    command = subparsers.add_parser("variflight-flight-price", help="通过飞常准查询城市间舱位价格")
    command.add_argument("--origin", required=True, type=iata_code, help="出发城市 IATA 代码")
    command.add_argument("--destination", required=True, type=iata_code, help="到达城市 IATA 代码")
    command.add_argument("--date", required=True, type=iso_date)
    add_external_query_options(command)
    command.set_defaults(handler=variflight_flight_price)

    command = subparsers.add_parser("variflight-flight-comfort", help="通过飞常准查询指定航班舒适度与准点等信息")
    command.add_argument("--flight-number", required=True, type=flight_number)
    command.add_argument("--date", required=True, type=iso_date)
    command.add_argument("--origin", type=iata_code, help="可选出发机场 IATA 代码")
    command.add_argument("--destination", type=iata_code, help="可选到达机场 IATA 代码")
    add_external_query_options(command)
    command.set_defaults(handler=variflight_flight_comfort)

    command = subparsers.add_parser("variflight-train", help="通过飞常准 Tripmatch MCP 查询火车票候选")
    command.add_argument("--origin", required=True, help="出发城市")
    command.add_argument("--destination", required=True, help="到达城市")
    command.add_argument("--date", required=True, type=iso_date)
    add_external_query_options(command)
    command.set_defaults(handler=variflight_train)

    command = subparsers.add_parser("variflight-train-stations", help="通过飞常准 Tripmatch MCP 检索车站")
    command.add_argument("--query", required=True)
    add_external_query_options(command)
    command.set_defaults(handler=variflight_train_stations)

    command = subparsers.add_parser("variflight-air-rail", help="通过飞常准 Tripmatch MCP 查询空铁联运候选")
    command.add_argument("--origin", required=True, type=iata_code, help="出发城市 IATA 代码")
    command.add_argument("--destination", required=True, type=iata_code, help="到达城市 IATA 代码")
    command.add_argument("--date", required=True, type=iso_date)
    add_external_query_options(command)
    command.set_defaults(handler=variflight_air_rail)

    command = subparsers.add_parser("fallback", help="生成用户可手动查询的 action_links")
    command.add_argument("--kind", choices=["attraction", "train", "ctrip", "map", "weather", "xiaohongshu"], required=True)
    command.add_argument("--date")
    command.add_argument("--origin")
    command.add_argument("--destination")
    command.add_argument("--city")
    command.add_argument("--keywords")
    command.add_argument("--travelers")
    command.add_argument("--fields")
    command.add_argument("--product", help="携程产品类型，例如酒店/航班/大巴/门票/餐厅")
    command.add_argument("--map-provider", choices=["amap", "google"], default="amap", help="地图手动入口；中国境内默认高德，境外可选 Google")
    command.add_argument("--url", help="已核验的景区官方 HTTPS 地址")
    command.add_argument("--recheck", default="建议出发前再次复核")
    command.set_defaults(handler=fallback)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = args.handler(args)
        output(payload)
        if args.command == "preflight" and payload.get("status") == "unavailable":
            return 2
        return 0
    except AdapterError as error:
        output(
            {
                "schema_version": "travel-source-error/v1",
                "status": "error",
                "failure_kind": error.failure_kind,
                "message": str(error),
                "checked_at": checked_at(),
            }
        )
        return 2
    except SourceError as error:
        output({"status": "error", "message": str(error), "checked_at": checked_at()})
        return 2


if __name__ == "__main__":
    sys.exit(main())
