#!/usr/bin/env python3
"""Assemble a researched trip from a declarative itinerary-plan/v1 document."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ALLOWED_ACTION_TYPES = {
    "map", "official", "official_homepage", "official_notice", "official_booking", "official_wechat",
    "weather", "weather_warning", "ticket", "train", "bus", "hotel",
    "restaurant", "guide", "image_source", "source",
}
ACTION_ALIASES = {
    "airline": "official", "flight": "source", "rail": "train",
    "railway": "train", "transport": "source", "hotel_quote": "hotel",
    "travel_platform": "source", "booking_platform": "source",
}
OUTPUT_COLLECTIONS = (
    "readiness", "attractions", "transport_edges", "intercity_options",
    "vehicles", "road_trip_plans", "rental_options", "parking_locations",
    "lodging_options", "restaurants", "restaurant_snapshots",
    "meal_baseline_routes", "meal_route_evaluations", "meal_options", "weather",
)


class AssemblyError(ValueError):
    """Raised when a plan cannot be assembled safely."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssemblyError(f"缺少装配输入：{path}") from exc
    except json.JSONDecodeError as exc:
        raise AssemblyError(f"JSON 无效：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AssemblyError(f"JSON 顶层必须是对象：{path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split(".") if path else []:
        if not isinstance(current, dict) or part not in current:
            raise AssemblyError(f"装配路径不存在：{path}")
        current = current[part]
    return current


def indexed(items: list[dict[str, Any]], key: str = "id") -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = str(item.get(key) or "")
        if not item_id:
            raise AssemblyError(f"集合元素缺少 {key}")
        if item_id in result:
            raise AssemblyError(f"集合存在重复 {key}：{item_id}")
        result[item_id] = item
    return result


def normalize_actions(
    items: list[dict[str, Any]], default_type: str, default_provider: str,
    disclaimer: str, checked_at: str,
) -> list[dict[str, Any]]:
    result = []
    for item in items or []:
        if not isinstance(item, dict) or not str(item.get("url") or "").startswith("https://"):
            continue
        action_type = ACTION_ALIASES.get(
            str(item.get("type") or default_type), str(item.get("type") or default_type)
        )
        if action_type not in ALLOWED_ACTION_TYPES:
            action_type = "source"
        result.append({
            **item,
            "type": action_type,
            "provider": item.get("provider") or default_provider,
            "checked_at": item.get("checked_at") or checked_at,
            "disclaimer": item.get("disclaimer") or disclaimer,
        })
    return result


def money(value: Any) -> str:
    return "待官方核验" if value is None else f"¥{value}"


def normalize_cost(item: dict[str, Any]) -> dict[str, Any]:
    role = str(item.get("pricing_role") or "optional")
    return {
        "name": item.get("name"),
        "kind": item.get("kind") or ("base_ticket" if role == "baseline" else "optional_experience"),
        "unit_price": money(item.get("unit_price_cny")),
        "quantity": item.get("quantity", 1),
        "subtotal": money(item.get("subtotal_cny")),
        "pricing_role": "baseline" if role == "baseline" else ("alternative" if role == "alternative" else "optional"),
        "required": role == "baseline",
        "status": item.get("status") or "to_recheck",
        "source_ids": item.get("source_ids") or [],
    }


def normalize_route(item: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(item)
    cost = result.get("cost")
    if isinstance(cost, dict):
        if cost.get("amount_yuan_for_4") is not None:
            result["cost"] = f"4人约 {cost['amount_yuan_for_4']} 元（{cost.get('status', '估算')}）"
        elif cost.get("amount_yuan_per_person") is not None:
            result["cost"] = f"约 {cost['amount_yuan_per_person']} 元/人（{cost.get('status', '估算')}）"
        else:
            result["cost"] = "待实时查询"
    result["reason"] = result.get("reason") or "承接相邻行程并减少折返"
    map_route = result.get("map_route") or {}
    if map_route.get("mode") == "transit":
        map_route["mode"] = "bus"
    if map_route:
        map_route["assumption"] = map_route.get("assumption") or defaults["map_assumption"]
        result["map_route"] = map_route
    result["action_links"] = normalize_actions(
        result.get("action_links") or [], "map", defaults["map_provider"],
        defaults["route_disclaimer"], defaults["checked_at"],
    )
    return result


def normalize_intercity(item: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(item)
    result["action_links"] = normalize_actions(
        result.get("action_links") or [], "source", defaults["transport_provider"],
        defaults["transport_disclaimer"], defaults["checked_at"],
    )
    cost = result.get("cost")
    if isinstance(cost, dict):
        if cost.get("amount_yuan_for_4") is not None:
            result["cost"] = f"4人{cost['amount_yuan_for_4']}（{cost.get('status', '待复核')}）"
        elif cost.get("amount_yuan_per_adult") is not None:
            result["cost"] = f"约¥{cost['amount_yuan_per_adult']}/人（{cost.get('status', '待复核')}）"
        else:
            result["cost"] = str(cost.get("fare") or "未取得可用实时价格，出发前重新查询")
    mode = str(result.get("mode") or "").casefold()
    if ("train" in mode or "rail" in mode or "高铁" in mode or "铁路" in mode) and not result.get("rail_verification"):
        result["country_code"] = result.get("country_code") or defaults["country_code"]
        if result["country_code"] == "CN":
            result["rail_verification"] = {
                "channel": "12306", "status": "to_recheck", "checked_at": defaults["checked_at"],
                "action_link": {
                    "type": "train", "label": "铁路12306最终复核", "provider": "铁路12306",
                    "url": "https://www.12306.cn/",
                },
            }
    return result


def normalize_lodging(item: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(item)
    quote = result.get("quote") or {}
    result["area"] = item.get("area_anchor") or item.get("district")
    result["price"] = (
        f"快照约¥{quote.get('amount_per_room_per_night_cny')}/间夜；"
        f"2间2晚约¥{quote.get('two_rooms_two_nights_estimate_cny')}"
        if quote.get("amount_per_room_per_night_cny") is not None else "待重新查询"
    )
    result["luggage_storage"] = (item.get("luggage_storage") or {}).get("policy") or "入住前确认"
    location = item.get("location") or {}
    result["location_verification"] = {
        "status": "verified", "checked_at": location.get("poi_verified_at") or defaults["checked_at"],
        "method": defaults["location_verification_method"], "source_ids": item.get("source_ids") or [],
    }
    result["action_links"] = normalize_actions(
        item.get("action_links") or [], "hotel", defaults["hotel_provider"],
        defaults["hotel_disclaimer"], defaults["checked_at"],
    )
    return result


def normalize_attraction(item: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(item)
    reservation = result.get("reservation") or {}
    official = result.get("official") or {}
    if reservation.get("required") is False:
        official["booking_status"] = "not_applicable"
        official["booking_url"] = None
    result["official"] = official
    result["area"] = official.get("physical_address")
    result["visit_duration"] = "按当日事件时间窗执行"
    url = official.get("homepage_url") or official.get("notice_url")
    result["action_links"] = [{
        "type": "official", "label": f"查看{result.get('name')}官方信息",
        "provider": defaults["attraction_provider"], "url": url,
        "checked_at": defaults["checked_at"], "disclaimer": defaults["attraction_disclaimer"],
    }] if str(url or "").startswith("https://") else []
    return result


def hm(value: str) -> int:
    try:
        hour, minute = (int(part) for part in value.split(":"))
    except (TypeError, ValueError) as exc:
        raise AssemblyError(f"时间必须是 HH:MM：{value}") from exc
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise AssemblyError(f"时间超出范围：{value}")
    return hour * 60 + minute


def time_text(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def build_attraction_event(
    attraction: dict[str, Any], config: dict[str, Any], defaults: dict[str, Any]
) -> dict[str, Any]:
    start, end = hm(str(config["start"])), hm(str(config["end"]))
    if end <= start:
        raise AssemblyError(f"景点事件结束时间必须晚于开始时间：{attraction['id']}")
    blueprint = deepcopy(attraction.get("checkpoint_blueprint") or [])
    checkpoint_order = config.get("checkpoint_order")
    if checkpoint_order:
        points = indexed(blueprint)
        missing = [item_id for item_id in checkpoint_order if item_id not in points]
        if missing:
            raise AssemblyError(f"景点 checkpoint 不存在：{attraction['id']}: {missing}")
        blueprint = [points[item_id] for item_id in checkpoint_order]
    overrides = config.get("checkpoint_overrides") or {}
    step = max(10, (end - start) // max(1, len(blueprint)))
    checkpoints = []
    for index, source in enumerate(blueprint, start=1):
        point = deep_merge(source, overrides.get(str(source.get("id")), {}))
        point_start = min(end - 5, start + (index - 1) * step)
        point_end = min(end, point_start + step)
        checkpoint = {
            "id": f"cp-{attraction['id']}-{index}", "order": index,
            "time": time_text(point_start), "end_time": time_text(point_end),
            "kind": point.get("kind") or ("entry" if index == 1 else ("exit" if index == len(blueprint) else "visit")),
            "name": point.get("name") or f"节点{index}", "required": point.get("required", True),
            "instruction": point.get("instruction") or point.get("action") or defaults["checkpoint_instruction"],
            "move_from_previous": point.get("move_from_previous") or {
                "mode": "步行/景区官方接驳", "duration": "按现场客流",
            },
            "source_ids": point.get("source_ids") or attraction.get("source_ids") or [],
        }
        if point.get("narration"):
            checkpoint["narration"] = point["narration"]
        checkpoints.append(checkpoint)
    reservation = attraction.get("reservation") or {}
    official = attraction.get("official") or {}
    wechat = official.get("wechat") or {}
    operation = attraction.get("operations") or {}
    entry = deep_merge(attraction.get("entrance") or {}, config.get("entry") or {})
    exit_point = deep_merge(attraction.get("exit") or {}, config.get("exit") or {})
    action_url = official.get("booking_url") or wechat.get("guide_url") or official.get("homepage_url")
    result = {
        "id": config["event_id"], "time": config["start"], "end_time": config["end"],
        "type": "attraction", "attraction_id": attraction["id"], "title": config["title"],
        "subtitle": config.get("subtitle") or defaults["attraction_subtitle"],
        "duration": f"约{end - start}分钟", "area": attraction.get("area"),
        "reservation_required": bool(reservation.get("required")), "weather_id": config["weather_id"],
        "admission": {
            "opening_hours": operation.get("opening_hours") or "待官方复核",
            "last_entry": operation.get("last_entry") or "待官方复核",
            "reservation_method": reservation.get("action") or "按官方公告核验",
            "entry_requirement": entry.get("arrival_instruction") or defaults["entry_requirement"],
            "notice": operation.get("temporary_notice") or defaults["temporary_notice"],
        },
        "execution": {
            "entry": {"name": entry.get("name"), "location_query": entry.get("location_query"),
                      "reason": entry.get("arrival_instruction") or "与当天顺向路线衔接"},
            "exit": {"name": exit_point.get("name"),
                     "location_query": exit_point.get("location_query") or entry.get("location_query")},
            "checkpoints": checkpoints, "leave_by": config["end"],
            "fallback": config.get("fallback") or exit_point.get("departure_instruction")
                        or reservation.get("fallback") or defaults["attraction_fallback"],
        },
        "booking_task_ids": [f"book-{attraction['id']}"] if reservation.get("required") else [],
        "cost_items": [normalize_cost(item) for item in attraction.get("cost_items") or []],
        "cost_summary": config.get("cost_summary") or defaults["cost_summary"],
        "preparation": config.get("preparation") or defaults["preparation"],
        "action_links": [{
            "type": "official", "label": "打开官方入口", "provider": attraction["name"],
            "url": action_url, "checked_at": defaults["checked_at"],
            "disclaimer": defaults["attraction_event_disclaimer"],
        }] if str(action_url or "").startswith("https://") else [],
    }
    return deep_merge(result, config.get("overrides") or {})


def build_booking_task(
    attraction: dict[str, Any], event: dict[str, Any], defaults: dict[str, Any]
) -> dict[str, Any]:
    reservation = attraction.get("reservation") or {}
    official = attraction.get("official") or {}
    wechat = official.get("wechat") or {}
    link = (
        reservation.get("booking_url") or official.get("booking_url")
        or wechat.get("guide_url") or official.get("notice_url")
    )
    link_type = "official_notice"
    if reservation.get("booking_url") or official.get("booking_url"):
        link_type = "official_booking"
    elif wechat.get("guide_url"):
        link_type = "official_wechat"
    return {
        "id": f"book-{attraction['id']}", "title": f"核验并完成{attraction['name']}预约",
        "product": defaults["booking_product"], "quantity": defaults["booking_quantity"],
        "next_action_at": reservation.get("next_action_at"),
        "deadline": reservation.get("next_action_at") or "出发前完成",
        "priority": "book_now" if reservation.get("required") else "recheck_later",
        "status": reservation.get("status") or "pending", "target_date": reservation.get("target_date"),
        "target_session": event["time"], "action": reservation.get("action") or "查看开放和限流公告",
        "event_id": event["id"], "attraction_id": attraction["id"],
        "action_links": [{
            "type": link_type,
            "label": "打开公众号预约说明" if link_type == "official_wechat" else "打开官方预约/公告",
            "provider": attraction["name"], "url": link,
            "checked_at": defaults["checked_at"], "disclaimer": defaults["booking_disclaimer"],
        }] if str(link or "").startswith("https://") else [],
    }


def default_settings(plan: dict[str, Any]) -> dict[str, Any]:
    trip = plan.get("trip") or {}
    values = {
        "checked_at": str(trip.get("updated_at") or ""), "country_code": "CN",
        "map_provider": "地图服务", "transport_provider": "交通查询平台",
        "hotel_provider": "住宿平台/地图", "attraction_provider": "景区官方/政府",
        "map_assumption": "以当前片区锚点计算；精确上下车点确定后重算",
        "route_disclaimer": "路况会变化，出发时按实时导航复核",
        "transport_disclaimer": "价格、库存与运行状态以最终平台为准",
        "hotel_disclaimer": "房态、含税总价、房型和取消规则以预订页为准",
        "restaurant_disclaimer": "营业、排队和菜单以到店前复核为准",
        "restaurant_snapshot_disclaimer": "动态信息以复核时为准",
        "weather_disclaimer": "按计划中的复核时间再次查询",
        "attraction_disclaimer": "临近出发再次查看专项公告",
        "attraction_event_disclaimer": "临近出发再次查看专项公告",
        "booking_disclaimer": "仅以官方渠道显示的适用日期、票种和时段为准",
        "location_verification_method": "地图POI全名、城市/行政区、完整地址与坐标交叉核验",
        "checkpoint_instruction": "按现场开放、导流和安全要求完成该节点。",
        "attraction_subtitle": "预约、天气与现场导流均为硬约束；不为打卡压缩下一段缓冲。",
        "entry_requirement": "携带本人有效证件，按预约时段入场",
        "temporary_notice": "临时公告发布后覆盖常规规则",
        "attraction_fallback": "限流、天气或体力不适时提前离场",
        "cost_summary": "基础票按旅行人数计；可选项目不计入基线。",
        "preparation": ["有效身份证件", "防滑鞋", "轻便雨具", "饮水和充电宝"],
        "booking_product": "实名票/时段", "booking_quantity": str(trip.get("travelers") or "按旅行人数"),
    }
    return deep_merge(values, plan.get("defaults") or {})


def load_collections(
    workspace: Path, plan: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    collections: dict[str, list[dict[str, Any]]] = {}
    task_results: dict[str, dict[str, Any]] = {}
    for name, binding in (plan.get("collections") or {}).items():
        if not isinstance(binding, dict):
            raise AssemblyError(f"collections.{name} 必须是对象")
        if binding.get("task"):
            task_id = str(binding["task"])
            payload = task_results.setdefault(task_id, read_json(workspace / "results" / f"{task_id}.json"))
        elif binding.get("file"):
            payload = read_json(workspace / str(binding["file"]))
        else:
            raise AssemblyError(f"collections.{name} 必须声明 task 或 file")
        raw = get_path(payload, str(binding.get("path") or ""))
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise AssemblyError(f"collections.{name} 指向的值必须是对象数组")
        items = deepcopy(raw)
        if binding.get("ids") is not None:
            source = indexed(items, str(binding.get("id_key") or "id"))
            missing = [item_id for item_id in binding["ids"] if str(item_id) not in source]
            if missing:
                raise AssemblyError(f"collections.{name} 缺少选定实体：{missing}")
            items = [source[str(item_id)] for item_id in binding["ids"]]
        patch_key = str(binding.get("id_key") or "id")
        patches = binding.get("patches") or {}
        items = [deep_merge(item, patches.get(str(item.get(patch_key)), {})) for item in items]
        append = binding.get("append") or []
        if not isinstance(append, list) or not all(isinstance(item, dict) for item in append):
            raise AssemblyError(f"collections.{name}.append 必须是对象数组")
        collections[name] = items + deepcopy(append)
    return collections, task_results


def load_source_snapshots(workspace: Path, task_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for task_id, result in task_results.items():
        for snapshot_id in result.get("source_snapshot_ids") or []:
            snapshot = read_json(workspace / "snapshots" / task_id / f"{snapshot_id}.json")
            if snapshot_id in snapshots and snapshots[snapshot_id] != snapshot:
                raise AssemblyError(f"动态快照 ID 冲突：{snapshot_id}")
            snapshots[str(snapshot_id)] = snapshot
    return list(snapshots.values())


def collect_sources(workspace: Path, allowed_ids: list[str] | None = None) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for path in sorted((workspace / "sources").glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AssemblyError(f"来源 JSONL 无效：{path}:{line_number}") from exc
            url = str(item.get("url") or "")
            if url.startswith("https://"):
                source_id = str(item.get("id") or "")
                if not source_id:
                    raise AssemblyError(f"来源缺少 id：{path}:{line_number}")
                merged[source_id] = {
                    "id": source_id, "title": item.get("title") or source_id, "url": url,
                    "note": item.get("summary") or f"{item.get('authority', '')} · {item.get('kind', '')}",
                    "checked_at": item.get("checked_at"),
                    **({"provider_poi_ids": item["provider_poi_ids"]} if item.get("provider_poi_ids") else {}),
                    **({"kind": item["kind"]} if item.get("kind") else {}),
                    **({"provider": item["provider"]} if item.get("provider") else {}),
                }
    if allowed_ids is None:
        return list(merged.values())
    missing = [source_id for source_id in allowed_ids if source_id not in merged]
    if missing:
        raise AssemblyError(f"来源白名单包含未登记 ID：{missing}")
    return [merged[source_id] for source_id in allowed_ids]


def normalize_collections(
    collections: dict[str, list[dict[str, Any]]], defaults: dict[str, Any],
    plan: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    output = deepcopy(collections)
    output["attractions"] = [normalize_attraction(item, defaults) for item in collections.get("attractions", [])]
    output["transport_edges"] = [normalize_route(item, defaults) for item in collections.get("transport_edges", [])]
    output["intercity_options"] = [normalize_intercity(item, defaults) for item in collections.get("intercity_options", [])]
    output["lodging_options"] = [normalize_lodging(item, defaults) for item in collections.get("lodging_options", [])]
    for name, action_type, provider, disclaimer in (
        ("readiness", "official", "官方/查询平台", "按任务说明复核"),
        ("restaurants", "restaurant", "地图服务", defaults["restaurant_disclaimer"]),
        ("restaurant_snapshots", "restaurant", "地图服务/社区", defaults["restaurant_snapshot_disclaimer"]),
        ("weather", "weather", "天气服务", defaults["weather_disclaimer"]),
    ):
        output[name] = []
        for item in collections.get(name, []):
            normalized = deepcopy(item)
            normalized["action_links"] = normalize_actions(
                item.get("action_links") or [], action_type, provider, disclaimer, defaults["checked_at"]
            )
            output[name].append(normalized)

    attraction_map = indexed(output.get("attractions", []))
    attraction_events: dict[str, dict[str, Any]] = {}
    for attraction_id, config in (plan.get("attraction_events") or {}).items():
        if attraction_id not in attraction_map:
            raise AssemblyError(f"行程引用了未选定景点：{attraction_id}")
        attraction_events[attraction_id] = build_attraction_event(attraction_map[attraction_id], config, defaults)

    restaurants = indexed(output.get("restaurants", []))
    snapshots = indexed(output.get("restaurant_snapshots", []), "snapshot_id")
    candidate_sets = indexed(collections.get("meal_candidate_sets", []))
    meal_configs = plan.get("meal_configs") or {}
    meals = []
    for source in collections.get("meal_options", []):
        item = deepcopy(source)
        meal_id = str(item.get("id") or "")
        config = meal_configs.get(meal_id) or {}
        candidate_set = candidate_sets.get(meal_id)
        if candidate_set:
            selected_id = str(item.get("selected_candidate_id") or "")
            selected = restaurants.get(selected_id)
            binding = next((entry for entry in item.get("candidates") or [] if str(entry.get("restaurant_id")) == selected_id), None)
            snapshot = snapshots.get(str((binding or {}).get("snapshot_id") or ""))
            if not selected or not binding or not snapshot:
                raise AssemblyError(f"餐窗主选绑定不完整：{meal_id}")
            constraints = deepcopy(candidate_set.get("constraints") or {})
            budget = constraints.get("budget_per_person_cny") or {}
            signal_price = next(
                (signal.get("per_person") for signal in snapshot.get("platform_signals") or [] if signal.get("per_person")), None
            )
            item.update({
                "research_status": "complete",
                # Keep the research-contract value unless the plan explicitly replaces
                # that contract. Day events own presentation times; punctuation-only
                # display edits must not break snapshot applicability checks.
                "time_window": config.get("contract_time_window") or candidate_set.get("time_window") or item.get("time_window"),
                "meal_type": config.get("meal_type") or item.get("meal_type"),
                "name": config.get("name") or item.get("name") or "顺路正餐",
                "location": (selected.get("location") or {}).get("physical_address") or selected.get("name"),
                "signature_dishes": selected.get("signature_dishes") or ["以到店菜单为准"],
                "per_person": signal_price or f"约¥{budget.get('min', '?')}–{budget.get('max', '?')}/人（规划带）",
                "opening_hours": (snapshot.get("operations") or {}).get("opening_hours") or "出发前复核",
                "queue_note": (snapshot.get("operations") or {}).get("queue") or item.get("switch_condition"),
                "why_here": item.get("selection_summary"),
                "fallback": item.get("switch_condition") or "主选不可用时切换结构化备选",
                "fallback_rule": item.get("switch_condition") or "主选不可用时切换结构化备选",
                "previous_anchor": deepcopy(candidate_set.get("previous_anchor")),
                "next_anchor": deepcopy(candidate_set.get("next_anchor")),
                "constraints": constraints,
                "candidate_policy": deepcopy(candidate_set.get("candidate_policy")),
                "checked_at": snapshot.get("checked_at") or defaults["checked_at"],
                "action_links": normalize_actions(
                    selected.get("action_links") or [], "restaurant", "地图服务",
                    defaults["restaurant_disclaimer"], defaults["checked_at"],
                ),
            })
        item = deep_merge(item, config.get("overrides") or {})
        meals.append(item)
    output["meal_options"] = meals
    return output, attraction_events


def validate_plan(workspace: Path, plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != "itinerary-plan/v1":
        raise AssemblyError("plan.schema_version 必须是 itinerary-plan/v1")
    for field in ("trip", "workflow", "collections", "days"):
        if field not in plan:
            raise AssemblyError(f"plan 缺少 {field}")
    if (plan.get("workflow") or {}).get("plan_status") == "candidate":
        raise AssemblyError(
            "itinerary plan 仍是 candidate；请在 planning-decisions.json 完成取舍并将 plan_status 设为 reviewed"
        )
    selected_route = read_json(workspace / "selected-route.json")
    if plan["workflow"].get("selected_route_id") != selected_route.get("id"):
        raise AssemblyError("plan.selected_route_id 与 workspace 已确认路线不一致")
    research_path = workspace / "state" / "research.json"
    actual_digest = sha256_file(research_path)
    if plan.get("research_state_sha256") != actual_digest:
        raise AssemblyError(
            "itinerary plan 已过期：research.json 摘要不匹配，请在重新 merge 后更新计划"
        )


def assemble(workspace: Path, plan_path: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    plan = read_json(plan_path)
    validate_plan(workspace, plan)
    defaults = default_settings(plan)
    collections, task_results = load_collections(workspace, plan)
    normalized, attraction_events = normalize_collections(collections, defaults, plan)

    days = []
    seen_event_ids: set[str] = set()
    for source_day in plan["days"]:
        day = deepcopy(source_day)
        events = []
        for spec in day.get("events") or []:
            if spec.get("type") == "attraction":
                attraction_id = str(spec.get("attraction_id") or "")
                if attraction_id not in attraction_events:
                    raise AssemblyError(f"日程引用了未配置的景点事件：{attraction_id}")
                event = deep_merge(attraction_events[attraction_id], spec.get("overrides") or {})
            else:
                event = deepcopy(spec)
            event_id = str(event.get("id") or "")
            if not event_id:
                raise AssemblyError("日程事件缺少 id")
            if event_id in seen_event_ids:
                raise AssemblyError(f"日程事件 ID 重复：{event_id}")
            seen_event_ids.add(event_id)
            events.append(event)
        day["events"] = events
        days.append(day)

    booking_tasks = []
    if plan.get("generate_attraction_booking_tasks", True):
        attraction_map = indexed(normalized.get("attractions", []))
        for attraction_id, attraction in attraction_map.items():
            if attraction_id in attraction_events:
                booking_tasks.append(build_booking_task(attraction, attraction_events[attraction_id], defaults))
    booking_tasks.extend(deepcopy(plan.get("booking_tasks") or []))
    research_profile = (read_json(workspace / "state" / "research.json").get("research_profile") or {})

    planning = {
        "restaurant_research_version": plan.get("restaurant_research_version", 3),
        "inventory_contract_version": plan.get("inventory_contract_version", 1),
        "source_snapshots": load_source_snapshots(workspace, task_results),
        "research_profile": research_profile,
        **{name: normalized.get(name, []) for name in OUTPUT_COLLECTIONS},
        "booking_tasks": booking_tasks,
    }
    planning = deep_merge(planning, plan.get("planning") or {})
    return {
        "trip": deepcopy(plan["trip"]), "workflow": deepcopy(plan["workflow"]),
        "route_proposals": deepcopy(plan.get("route_proposals") or []),
        "planning": planning, "days": days,
        "sources": collect_sources(workspace, plan.get("source_ids")),
        **({"claims": deepcopy(plan["claims"])} if "claims" in plan else {}),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--plan", type=Path, help="默认使用 <workspace>/state/itinerary-plan.json")
    parser.add_argument("--output", type=Path, help="默认写入 <workspace>/artifacts/itinerary.json")
    parser.add_argument(
        "--print-research-sha256", action="store_true",
        help="只打印当前 state/research.json 摘要，供 itinerary plan 绑定输入版本",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workspace = args.workspace.resolve()
    if args.print_research_sha256:
        print(sha256_file(workspace / "state" / "research.json"))
        return 0
    plan_path = args.plan.resolve() if args.plan else workspace / "state" / "itinerary-plan.json"
    output = args.output.resolve() if args.output else workspace / "artifacts" / "itinerary.json"
    payload = assemble(workspace, plan_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
