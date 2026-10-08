#!/usr/bin/env python3
"""Audit a merged itinerary before rendering the final HTML artifact."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


RENDERER_PATH = Path(__file__).with_name("render_itinerary.py")
SPEC = importlib.util.spec_from_file_location("render_itinerary", RENDERER_PATH)
assert SPEC and SPEC.loader
render_itinerary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_itinerary)

REPORT_PHRASES = ("综合考虑", "总体而言", "值得一去", "丰富体验", "感受当地", "合理安排", "行程亮点")
TRANSPORT_COVERAGE_SORTS = {2, 3, 4, 6, 7}
STRONG_AVAILABILITY_CLAIMS = {"available", "confirmed", "verified", "booked", "有房", "可订", "已确认"}


def minute_of(value: Any) -> int | None:
    text = str(value or "")
    parts = text.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    hour, minute = int(parts[0]), int(parts[1])
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def minute_range(value: Any) -> tuple[int, int] | None:
    text = str(value or "").replace("—", "–").replace("-", "–")
    parts = [part.strip() for part in text.split("–")]
    if len(parts) != 2:
        return None
    start, end = minute_of(parts[0]), minute_of(parts[1])
    if start is None or end is None or end < start:
        return None
    return start, end


def event_text(event: dict[str, Any]) -> str:
    values: list[str] = []
    for field in ("title", "subtitle"):
        if event.get(field):
            values.append(str(event[field]))
    values.extend(str(value) for value in event.get("details") or [])
    values.extend(str(value) for value in event.get("tips") or [])
    return " ".join(values)


def transport_coverage_key(snapshot: dict[str, Any]) -> str | None:
    if snapshot.get("snapshot_kind") != "quote" or snapshot.get("product_type") not in {"flight", "train"}:
        return None
    query = snapshot.get("query") or {}
    if query.get("transport_no"):
        return None
    identifying = {
        key: query.get(key)
        for key in ("origin", "destination", "dep_date", "journey_type", "seat_class_name")
    }
    return json.dumps(identifying, ensure_ascii=False, sort_keys=True)


def coordinates(value: Any) -> tuple[float, float] | None:
    try:
        longitude, latitude = (float(part.strip()) for part in str(value or "").split(","))
    except (TypeError, ValueError):
        return None
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return None
    return longitude, latitude


def anchor(value: Any, *, name: Any = None, coordinate_value: Any = None) -> dict[str, Any] | None:
    source = value if isinstance(value, dict) else {}
    anchor_name = str(source.get("name") or name or "").strip()
    anchor_coordinates = str(source.get("coordinates") or coordinate_value or "").strip()
    if not anchor_name and not anchor_coordinates:
        return None
    return {"name": anchor_name, "coordinates": anchor_coordinates}


def anchor_label(value: dict[str, Any] | None) -> str:
    if not value:
        return "未知地点"
    return str(value.get("name") or value.get("coordinates") or "未知地点")


def anchor_distance(first: dict[str, Any] | None, second: dict[str, Any] | None) -> float | None:
    first_point = coordinates((first or {}).get("coordinates"))
    second_point = coordinates((second or {}).get("coordinates"))
    if not first_point or not second_point:
        return None
    lon1, lat1 = (math.radians(value) for value in first_point)
    lon2, lat2 = (math.radians(value) for value in second_point)
    delta_lon, delta_lat = lon2 - lon1, lat2 - lat1
    haversine = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(haversine))


def same_anchor(first: dict[str, Any] | None, second: dict[str, Any] | None) -> bool:
    distance = anchor_distance(first, second)
    if distance is not None:
        return distance <= 20
    first_name = "".join(str((first or {}).get("name") or "").split()).casefold()
    second_name = "".join(str((second or {}).get("name") or "").split()).casefold()
    return bool(first_name and first_name == second_name)


def activity_anchors(
    event: dict[str, Any],
    attractions: dict[str, dict[str, Any]],
    meals: dict[str, dict[str, Any]],
    restaurants: dict[str, dict[str, Any]],
    lodgings: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None] | None:
    kind = event.get("type")
    if kind == "attraction":
        item = attractions.get(str(event.get("attraction_id") or "")) or {}
        return anchor(item.get("entrance")), anchor(item.get("exit") or item.get("entrance"))
    if kind == "meal":
        meal = meals.get(str(event.get("meal_id") or "")) or {}
        restaurant = restaurants.get(str(meal.get("selected_candidate_id") or "")) or {}
        location = restaurant.get("location") or {}
        point = anchor(location, name=restaurant.get("name"))
        return point, point
    if kind == "lodging":
        lodging = lodgings.get(str(event.get("lodging_id") or "")) or {}
        point = anchor(lodging.get("location"), name=lodging.get("name"))
        return point, point
    if kind == "rest":
        point = anchor(event.get("location"), name=event.get("title"))
        return point, point
    return None


def transport_anchors(event: dict[str, Any], routes: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    route = routes.get(str(event.get("route_id") or "")) or {}
    map_route = route.get("map_route") or {}
    origin = anchor(route.get("origin"), name=route.get("from"), coordinate_value=map_route.get("origin"))
    destination = anchor(route.get("destination"), name=route.get("to"), coordinate_value=map_route.get("destination"))
    return origin, destination, route


def audit_route_continuity(data: dict[str, Any]) -> list[str]:
    planning = data.get("planning") or {}
    if (data.get("workflow") or {}).get("phase") not in {"confirmed_planning", "final"}:
        return []
    blocking: list[str] = []
    if planning.get("route_continuity_version") != 1:
        return ["正式行程缺少 planning.route_continuity_version=1，无法证明逐日地点与交通连续性"]

    attractions = {str(item.get("id")): item for item in planning.get("attractions") or [] if item.get("id")}
    meals = {str(item.get("id")): item for item in planning.get("meal_options") or [] if item.get("id")}
    restaurants = {str(item.get("id")): item for item in planning.get("restaurants") or [] if item.get("id")}
    lodgings = {str(item.get("id")): item for item in planning.get("lodging_options") or [] if item.get("id")}
    meal_route_evaluations = {
        str(item.get("id")): item
        for item in planning.get("meal_route_evaluations") or []
        if item.get("id")
    }
    routes = {
        str(item.get("id")): item
        for item in [*(planning.get("transport_edges") or []), *(planning.get("intercity_options") or [])]
        if item.get("id")
    }
    daily_routes = {str(item.get("date")): item for item in planning.get("daily_routes") or [] if item.get("date")}

    for day in data.get("days") or []:
        day_name = str(day.get("date") or day.get("label") or "未命名日期")
        start_anchor = anchor(day.get("start_anchor"))
        end_anchor = anchor(day.get("end_anchor"))
        if not start_anchor or not coordinates(start_anchor.get("coordinates")):
            blocking.append(f"{day_name} 缺少带坐标的 start_anchor")
        if not end_anchor or not coordinates(end_anchor.get("coordinates")):
            blocking.append(f"{day_name} 缺少带坐标的 end_anchor")

        previous_place: tuple[dict[str, Any], dict[str, Any]] | None = None
        pending_transports: list[tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]] = []
        resolved_start: dict[str, Any] | None = None
        resolved_end: dict[str, Any] | None = None
        location_event_ids: set[str] = set()
        day_events = day.get("events") or []

        for event in day_events:
            event_id = str(event.get("id") or "")
            title = str(event.get("title") or event_id or "未命名")
            if event.get("type") == "transport":
                origin, destination, route = transport_anchors(event, routes)
                if (
                    not origin or not origin.get("name") or not coordinates(origin.get("coordinates"))
                    or not destination or not destination.get("name") or not coordinates(destination.get("coordinates"))
                ):
                    blocking.append(f"{day_name} 交通“{title}”缺少带坐标的准确起终点")
                if not route.get("mode"):
                    blocking.append(f"{day_name} 交通“{title}”缺少 mode")
                distance = route.get("distance_meters")
                if distance is None:
                    blocking.append(f"{day_name} 交通“{title}”缺少 distance_meters")
                elif not isinstance(distance, (int, float)) or distance < 0:
                    blocking.append(f"{day_name} 交通“{title}”的 distance_meters 必须是非负数")
                if not (route.get("door_to_door_duration") or route.get("door_to_door_minutes")):
                    blocking.append(f"{day_name} 交通“{title}”缺少门到门时长")
                if not route.get("fallback"):
                    blocking.append(f"{day_name} 交通“{title}”缺少 fallback")
                has_map = str(route.get("map_url") or "").startswith("https://") or any(
                    action.get("type") == "map" and str(action.get("url") or "").startswith("https://")
                    for action in route.get("action_links") or []
                )
                if not has_map:
                    blocking.append(f"{day_name} 交通“{title}”缺少可执行地图链接")
                if resolved_start is None:
                    resolved_start = origin
                pending_transports.append((event, origin, destination))
                resolved_end = destination
                continue

            anchors = activity_anchors(event, attractions, meals, restaurants, lodgings)
            if anchors is None:
                continue
            activity_start, activity_end = anchors
            location_event_ids.add(event_id)
            if not activity_start or not coordinates(activity_start.get("coordinates")) or not activity_end or not coordinates(activity_end.get("coordinates")):
                blocking.append(f"{day_name} 地点活动“{title}”缺少带坐标的入口或出口")
                previous_place = (event, activity_end or activity_start or {})
                pending_transports = []
                continue
            if resolved_start is None:
                resolved_start = activity_start

            if previous_place:
                previous_event, previous_end = previous_place
                previous_title = str(previous_event.get("title") or previous_event.get("id") or "上一活动")
                if same_anchor(previous_end, activity_start):
                    if pending_transports:
                        blocking.append(f"{day_name} “{previous_title}”与“{title}”位于同一地点，却插入了不必要的交通事件")
                elif not pending_transports:
                    blocking.append(
                        f"{day_name} “{previous_title}”结束于{anchor_label(previous_end)}，"
                        f"“{title}”开始于{anchor_label(activity_start)}，两者之间缺少独立交通事件"
                    )
                else:
                    first_origin = pending_transports[0][1]
                    last_destination = pending_transports[-1][2]
                    if first_origin and not same_anchor(previous_end, first_origin):
                        blocking.append(f"{day_name} “{previous_title}”后的交通起点未衔接其出口")
                    if last_destination and not same_anchor(last_destination, activity_start):
                        blocking.append(f"{day_name} 到“{title}”的交通终点未衔接其入口")
                    for index in range(1, len(pending_transports)):
                        if not same_anchor(pending_transports[index - 1][2], pending_transports[index][1]):
                            blocking.append(f"{day_name} 连续交通事件在第{index}次换乘处端点不连续")
            elif pending_transports:
                last_destination = pending_transports[-1][2]
                if last_destination and not same_anchor(last_destination, activity_start):
                    blocking.append(f"{day_name} 首个地点活动“{title}”未衔接前序交通终点")

            previous_place = (event, activity_end)
            pending_transports = []
            resolved_end = activity_end

        if previous_place and pending_transports:
            previous_title = str(previous_place[0].get("title") or previous_place[0].get("id") or "最后活动")
            if pending_transports[0][1] and not same_anchor(previous_place[1], pending_transports[0][1]):
                blocking.append(f"{day_name} “{previous_title}”后的返程交通起点未衔接其出口")
            resolved_end = pending_transports[-1][2]

        if start_anchor and resolved_start and not same_anchor(start_anchor, resolved_start):
            blocking.append(f"{day_name} start_anchor 与首个地点或交通起点不一致")
        if end_anchor and resolved_end and not same_anchor(end_anchor, resolved_end):
            blocking.append(f"{day_name} end_anchor 与最后地点或交通终点不一致")

        daily_route = daily_routes.get(day_name) or {}
        stop_event_ids = {str(stop.get("event_id")) for stop in daily_route.get("stops") or [] if stop.get("event_id")}
        missing_stop_events = sorted(event_id for event_id in location_event_ids if event_id and event_id not in stop_event_ids)
        if missing_stop_events:
            blocking.append(f"{day_name} 每日路线图缺少地点事件 stop 绑定：{'、'.join(missing_stop_events)}")

        for index, event in enumerate(day_events):
            if event.get("type") != "meal":
                continue
            title = str(event.get("title") or event.get("meal_id") or "未命名餐饮")
            meal = meals.get(str(event.get("meal_id") or "")) or {}
            selected_id = str(meal.get("selected_candidate_id") or "")
            candidate = next(
                (item for item in meal.get("candidates") or [] if str(item.get("restaurant_id") or "") == selected_id),
                {},
            )
            evaluation = meal_route_evaluations.get(str(candidate.get("route_evaluation_id") or "")) or {}
            for direction, offset, leg_name in (("进店", -1, "from_previous"), ("离店", 1, "to_next")):
                adjacent = day_events[index + offset] if 0 <= index + offset < len(day_events) else {}
                if adjacent.get("type") != "transport":
                    blocking.append(f"{day_name} 餐饮“{title}”的主选{direction}路线没有投影为相邻交通事件")
                    continue
                actual_origin, actual_destination, _ = transport_anchors(adjacent, routes)
                leg = evaluation.get(leg_name) or {}
                expected_origin = anchor(leg.get("origin"))
                expected_destination = anchor(leg.get("destination"))
                if (
                    not expected_origin or not expected_destination
                    or not same_anchor(actual_origin, expected_origin)
                    or not same_anchor(actual_destination, expected_destination)
                ):
                    blocking.append(f"{day_name} 餐饮“{title}”的主选{direction}路线与相邻交通事件起终点不一致")

    return list(dict.fromkeys(blocking))


def audit(data: dict[str, Any]) -> dict[str, Any]:
    blocking: list[str] = []
    warnings: list[str] = []
    try:
        render_itinerary.validate_data(data)
    except ValueError as error:
        blocking.append(str(error))
    blocking.extend(audit_route_continuity(data))

    planning = data.get("planning") or {}
    meals = {item.get("id"): item for item in planning.get("meal_options") or []}
    attractions = {
        str(item.get("id")): item
        for item in planning.get("attractions") or []
        if item.get("id")
    }
    source_snapshots = {
        str(item.get("snapshot_id")): item
        for item in planning.get("source_snapshots") or []
        if item.get("snapshot_id")
    }
    inventory_candidates = {
        str(item.get("id")): item
        for item in [
            *(planning.get("transport_edges") or []),
            *(planning.get("intercity_options") or []),
            *(planning.get("lodging_options") or []),
            *(planning.get("rental_options") or []),
        ]
        if item.get("id")
    }
    selected_inventory_refs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    checked_event_ids: list[str] = []
    used_meal_ids: set[str] = set()

    active_modules = set((planning.get("research_profile") or {}).get("modules") or [])
    vehicles = {str(item.get("id")): item for item in planning.get("vehicles") or [] if item.get("id")}
    route_entities = {
        str(item.get("id")): item
        for item in [*(planning.get("transport_edges") or []), *(planning.get("intercity_options") or [])]
        if item.get("id")
    }
    parking_locations = {
        str(item.get("id")): item for item in planning.get("parking_locations") or [] if item.get("id")
    }
    road_trip_plans = planning.get("road_trip_plans") or []
    rental_options = planning.get("rental_options") or []
    if "transport.self_drive" in active_modules and not road_trip_plans:
        blocking.append("research profile 已激活自驾，但最终规划缺少 road_trip_plans；驾车地图路线不能替代自驾审查")
    if "transport.car_rental" in active_modules and not rental_options:
        blocking.append("research profile 已激活租车，但最终规划缺少 rental_options")
    for plan in road_trip_plans:
        plan_id = str(plan.get("id") or "未命名自驾计划")
        if str(plan.get("vehicle_id") or "") not in vehicles:
            blocking.append(f"自驾计划“{plan_id}”引用了不存在的 vehicle_id")
        missing_routes = sorted(
            str(value) for value in plan.get("route_edge_ids") or [] if str(value) not in route_entities
        )
        if missing_routes:
            blocking.append(f"自驾计划“{plan_id}”引用了不存在的交通边：{'、'.join(missing_routes)}")
        for stop in plan.get("parking_stops") or []:
            parking_id = str(stop.get("parking_location_id") or "")
            if parking_id and parking_id not in parking_locations:
                blocking.append(f"自驾计划“{plan_id}”引用了不存在的停车点：{parking_id}")
            if not parking_id and not stop.get("fallback"):
                blocking.append(f"自驾计划“{plan_id}”的停靠点“{stop.get('stop_id') or '未命名'}”缺少停车点或替代接驳")
    for option in rental_options:
        option_id = str(option.get("id") or "未命名租车候选")
        if str(option.get("vehicle_id") or "") not in vehicles:
            blocking.append(f"租车候选“{option_id}”引用了不存在的 vehicle_id")
        pickup_at = str((option.get("pickup") or {}).get("event_at") or "")
        return_at = str((option.get("return") or {}).get("event_at") or "")
        try:
            if datetime.fromisoformat(return_at.replace("Z", "+00:00")) <= datetime.fromisoformat(pickup_at.replace("Z", "+00:00")):
                blocking.append(f"租车候选“{option_id}”的还车时间不晚于取车时间")
        except (TypeError, ValueError):
            blocking.append(f"租车候选“{option_id}”的取还车 event_at 不是有效 ISO 时间")

    for day in data.get("days") or []:
        events = day.get("events") or []
        day_name = day.get("date") or day.get("label") or "未命名日期"
        previous_end: int | None = None
        timed_events: list[tuple[int, int, dict[str, Any]]] = []
        for event in events:
            title = event.get("title") or "未命名"
            if "description" in event:
                blocking.append(
                    f"{day_name} 事件“{title}”使用 renderer 不展示的 description；"
                    "请改用 subtitle、details[]、tips[] 或类型专属结构"
                )
            if event.get("type") == "note" and "end_time" in event:
                blocking.append(
                    f"{day_name} 提示“{title}”不能用 end_time 占据持续时间窗；"
                    "持续活动应改为对应事件，城市漫游应使用 attraction + checkpoints，自由留白使用 rest"
                )
            if event.get("id"):
                checked_event_ids.append(str(event["id"]))
            elif (data.get("workflow") or {}).get("phase") in {"confirmed_planning", "final"}:
                blocking.append(f"{day_name} 事件“{event.get('title') or '未命名'}”缺少稳定 id")
            if event.get("type") == "attraction":
                execution = event.get("execution") or {}
                checkpoints = execution.get("checkpoints") or []
                if not checkpoints:
                    blocking.append(f"{day_name} 景点“{event.get('title') or '未命名'}”缺少必达卡点和内部顺序")
                orders = [point.get("order") for point in checkpoints]
                if checkpoints and orders != list(range(1, len(checkpoints) + 1)):
                    blocking.append(f"{day_name} 景点“{event.get('title') or '未命名'}”的 checkpoint order 必须从1连续递增")
                attraction = attractions.get(str(event.get("attraction_id") or "")) or {}
                if attraction.get("attraction_type") == "urban_walk":
                    if len(checkpoints) < 2:
                        blocking.append(f"{day_name} 城市漫游“{title}”至少需要两个 checkpoints")
                    for point in checkpoints:
                        point_name = point.get("name") or point.get("id") or "未命名节点"
                        narration = str(point.get("narration") or "").strip()
                        if not narration or narration in render_itinerary.LEGACY_CHECKPOINT_PLACEHOLDERS:
                            blocking.append(f"{day_name} 城市漫游节点“{point_name}”缺少具体现场看点 narration")
                        if not str(point.get("instruction") or "").strip():
                            blocking.append(f"{day_name} 城市漫游节点“{point_name}”缺少旅行者动作或转向 instruction")
                checkpoint_previous_end: int | None = None
                event_start = minute_of(event.get("time"))
                event_end = minute_of(event.get("end_time"))
                for point in checkpoints:
                    point_start = minute_of(point.get("time"))
                    point_end = minute_of(point.get("end_time"))
                    point_name = point.get("name") or point.get("id") or "未命名节点"
                    if point_start is None or point_end is None:
                        blocking.append(f"{day_name} 景点节点“{point_name}”必须提供 HH:MM 的 time 和 end_time")
                        continue
                    if point_end < point_start:
                        blocking.append(f"{day_name} 景点节点“{point_name}”的 end_time 早于 time")
                    if checkpoint_previous_end is not None and point_start < checkpoint_previous_end:
                        blocking.append(f"{day_name} 景点节点“{point_name}”与前一节点时间重叠")
                    if event_start is not None and point_start < event_start:
                        blocking.append(f"{day_name} 景点节点“{point_name}”早于外层景点事件")
                    if event_end is not None and point_end > event_end:
                        blocking.append(f"{day_name} 景点节点“{point_name}”晚于外层景点事件")
                    checkpoint_previous_end = point_end
                    for image in point.get("images") or []:
                        required_image = {"url", "alt", "source_url", "license"}
                        missing_image = sorted(field for field in required_image if not image.get(field))
                        if missing_image or not (image.get("author") or image.get("source_label")):
                            blocking.append(f"{day_name} 景点节点“{point_name}”的图片缺少 alt、作者/机构、许可或原始页面")
                    if point.get("meal_id"):
                        used_meal_ids.add(str(point["meal_id"]))
            start = minute_of(event.get("time"))
            end = minute_of(event.get("end_time"))
            if start is None:
                blocking.append(f"{day_name} 事件“{event.get('title') or '未命名'}”的 time 必须是 HH:MM")
                continue
            if previous_end is not None and start < previous_end:
                blocking.append(f"{day_name} 事件“{event.get('title') or '未命名'}”与前一事件时间重叠或顺序倒置")
            if end is not None and end < start:
                blocking.append(f"{day_name} 事件“{event.get('title') or '未命名'}”的 end_time 早于 time")
            timed_events.append((start, end if end is not None else start, event))
            previous_end = end if end is not None else start

            if event.get("type") == "meal" and event.get("meal_id"):
                meal_id = str(event["meal_id"])
                used_meal_ids.add(meal_id)
                meal = meals.get(meal_id) or {}
                allowed = minute_range(meal.get("time_window"))
                if end is None:
                    blocking.append(f"{day_name} 餐饮事件“{event.get('title') or meal_id}”必须提供 end_time")
                elif allowed and (start < allowed[0] or end > allowed[1]):
                    blocking.append(
                        f"{day_name} 餐饮事件“{event.get('title') or meal_id}”的事件时间超出 meal_option.time_window"
                    )

            candidate_id = event.get("route_id") if event.get("type") == "transport" else event.get("lodging_id") if event.get("type") == "lodging" else None
            candidate = inventory_candidates.get(str(candidate_id or "")) or {}
            for ref in candidate.get("inventory_refs") or []:
                selected_inventory_refs.append((candidate, ref))

            text = event_text(event)
            found = [phrase for phrase in REPORT_PHRASES if phrase in text]
            if found:
                warnings.append(f"{day_name} 事件“{event.get('title') or '未命名'}”含汇报式措辞：{'、'.join(found)}")

        if not timed_events:
            continue
        day_start = min(start for start, _, _ in timed_events)
        day_end = max(end for _, end, _ in timed_events)
        exemptions = day.get("meal_exemptions") or {}
        for meal_type, center in (("午餐", 12 * 60 + 30), ("晚餐", 19 * 60)):
            if not (day_start <= center <= day_end) or exemptions.get(meal_type):
                continue
            has_meal = any(
                event.get("type") == "meal" and (meals.get(event.get("meal_id")) or {}).get("meal_type") == meal_type
                for _, _, event in timed_events
            )
            if not has_meal:
                blocking.append(f"{day_name} 跨过{meal_type}窗口但没有绑定 meal_id 的{meal_type}事件")

    blocking = list(dict.fromkeys(blocking))
    unused_meals = sorted(str(meal_id) for meal_id in meals if meal_id not in used_meal_ids)
    if unused_meals:
        warnings.append(f"存在未绑定到事件或景点节点的 meal_options：{'、'.join(unused_meals)}")
    warnings = list(dict.fromkeys(warnings))
    purchase_refresh_snapshot_ids: set[str] = set()
    checked_inventory_refs: set[tuple[str, str]] = set()
    coverage_by_query: dict[str, set[int]] = {}
    for snapshot in source_snapshots.values():
        key = transport_coverage_key(snapshot)
        sort_type = (snapshot.get("query") or {}).get("sort_type")
        if key and isinstance(sort_type, int):
            coverage_by_query.setdefault(key, set()).add(sort_type)
    selected_coverage_keys: set[str] = set()
    coverage_gaps: list[str] = []
    lodging_verification_issues: list[str] = []
    for candidate, ref in selected_inventory_refs:
        snapshot_id = str(ref.get("snapshot_id") or "")
        offer_id = str(ref.get("offer_id") or "")
        if (snapshot_id, offer_id) in checked_inventory_refs:
            continue
        checked_inventory_refs.add((snapshot_id, offer_id))
        snapshot = source_snapshots.get(snapshot_id) or {}
        item = next(
            (entry for entry in snapshot.get("items") or [] if str(entry.get("offer_id") or "") == offer_id),
            {},
        )
        coverage_key = transport_coverage_key(snapshot)
        if coverage_key:
            selected_coverage_keys.add(coverage_key)
        if snapshot.get("snapshot_kind") == "quote":
            purchase_refresh_snapshot_ids.add(snapshot_id)
        if snapshot.get("product_type") == "hotel":
            requested = (snapshot.get("query") or {}).get("requested_occupancy") or {}
            requirement = candidate.get("room_requirement") or {}
            requested_rooms = requested.get("rooms")
            requested_adults = requested.get("adults")
            if not requested_rooms or not requested_adults:
                lodging_verification_issues.append(
                    f"住宿候选“{candidate.get('id') or '未命名'}”的报价快照没有记录成人数和房间数"
                )
            elif requirement and (
                requested_rooms != requirement.get("rooms")
                or requested_adults != requirement.get("travelers")
            ):
                lodging_verification_issues.append(
                    f"住宿候选“{candidate.get('id') or '未命名'}”的报价人数/房间数与行程需求不一致"
                )
            availability = item.get("availability") or {}
            selection_status = str(candidate.get("selection_status") or "").casefold()
            if availability.get("remaining") is None and selection_status in STRONG_AVAILABILITY_CLAIMS:
                blocking.append(
                    f"住宿候选“{candidate.get('id') or '未命名'}”没有多间同房型库存证据，不能标记为有房或已确认"
                )
            location_verification = candidate.get("location_verification") or {}
            if location_verification.get("status") != "verified":
                lodging_verification_issues.append(
                    f"住宿候选“{candidate.get('id') or '未命名'}”尚未完成酒店全名、城市/行政区、地址和坐标核验"
                )
        if snapshot.get("product_type") == "train" and (
            candidate.get("country_code") == "CN"
            or (candidate.get("rail_verification") or {}).get("channel") == "12306"
        ):
            verification = candidate.get("rail_verification") or {}
            if not verification.get("action_link") or verification.get("channel") != "12306":
                blocking.append(f"铁路候选“{candidate.get('id') or '未命名'}”缺少 12306 最终复核入口")
            elif (data.get("workflow") or {}).get("phase") == "final" and verification.get("status") != "verified":
                blocking.append(f"最终铁路候选“{candidate.get('id') or '未命名'}”尚未完成 12306 复核")
    for key in sorted(selected_coverage_keys):
        missing = sorted(TRANSPORT_COVERAGE_SORTS - coverage_by_query.get(key, set()))
        if missing:
            coverage_gaps.append(f"所选开放式交通查询缺少排序覆盖：{','.join(str(value) for value in missing)}")
    phase = (data.get("workflow") or {}).get("phase")
    for message in coverage_gaps + lodging_verification_issues:
        if phase == "final":
            blocking.append(message)
        else:
            warnings.append(message)
    blocking = list(dict.fromkeys(blocking))
    warnings = list(dict.fromkeys(warnings))
    return {
        "status": "pass" if not blocking else "fail",
        "blocking": blocking,
        "warnings": warnings,
        "restaurant_audit": {
            "meal_slot_count": len(meals),
            "used_meal_slot_count": len(used_meal_ids),
            "candidate_reference_count": sum(len(meal.get("candidate_ids") or []) for meal in meals.values()),
            "restaurant_count": len(planning.get("restaurants") or []),
            "snapshot_count": len(planning.get("restaurant_snapshots") or []),
            "baseline_route_count": len(planning.get("meal_baseline_routes") or []),
            "route_evaluation_count": len(planning.get("meal_route_evaluations") or []),
            "community_reference_count": sum(
                len((snapshot.get("community_consensus") or {}).get("references") or [])
                for snapshot in planning.get("restaurant_snapshots") or []
            ),
            "source_registry_count": len(data.get("sources") or []),
        },
        "inventory_audit": {
            "snapshot_count": len(source_snapshots),
            "selected_reference_count": len(checked_inventory_refs),
            "purchase_refresh_snapshot_ids": sorted(purchase_refresh_snapshot_ids),
            "transport_coverage_gaps": coverage_gaps,
            "lodging_verification_issues": lodging_verification_issues,
        },
        "road_trip_audit": {
            "active": "transport.self_drive" in active_modules,
            "vehicle_count": len(vehicles),
            "plan_count": len(road_trip_plans),
            "rental_option_count": len(rental_options),
            "parking_location_count": len(parking_locations),
        },
        "checked_event_ids": checked_event_ids,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    result = audit(data)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
