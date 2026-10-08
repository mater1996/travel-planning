#!/usr/bin/env python3
"""Generate a candidate itinerary plan and apply a small Agent decision overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


COLLECTION_NAMES = (
    "readiness",
    "attractions",
    "transport_edges",
    "intercity_options",
    "vehicles",
    "road_trip_plans",
    "rental_options",
    "parking_locations",
    "lodging_options",
    "restaurants",
    "restaurant_snapshots",
    "meal_candidate_sets",
    "meal_baseline_routes",
    "meal_route_evaluations",
    "meal_options",
    "weather",
)
COLLECTION_PREFERENCES = {
    "readiness": ("readiness", None),
    "attractions": ("attractions", None),
    "transport_edges": ("route-data", None),
    "intercity_options": ("route-data", None),
    "vehicles": ("road-trip", None),
    "road_trip_plans": ("road-trip", None),
    "rental_options": ("road-trip", None),
    "parking_locations": ("road-trip", None),
    "lodging_options": ("stay-food", None),
    "restaurants": ("restaurant-research", "restaurant_discovery"),
    "restaurant_snapshots": ("restaurant-research", "restaurant_discovery"),
    "meal_candidate_sets": ("restaurant-research", "restaurant_discovery"),
    "meal_baseline_routes": ("route-data", "meal_route_evaluation"),
    "meal_route_evaluations": ("route-data", "meal_route_evaluation"),
    "meal_options": ("restaurant-research", "restaurant_ranking"),
    "weather": ("weather-risk", None),
}
COLLECTION_DOMAIN_ALIASES = {
    "transport_edges": {"route-data", "transport", "transport-intercity", "transport-local"},
    "intercity_options": {"route-data", "transport", "transport-intercity"},
    "vehicles": {"road-trip"},
    "road_trip_plans": {"road-trip"},
    "rental_options": {"road-trip"},
    "parking_locations": {"road-trip"},
    "lodging_options": {"stay-food", "stay_food", "lodging"},
    "meal_baseline_routes": {"route-data", "transport", "transport-local"},
    "meal_route_evaluations": {"route-data", "transport", "transport-local"},
}
TIME_RANGE_RE = re.compile(r"(?<!\d)([0-2]\d:[0-5]\d)\s*[-–—至]\s*([0-2]\d:[0-5]\d)")
DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")


class PlanGenerationError(RuntimeError):
    """The research workspace cannot produce a safe candidate plan."""


def read_json_value(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanGenerationError(f"缺少候选计划输入：{path}") from exc
    except json.JSONDecodeError as exc:
        raise PlanGenerationError(f"JSON 无效：{path}: {exc}") from exc


def read_json(path: Path) -> dict[str, Any]:
    value = read_json_value(path)
    if not isinstance(value, dict):
        raise PlanGenerationError(f"JSON 顶层必须是对象：{path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_date_range(*values: Any) -> tuple[str, str] | None:
    for value in values:
        if isinstance(value, dict) and value.get("start") and value.get("end"):
            return str(value["start"]), str(value["end"])
        matches = DATE_RE.findall(str(value or ""))
        if len(matches) >= 2:
            return matches[0], matches[1]
        if len(matches) == 1:
            return matches[0], matches[0]
    return None


def expand_dates(start: str, end: str) -> list[str]:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    if last < first:
        raise PlanGenerationError("路线结束日期早于开始日期")
    return [(first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1)]


def fixed_days(selected_route: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    fixed = selected_route.get("fixed_plan") or []
    if fixed:
        return [
            {
                "date": str(item["date"]),
                "city": str(item.get("city") or ""),
                "intent": str(item.get("intent") or item.get("title") or ""),
            }
            for item in fixed
            if isinstance(item, dict) and item.get("date")
        ]
    value = parse_date_range(
        selected_route.get("date_range"), selected_route.get("date"), brief.get("date_range")
    )
    if not value:
        raise PlanGenerationError("selected-route.json 或 brief.json 缺少可解析的日期")
    destination = str(brief.get("destination") or selected_route.get("destination") or "")
    return [{"date": item, "city": destination, "intent": destination} for item in expand_dates(*value)]


def task_results(workspace: Path, research: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    loaded: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for task in research.get("tasks") or []:
        if not isinstance(task, dict) or not task.get("task_id"):
            continue
        relative = task.get("result_path") or f"results/{task['task_id']}.json"
        path = workspace / str(relative)
        if path.is_file():
            loaded.append((task, read_json(path)))
    return loaded


def task_score(task: dict[str, Any], collection: str, count: int) -> tuple[int, int, str]:
    preferred_domain, preferred_stage = COLLECTION_PREFERENCES[collection]
    domain = str(task.get("domain") or "")
    stage = task.get("stage")
    score = 0
    if domain == preferred_domain or domain in COLLECTION_DOMAIN_ALIASES.get(collection, set()):
        score += 40
    if preferred_stage is not None and stage == preferred_stage:
        score += 80
    if preferred_stage is None and stage is None:
        score += 20
    if collection == "meal_options" and stage == "restaurant_ranking":
        score += 100
    return score, count, str(task.get("task_id") or "")


def choose_collections(
    results: list[tuple[dict[str, Any], dict[str, Any]]]
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    bindings: dict[str, dict[str, Any]] = {}
    values: dict[str, list[dict[str, Any]]] = {}
    for collection in COLLECTION_NAMES:
        candidates: list[tuple[tuple[int, int, str], dict[str, Any], list[dict[str, Any]]]] = []
        for task, result in results:
            items = (result.get("entities") or {}).get(collection)
            if isinstance(items, list):
                candidates.append((task_score(task, collection, len(items)), task, items))
        if not candidates:
            continue
        _, task, items = max(candidates, key=lambda item: item[0])
        id_key = "snapshot_id" if collection == "restaurant_snapshots" else "id"
        ids = [str(item.get(id_key)) for item in items if isinstance(item, dict) and item.get(id_key)]
        binding: dict[str, Any] = {
            "task": str(task["task_id"]),
            "path": f"entities.{collection}",
            "ids": ids,
        }
        if id_key != "id":
            binding["id_key"] = id_key
        bindings[collection] = binding
        values[collection] = deepcopy(items)
    return bindings, values


def day_aliases(days: list[dict[str, str]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for index, item in enumerate(days, start=1):
        day_value = item["date"]
        for alias in (day_value, f"day-{day_value}", f"day-{index}", f"d{index}"):
            aliases[alias] = day_value
    return aliases


def resolve_day(value: Any, aliases: dict[str, str]) -> str | None:
    text = str(value or "")
    if text in aliases:
        return aliases[text]
    match = DATE_RE.search(text)
    if match and match.group(0) in aliases:
        return match.group(0)
    match = re.search(r"(?:day-|d)(\d+)", text)
    if match:
        return aliases.get(f"day-{match.group(1)}") or aliases.get(f"d{match.group(1)}")
    return None


def parse_time_range(value: Any) -> tuple[str, str] | None:
    match = TIME_RANGE_RE.search(str(value or ""))
    return (match.group(1), match.group(2)) if match else None


def minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def time_text(value: int) -> str:
    value = max(0, min(value, 23 * 60 + 59))
    return f"{value // 60:02d}:{value % 60:02d}"


def index_items(items: list[dict[str, Any]], key: str = "id") -> dict[str, dict[str, Any]]:
    return {str(item[key]): item for item in items if isinstance(item, dict) and item.get(key)}


def weather_for_date(weather: list[dict[str, Any]], day_value: str) -> str:
    match = next((item for item in weather if str(item.get("date") or "") == day_value), None)
    if match and match.get("id"):
        return str(match["id"])
    return f"weather-{day_value}"


def attraction_duration(item: dict[str, Any]) -> int:
    checkpoints = item.get("checkpoint_blueprint") or []
    explicit = sum(
        int(point.get("duration_minutes") or 0)
        for point in checkpoints
        if isinstance(point, dict) and str(point.get("duration_minutes") or "").isdigit()
    )
    return max(60, min(explicit or max(1, len(checkpoints)) * 30, 240))


def preferred_start(value: str) -> int:
    parsed = parse_time_range(value)
    if parsed:
        return minutes(parsed[0])
    if "早" in value or "上午" in value:
        return 9 * 60
    if "午后" in value or "下午" in value:
        return 14 * 60
    if "黄昏" in value or "晚" in value or "夜" in value:
        return 18 * 60
    return 9 * 60


def next_free_slot(start: int, duration: int, occupied: list[tuple[int, int]]) -> tuple[int, int]:
    cursor = start
    for lower, upper in sorted(occupied):
        if cursor + duration <= lower:
            break
        if cursor < upper and cursor + duration > lower:
            cursor = upper + 15
    return cursor, cursor + duration


def collect_event_bindings(
    results: list[tuple[dict[str, Any], dict[str, Any]]]
) -> list[dict[str, Any]]:
    bindings = []
    for _, result in results:
        bindings.extend(item for item in result.get("event_bindings") or [] if isinstance(item, dict))
    return bindings


def selected_transport_ids(patch: dict[str, Any]) -> list[str]:
    keys = (
        "recommended_transport_option_id",
        "boundary_option_id",
        "primary_option_id",
        "arrival_ground_edge_id",
        "departure_ground_edge_id",
        "airport_ground_edge_id",
    )
    return [str(patch[key]) for key in keys if patch.get(key)]


def event_id(prefix: str, entity_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", entity_id.lower()).strip("-")
    return f"event-{prefix}-{cleaned}"


def generate_base_plan(
    workspace: Path,
    research: dict[str, Any],
    selected_route: dict[str, Any],
    brief: dict[str, Any],
    route_proposals: Any,
    results: list[tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    research_path = workspace / "state" / "research.json"
    research_digest = sha256_file(research_path)
    day_defs = fixed_days(selected_route, brief)
    aliases = day_aliases(day_defs)
    collections, collection_values = choose_collections(results)
    bindings = collect_event_bindings(results)
    attractions = index_items(collection_values.get("attractions", []))
    route_edges = index_items(collection_values.get("transport_edges", []))
    intercity = index_items(collection_values.get("intercity_options", []))
    lodging = collection_values.get("lodging_options", [])
    weather = collection_values.get("weather", [])
    meals = collection_values.get("meal_options", [])
    events_by_day: dict[str, list[dict[str, Any]]] = {item["date"]: [] for item in day_defs}
    occupied_by_day: dict[str, list[tuple[int, int]]] = {item["date"]: [] for item in day_defs}
    attraction_events: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []

    for item in intercity.values():
        if not item.get("recommended") or not item.get("date"):
            continue
        day_value = str(item["date"])
        if day_value not in events_by_day:
            continue
        departure = str(item.get("departure_at") or "")
        arrival = str(item.get("arrival_at") or "")
        start = departure[11:16] if len(departure) >= 16 else None
        end = arrival[11:16] if len(arrival) >= 16 else None
        spec = {
            "id": event_id("transport", str(item["id"])),
            "type": "transport",
            "route_id": str(item["id"]),
            "title": f"{item.get('from') or '出发地'} → {item.get('to') or '目的地'}",
            "candidate_origin": "recommended_intercity_option",
        }
        if start and end:
            spec.update({"time": start, "end_time": end})
            occupied_by_day[day_value].append((minutes(start), minutes(end)))
        else:
            pending.append({"id": f"set-time-{spec['id']}", "day": day_value, "event_id": spec["id"], "reason": "交通候选缺少完整出发到达时间"})
        events_by_day[day_value].append(spec)

    meal_names = {"lunch": "午餐", "dinner": "晚餐", "breakfast": "早餐"}
    for meal in meals:
        day_value = str(meal.get("date") or "") or resolve_day(meal.get("day_id"), aliases)
        if day_value not in events_by_day or not meal.get("id"):
            continue
        parsed = parse_time_range(meal.get("time_window"))
        if not parsed:
            fallback = {"breakfast": ("08:00", "09:00"), "lunch": ("12:00", "13:00"), "dinner": ("18:30", "19:45")}
            parsed = fallback.get(str(meal.get("meal_type") or ""), ("12:00", "13:00"))
            pending.append({"id": f"review-time-{meal['id']}", "day": day_value, "event_id": event_id("meal", str(meal["id"])), "reason": "餐窗没有可直接解析的精确时间"})
        start, end = parsed
        events_by_day[day_value].append({
            "id": event_id("meal", str(meal["id"])),
            "time": start,
            "end_time": end,
            "type": "meal",
            "meal_id": str(meal["id"]),
            "title": meal.get("name") or meal_names.get(str(meal.get("meal_type") or ""), "用餐"),
            "candidate_origin": "ranked_meal_option",
        })
        occupied_by_day[day_value].append((minutes(start), minutes(end)))

    attraction_bindings = [
        item for item in bindings if (item.get("target") or {}).get("type") == "attraction"
    ]
    for binding in attraction_bindings:
        attraction_id = str((binding.get("target") or {}).get("entity_id") or "")
        attraction = attractions.get(attraction_id)
        if not attraction:
            continue
        day_value = resolve_day(binding.get("day_id"), aliases)
        if not day_value:
            day_value = resolve_day((attraction.get("reservation") or {}).get("target_date"), aliases)
        if day_value not in events_by_day:
            continue
        preferred = str((binding.get("event_patch") or {}).get("preferred_window") or "")
        duration = attraction_duration(attraction)
        start_minute, end_minute = next_free_slot(
            preferred_start(preferred), duration, occupied_by_day[day_value]
        )
        start, end = time_text(start_minute), time_text(end_minute)
        attraction_events[attraction_id] = {
            "event_id": event_id("attraction", attraction_id),
            "start": start,
            "end": end,
            "weather_id": weather_for_date(weather, day_value),
            "title": attraction.get("name") or attraction_id,
            "candidate_origin": "research_binding_and_preferred_window",
        }
        events_by_day[day_value].append({
            "id": event_id("attraction-ref", attraction_id),
            "type": "attraction",
            "attraction_id": attraction_id,
        })
        occupied_by_day[day_value].append((start_minute, end_minute))
        pending.append({
            "id": f"review-attraction-{attraction_id}",
            "day": day_value,
            "event_id": attraction_events[attraction_id]["event_id"],
            "reason": f"景点时间由“{preferred or '未提供偏好时段'}”和 checkpoint 时长机械推导，需结合全日路线复核",
        })

    used_transport_ids = {str(event.get("route_id")) for events in events_by_day.values() for event in events if event.get("route_id")}
    for binding in bindings:
        if (binding.get("target") or {}).get("type") != "day":
            continue
        day_value = resolve_day(binding.get("day_id") or (binding.get("target") or {}).get("entity_id"), aliases)
        if day_value not in events_by_day:
            continue
        for route_id in selected_transport_ids(binding.get("event_patch") or {}):
            if route_id in used_transport_ids:
                continue
            route = route_edges.get(route_id) or intercity.get(route_id)
            if not route:
                continue
            spec = {
                "id": event_id("transport", route_id),
                "type": "transport",
                "route_id": route_id,
                "title": f"{route.get('from') or '起点'} → {route.get('to') or '终点'}",
                "candidate_origin": "selected_day_transport_binding",
            }
            departure = str(route.get("departure_at") or "")
            arrival = str(route.get("arrival_at") or "")
            if len(departure) >= 16 and len(arrival) >= 16:
                spec.update({"time": departure[11:16], "end_time": arrival[11:16]})
            else:
                pending.append({"id": f"set-time-{spec['id']}", "day": day_value, "event_id": spec["id"], "reason": "门到门路线已选定，但开始和结束时间需要结合相邻事件决定"})
            events_by_day[day_value].append(spec)
            used_transport_ids.add(route_id)

    selected_lodging: dict[tuple[str, str], dict[str, Any]] = {}
    for item in lodging:
        check_in, check_out = str(item.get("check_in") or ""), str(item.get("check_out") or "")
        if not check_in or not check_out or not item.get("id"):
            continue
        key = (check_in, check_out)
        current = selected_lodging.get(key)
        if current is None or int(item.get("rank") or 999) < int(current.get("rank") or 999):
            selected_lodging[key] = item
    for (check_in, check_out), item in selected_lodging.items():
        for day_value, kind, start, end, title in (
            (check_in, "checkin", "15:00", "15:15", "办理入住或寄存行李"),
            (check_out, "checkout", "08:00", "08:15", "退房并处理行李"),
        ):
            if day_value not in events_by_day:
                continue
            eid = event_id(kind, str(item["id"]))
            events_by_day[day_value].append({
                "id": eid,
                "time": start,
                "end_time": end,
                "type": "lodging",
                "lodging_id": str(item["id"]),
                "title": title,
                "candidate_origin": "lowest_ranked_lodging_for_stay",
            })
            pending.append({"id": f"review-{eid}", "day": day_value, "event_id": eid, "reason": "住宿主选和办理时间由排名及默认时间生成，需结合订单和交通复核"})

    day_items = []
    for item in day_defs:
        day_value = item["date"]
        events = events_by_day[day_value]
        def sort_key(event: dict[str, Any]) -> tuple[int, str]:
            value = event.get("time")
            if event.get("type") == "attraction":
                value = (attraction_events.get(str(event.get("attraction_id") or "")) or {}).get("start")
            return (minutes(str(value)) if value else 24 * 60, str(event.get("id") or ""))

        events.sort(key=sort_key)
        pending.append({
            "id": f"review-route-continuity-{day_value}",
            "day": day_value,
            "reason": "必须声明 start_anchor/end_anchor，并为所有相邻地点活动补齐独立交通事件",
        })
        day_items.append({
            "date": day_value,
            "title": item.get("intent") or item.get("city") or day_value,
            "area": item.get("city"),
            "candidate_origin": "selected_route_fixed_plan",
            "events": events,
        })

    travelers = brief.get("travelers") or selected_route.get("travelers") or "按 brief 执行"
    if isinstance(travelers, dict):
        travelers = f"{travelers.get('adults', '?')}位成人 · {travelers.get('rooms', '?')}间房"
    updated = str(brief.get("updated_at") or selected_route.get("selected_at") or research.get("merged_at") or "")
    if isinstance(route_proposals, list):
        route_values = route_proposals
    elif isinstance(route_proposals, dict):
        route_values = route_proposals.get("routes") or route_proposals.get("proposals") or []
    else:
        route_values = []
    if not isinstance(route_values, list):
        route_values = []
    plan = {
        "schema_version": "itinerary-plan/v1",
        "research_state_sha256": research_digest,
        "generation": {
            "generator": "generate_itinerary_plan.py",
            "mode": "candidate_plus_decisions",
            "research_merged_at": research.get("merged_at"),
            "pending_decisions": pending,
        },
        "trip": {
            "title": f"{selected_route.get('title') or selected_route.get('label') or selected_route.get('name') or brief.get('destination') or '旅行'} · 候选执行计划",
            "destination": brief.get("destination"),
            "date_range": brief.get("date_range") or selected_route.get("date_range") or selected_route.get("date"),
            "travelers": travelers,
            "budget": brief.get("budget") or selected_route.get("budget") or selected_route.get("budget_policy"),
            "currency": "CNY",
            "updated_at": updated[:10],
            "assumptions": deepcopy(selected_route.get("assumptions") or brief.get("constraints") or []),
        },
        "workflow": {
            "phase": "confirmed_planning",
            "plan_status": "candidate",
            "selected_route_id": str(selected_route.get("id") or ""),
            "confirmed_at": selected_route.get("selected_at") or selected_route.get("confirmed_at"),
        },
        "route_proposals": route_values,
        "defaults": {"checked_at": updated[:10]},
        "collections": collections,
        "attraction_events": attraction_events,
        "meal_configs": {},
        "generate_attraction_booking_tasks": True,
        "booking_tasks": [],
        "restaurant_research_version": 3,
        "inventory_contract_version": 1,
        "planning": {"route_continuity_version": 1},
        "days": day_items,
    }
    return plan


def decision_template(base: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "planning-decisions/v1",
        "research_state_sha256": base["research_state_sha256"],
        "workflow": {},
        "trip": {},
        "defaults": {},
        "collections": {},
        "attraction_events": {},
        "meal_configs": {},
        "planning": {},
        "days": {
            str(day["date"]): {
                "event_order": [str(event["id"]) for event in day.get("events") or []],
                "event_overrides": {},
                "remove_event_ids": [],
                "append_events": [],
            }
            for day in base.get("days") or []
        },
        "booking_tasks": [],
        "decision_notes": [
            "复核 generation.pending_decisions，按需调整事件顺序、时间、主选和降级策略。",
            "逐日填写 start_anchor/end_anchor，并确认所有相邻地点活动之间都有独立 transport 事件。",
            "完成后将 workflow.plan_status 设为 reviewed，再重新运行生成器。",
        ],
    }


def apply_day_decision(day: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    result = deep_merge(day, {key: value for key, value in decision.items() if key not in {
        "event_order", "event_overrides", "remove_event_ids", "append_events"
    }})
    events = {str(item.get("id") or ""): deepcopy(item) for item in day.get("events") or [] if item.get("id")}
    for event_id in decision.get("remove_event_ids") or []:
        events.pop(str(event_id), None)
    for event_id, overlay in (decision.get("event_overrides") or {}).items():
        if str(event_id) not in events:
            raise PlanGenerationError(f"day decision 引用了未知事件：{day.get('date')} / {event_id}")
        events[str(event_id)] = deep_merge(events[str(event_id)], overlay)
    for item in decision.get("append_events") or []:
        if not isinstance(item, dict) or not item.get("id"):
            raise PlanGenerationError(f"{day.get('date')} append_events 必须包含带 id 的对象")
        if str(item["id"]) in events:
            raise PlanGenerationError(f"{day.get('date')} append_events ID 重复：{item['id']}")
        events[str(item["id"])] = deepcopy(item)
    order = [str(value) for value in decision.get("event_order") or []]
    unknown = [value for value in order if value not in events]
    if unknown:
        raise PlanGenerationError(f"{day.get('date')} event_order 引用了未知事件：{unknown}")
    if len(order) != len(set(order)):
        raise PlanGenerationError(f"{day.get('date')} event_order 存在重复 ID")
    order.extend(event_id for event_id in events if event_id not in order)
    result["events"] = [events[event_id] for event_id in order]
    return result


def materialize(base: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    if decisions.get("schema_version") != "planning-decisions/v1":
        raise PlanGenerationError("planning-decisions.schema_version 必须是 planning-decisions/v1")
    if decisions.get("research_state_sha256") != base.get("research_state_sha256"):
        raise PlanGenerationError("planning-decisions 已过期；研究状态变化后必须复核决策并更新 research_state_sha256")
    result = deepcopy(base)
    for name in ("trip", "workflow", "defaults", "planning"):
        result[name] = deep_merge(result.get(name) or {}, decisions.get(name) or {})
    for name in ("collections", "attraction_events", "meal_configs"):
        for item_id, overlay in (decisions.get(name) or {}).items():
            result.setdefault(name, {})[str(item_id)] = deep_merge(
                result.get(name, {}).get(str(item_id)) or {}, overlay
            )
    decision_days = decisions.get("days") or {}
    result["days"] = [
        apply_day_decision(day, decision_days.get(str(day.get("date"))) or {})
        for day in result.get("days") or []
    ]
    result["booking_tasks"] = list(result.get("booking_tasks") or []) + deepcopy(decisions.get("booking_tasks") or [])
    result["generation"]["decisions_applied"] = True
    result["generation"]["decision_status"] = result.get("workflow", {}).get("plan_status")
    return result


def generated_output(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        payload = read_json(path)
    except PlanGenerationError:
        return False
    return (payload.get("generation") or {}).get("generator") == "generate_itinerary_plan.py"


def generate(
    workspace: Path,
    base_path: Path,
    decisions_path: Path,
    output_path: Path,
    *,
    force: bool = False,
    reset_decisions: bool = False,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if output_path.exists() and not force and not generated_output(output_path):
        raise PlanGenerationError(f"拒绝覆盖非生成计划：{output_path}；确认迁移后使用 --force")
    research = read_json(workspace / "state" / "research.json")
    selected_route = read_json(workspace / "selected-route.json")
    brief = read_json(workspace / "brief.json")
    proposals_path = workspace / "route-proposals.json"
    proposals = read_json_value(proposals_path) if proposals_path.is_file() else {}
    results = task_results(workspace, research)
    base = generate_base_plan(workspace, research, selected_route, brief, proposals, results)
    if decisions_path.exists() and not reset_decisions:
        decisions = read_json(decisions_path)
    else:
        decisions = decision_template(base)
    output = materialize(base, decisions)
    write_json(base_path, base)
    write_json(decisions_path, decisions)
    write_json(output_path, output)
    return {
        "status": "ok",
        "base": str(base_path),
        "decisions": str(decisions_path),
        "output": str(output_path),
        "plan_status": (output.get("workflow") or {}).get("plan_status"),
        "pending_decision_count": len((output.get("generation") or {}).get("pending_decisions") or []),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--base", type=Path, help="默认写入 <workspace>/state/itinerary-plan.base.json")
    parser.add_argument("--decisions", type=Path, help="默认使用 <workspace>/state/planning-decisions.json")
    parser.add_argument("--output", type=Path, help="默认写入 <workspace>/state/itinerary-plan.json")
    parser.add_argument("--force", action="store_true", help="允许替换现有非生成 itinerary-plan.json")
    parser.add_argument("--reset-decisions", action="store_true", help="重建空白 decisions 模板")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workspace = args.workspace.resolve()
    state = workspace / "state"
    result = generate(
        workspace,
        (args.base or state / "itinerary-plan.base.json").resolve(),
        (args.decisions or state / "planning-decisions.json").resolve(),
        (args.output or state / "itinerary-plan.json").resolve(),
        force=args.force,
        reset_decisions=args.reset_decisions,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PlanGenerationError as exc:
        print(str(exc))
        raise SystemExit(1) from exc
