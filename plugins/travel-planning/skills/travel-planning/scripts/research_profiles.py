#!/usr/bin/env python3
"""Resolve per-trip progressive research modules from a confirmed route."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = SKILL_ROOT / "registries" / "research-modules.json"
CORE_MODULES = ("attractions.core", "transport.core", "dining.core", "lodging.core")
FEATURE_KEYS = {
    "transport_modes": "transport_modes",
    "transport_mode": "transport_modes",
    "modes": "transport_modes",
    "mode": "transport_modes",
    "attraction_types": "attraction_types",
    "attraction_type": "attraction_types",
    "scenarios": "scenarios",
    "scenario": "scenarios",
}
ALIASES = {
    "transport_modes": {
        "flight": "flight", "air": "flight", "plane": "flight", "航班": "flight", "飞机": "flight",
        "rail": "rail", "train": "rail", "high_speed_rail": "rail", "高铁": "rail", "铁路": "rail", "火车": "rail",
        "public_transit": "public_transit", "transit": "public_transit", "metro": "public_transit", "bus": "public_transit", "公交": "public_transit", "地铁": "public_transit",
        "self_drive": "self_drive", "self-drive": "self_drive", "driving": "self_drive", "自驾": "self_drive",
        "car_rental": "self_drive", "rental_car": "self_drive", "租车": "self_drive",
        "charter_driver": "charter_driver", "charter": "charter_driver", "包车": "charter_driver", "包车司机": "charter_driver",
        "coach_ferry": "coach_ferry", "coach": "coach_ferry", "ferry": "coach_ferry", "大巴": "coach_ferry", "轮渡": "coach_ferry"
    },
    "attraction_types": {
        "museum_venue": "museum_venue", "museum": "museum_venue", "博物馆": "museum_venue", "展馆": "museum_venue",
        "scenic_area": "scenic_area", "景区": "scenic_area",
        "mountain_outdoor": "mountain_outdoor", "mountain": "mountain_outdoor", "hiking": "mountain_outdoor", "山岳": "mountain_outdoor", "徒步": "mountain_outdoor",
        "theme_park": "theme_park", "主题乐园": "theme_park",
        "performance_night": "performance_night", "performance": "performance_night", "night_tour": "performance_night", "演出": "performance_night", "夜游": "performance_night",
        "urban_walk": "urban_walk", "urban-walk": "urban_walk", "citywalk": "urban_walk", "city_walk": "urban_walk", "老街": "urban_walk", "古城": "urban_walk", "市场": "urban_walk", "步行街": "urban_walk", "街区漫游": "urban_walk"
    },
    "scenarios": {
        "car_rental": "car_rental", "rental_car": "car_rental", "租车": "car_rental",
        "driving_parking": "driving_parking", "自驾用餐": "driving_parking",
        "constrained_venue": "constrained_venue", "受限餐饮": "constrained_venue",
        "lodging_inventory": "lodging_inventory", "住宿库存": "lodging_inventory",
        "multi_room": "multi_room", "多间房": "multi_room",
        "late_arrival": "late_arrival", "深夜入住": "late_arrival",
        "lodging_self_drive": "lodging_self_drive", "自驾住宿": "lodging_self_drive"
    }
}


class ProfileError(RuntimeError):
    pass


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "travel-research-module-registry/v1":
        raise ProfileError("研究模块注册表版本无效")
    modules: dict[str, dict[str, Any]] = {}
    for module in payload.get("modules") or []:
        module_id = str(module.get("id") or "")
        if not module_id or module_id in modules:
            raise ProfileError(f"研究模块 ID 缺失或重复：{module_id or 'empty'}")
        guide = SKILL_ROOT / str(module.get("guide") or "")
        if not guide.is_file():
            raise ProfileError(f"研究模块缺少 guide：{module_id}")
        for schema_ref in module.get("schema_refs") or []:
            if not (SKILL_ROOT / str(schema_ref)).is_file():
                raise ProfileError(f"研究模块缺少 schema：{module_id} -> {schema_ref}")
        modules[module_id] = module
    for module_id, module in modules.items():
        for dependency in module.get("depends_on") or []:
            if dependency not in modules:
                raise ProfileError(f"研究模块依赖不存在：{module_id} -> {dependency}")
    _validate_acyclic(modules)
    for stage, guides in (payload.get("stage_guides") or {}).items():
        if not stage or not isinstance(guides, list) or not guides:
            raise ProfileError("研究阶段 guide 映射无效")
        for guide_ref in guides:
            if not (SKILL_ROOT / str(guide_ref)).is_file():
                raise ProfileError(f"研究阶段缺少 guide：{stage} -> {guide_ref}")
    return modules


def _validate_acyclic(modules: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module_id: str) -> None:
        if module_id in visiting:
            raise ProfileError(f"研究模块存在循环依赖：{module_id}")
        if module_id in visited:
            return
        visiting.add(module_id)
        for dependency in modules[module_id].get("depends_on") or []:
            visit(str(dependency))
        visiting.remove(module_id)
        visited.add(module_id)

    for module_id in modules:
        visit(module_id)


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]


def collect_features(route: dict[str, Any]) -> dict[str, set[str]]:
    features = {"transport_modes": set(), "attraction_types": set(), "scenarios": set()}
    explicit = route.get("research_features") or {}
    if isinstance(explicit, dict):
        for key in features:
            for value in _values(explicit.get(key)):
                normalized = ALIASES[key].get(value.casefold(), ALIASES[key].get(value, value.casefold()))
                features[key].add(normalized)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                feature_key = FEATURE_KEYS.get(str(key))
                if feature_key:
                    for item in _values(child):
                        normalized = ALIASES[feature_key].get(item.casefold(), ALIASES[feature_key].get(item))
                        if normalized:
                            features[feature_key].add(normalized)
                        if feature_key == "transport_modes" and (item.casefold() in {"car_rental", "rental_car"} or item == "租车"):
                            features["scenarios"].add("car_rental")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(route)
    if "car_rental" in features["scenarios"]:
        features["transport_modes"].add("self_drive")
    if "self_drive" in features["transport_modes"]:
        features["scenarios"].add("driving_parking")
    return features


def resolve_profile(route: dict[str, Any], generated_at: str | None = None) -> dict[str, Any]:
    modules = load_registry()
    features = collect_features(route)
    selected = set(CORE_MODULES)
    reasons = {module_id: "路线确认后的领域基础模块" for module_id in CORE_MODULES}
    has_structured_features = any(features.values())
    for module_id, module in modules.items():
        triggers = module.get("triggers") or {}
        for feature_key in ("transport_modes", "attraction_types", "scenarios"):
            matched = features[feature_key].intersection(str(value) for value in triggers.get(feature_key) or [])
            if matched:
                selected.add(module_id)
                reasons[module_id] = f"selected-route 激活 {feature_key}: {', '.join(sorted(matched))}"

    def add_dependencies(module_id: str) -> None:
        for dependency in modules[module_id].get("depends_on") or []:
            dependency = str(dependency)
            selected.add(dependency)
            reasons.setdefault(dependency, f"{module_id} 的依赖模块")
            add_dependencies(dependency)

    for module_id in list(selected):
        add_dependencies(module_id)
    ordered = [module_id for module_id in modules if module_id in selected]
    return {
        "schema_version": "travel-research-profile/v1",
        "selected_route_id": str(route.get("id") or ""),
        "modules": ordered,
        "reasons": {module_id: reasons[module_id] for module_id in ordered},
        "compatibility_mode": "structured" if has_structured_features else "legacy_core_only",
        "generated_at": generated_at or now(),
    }


def modules_for_assignment(profile: dict[str, Any], domain: str) -> dict[str, list[str]]:
    registry = load_registry()
    profile_modules = [str(value) for value in profile.get("modules") or []]
    unknown = sorted(set(profile_modules) - set(registry))
    if unknown:
        raise ProfileError(f"research profile 包含未知模块：{', '.join(unknown)}")
    selected_set = set(profile_modules)
    for module_id in profile_modules:
        missing = sorted(
            set(str(value) for value in registry[module_id].get("depends_on") or []) - selected_set
        )
        if missing:
            raise ProfileError(f"research profile 缺少 {module_id} 的依赖：{', '.join(missing)}")
    selected = []
    guides = []
    schema_refs = []
    completion_checks = []
    for module_id in profile_modules:
        module = registry[module_id]
        if domain not in (module.get("applies_to_domains") or []):
            continue
        selected.append(module_id)
        guides.append(str(module["guide"]))
        schema_refs.extend(str(value) for value in module.get("schema_refs") or [])
        completion_checks.extend(str(value) for value in module.get("completion_checks") or [])
    return {
        "required_modules": selected,
        "required_guides": list(dict.fromkeys(guides)),
        "schema_refs": list(dict.fromkeys(schema_refs)),
        "completion_checks": list(dict.fromkeys(completion_checks)),
    }


def guides_for_stage(stage: str | None, path: Path = REGISTRY_PATH) -> list[str]:
    """Return deterministic guides for a staged workflow after validating the registry."""
    load_registry(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [str(value) for value in (payload.get("stage_guides") or {}).get(str(stage or ""), [])]
