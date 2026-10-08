from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "travel-planning"
MODULE_PATH = SKILL_ROOT / "scripts" / "audit_itinerary.py"
SPEC = importlib.util.spec_from_file_location("audit_itinerary", MODULE_PATH)
assert SPEC and SPEC.loader
audit_itinerary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_itinerary)


def add_expired_inventory(data: dict) -> str:
    snapshot_id = "0123456789abcdef01234567"
    data["planning"]["source_snapshots"] = [{
        "schema_version": "travel-source-snapshot/v1", "snapshot_id": snapshot_id,
        "snapshot_kind": "quote", "status": "platform_reported",
        "provider": {"id": "fliggy_flyai", "name": "飞猪 FlyAI"},
        "product_type": "flight", "tool": "search-flight", "query": {},
        "freshness": {"checked_at": "2000-01-01T10:00:00+08:00", "expires_at": "2000-01-01T10:30:00+08:00", "dynamic": True},
        "items": [{"offer_id": "mu1", "name": "MU1", "price": {"display": "¥500"}, "availability": {}, "action_link": None}],
        "count": 1, "raw_response_hash": "sha256:" + "a" * 64,
        "source": {"title": "飞猪", "url": "https://example.com", "kind": "official_platform_api"}, "disclaimer": "复核",
    }]
    route = next(item for item in data["planning"]["transport_edges"] if item["id"] == "r1")
    route["inventory_refs"] = [{"snapshot_id": snapshot_id, "offer_id": "mu1", "role": "candidate_quote"}]
    return snapshot_id


class AuditItineraryTest(unittest.TestCase):
    def load_example(self) -> dict:
        return json.loads((SKILL_ROOT / "assets" / "example-itinerary.json").read_text(encoding="utf-8"))

    def test_example_passes(self) -> None:
        result = audit_itinerary.audit(self.load_example())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["blocking"], [])
        self.assertEqual(result["restaurant_audit"]["used_meal_slot_count"], 3)
        self.assertEqual(result["restaurant_audit"]["restaurant_count"], 5)

    def test_detects_time_overlap(self) -> None:
        data = self.load_example()
        data["days"][0]["events"][2]["time"] = "10:00"
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("时间重叠" in item for item in result["blocking"]))

    def test_detects_missing_meal_in_active_window(self) -> None:
        data = self.load_example()
        data["days"][0]["events"] = [event for event in data["days"][0]["events"] if event["type"] != "meal"]
        data["days"][0]["events"][-1]["end_time"] = "13:00"
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("午餐窗口" in item for item in result["blocking"]))

    def test_meal_exemption_is_explicit(self) -> None:
        data = self.load_example()
        data["days"][0]["events"] = [event for event in data["days"][0]["events"] if event["type"] != "meal"]
        data["days"][0]["events"][-1]["end_time"] = "13:00"
        data["days"][0]["meal_exemptions"] = {"午餐": "12:00 前结束正式活动，用户自行安排"}
        result = audit_itinerary.audit(data)
        self.assertFalse(any("午餐窗口" in item for item in result["blocking"]))

    def test_detects_internal_checkpoint_overlap(self) -> None:
        data = self.load_example()
        data["days"][0]["events"][1]["execution"]["checkpoints"][1]["time"] = "09:20"
        result = audit_itinerary.audit(data)
        self.assertTrue(any("节点时间重叠" in item for item in result["blocking"]))

    def test_detects_meal_event_outside_researched_time_window(self) -> None:
        data = self.load_example()
        meal_event = next(event for event in data["days"][0]["events"] if event.get("meal_id") == "m1")
        meal_event["time"] = "13:20"
        meal_event["end_time"] = "14:20"
        result = audit_itinerary.audit(data)
        self.assertTrue(any("超出 meal_option.time_window" in item for item in result["blocking"]))

    def test_warns_about_unbound_meal_research(self) -> None:
        data = self.load_example()
        data["planning"]["meal_options"].append({"id": "unused-meal"})
        result = audit_itinerary.audit(data)
        self.assertTrue(any("未绑定" in item and "unused-meal" in item for item in result["warnings"]))

    def test_note_cannot_occupy_an_activity_window(self) -> None:
        data = self.load_example()
        data["days"][0]["events"].append({
            "id": "event-citywalk-as-note",
            "time": "20:00",
            "end_time": "22:00",
            "type": "note",
            "title": "老街慢走",
        })
        result = audit_itinerary.audit(data)
        self.assertTrue(any("不能用 end_time 占据持续时间窗" in item for item in result["blocking"]))

    def test_event_description_is_blocked_before_renderer_can_drop_it(self) -> None:
        data = self.load_example()
        data["days"][0]["events"][0]["description"] = "页面不会展示这段内容"
        result = audit_itinerary.audit(data)
        self.assertTrue(any("renderer 不展示的 description" in item for item in result["blocking"]))

    def test_urban_walk_requires_multiple_checkpoints_with_visible_content(self) -> None:
        data = self.load_example()
        event = data["days"][0]["events"][1]
        attraction = data["planning"]["attractions"][0]
        attraction["attraction_type"] = "urban_walk"
        event["execution"]["checkpoints"] = [event["execution"]["checkpoints"][0]]
        event["execution"]["checkpoints"][0].pop("narration", None)
        result = audit_itinerary.audit(data)
        self.assertTrue(any("至少需要两个 checkpoints" in item for item in result["blocking"]))
        self.assertTrue(any("缺少具体现场看点 narration" in item for item in result["blocking"]))

    def test_detects_missing_transport_between_distinct_locations(self) -> None:
        data = self.load_example()
        data["days"][1]["events"] = [
            event for event in data["days"][1]["events"] if event.get("route_id") != "r6"
        ]
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("两者之间缺少独立交通事件" in item for item in result["blocking"]))

    def test_detects_day_that_does_not_return_to_declared_end_anchor(self) -> None:
        data = self.load_example()
        data["days"][0]["events"] = [
            event for event in data["days"][0]["events"] if event.get("route_id") != "r4"
        ]
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("end_anchor 与最后地点或交通终点不一致" in item for item in result["blocking"]))

    def test_daily_route_must_bind_every_location_event(self) -> None:
        data = self.load_example()
        data["planning"]["daily_routes"][1]["stops"] = [
            stop for stop in data["planning"]["daily_routes"][1]["stops"]
            if stop.get("event_id") != "e-d2-m2"
        ]
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("每日路线图缺少地点事件 stop 绑定" in item for item in result["blocking"]))

    def test_transport_requires_distance_mode_and_fallback(self) -> None:
        data = self.load_example()
        route = next(item for item in data["planning"]["transport_edges"] if item["id"] == "r1")
        route.pop("distance_meters")
        route.pop("mode")
        route.pop("fallback")
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("缺少 distance_meters" in item for item in result["blocking"]))
        self.assertTrue(any("缺少 mode" in item for item in result["blocking"]))
        self.assertTrue(any("缺少 fallback" in item for item in result["blocking"]))

    def test_selected_restaurant_legs_must_be_timeline_transport_events(self) -> None:
        data = self.load_example()
        meal_index = next(
            index for index, event in enumerate(data["days"][1]["events"])
            if event.get("meal_id") == "m2"
        )
        data["days"][1]["events"][meal_index + 1]["route_id"] = "r3"
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("主选离店路线与相邻交通事件起终点不一致" in item for item in result["blocking"]))

    def test_expired_quote_does_not_affect_planning_delivery(self) -> None:
        data = self.load_example()
        snapshot_id = add_expired_inventory(data)
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(any("已过期" in item for item in result["warnings"]))
        self.assertEqual(result["inventory_audit"]["selected_reference_count"], 1)
        self.assertEqual(result["inventory_audit"]["purchase_refresh_snapshot_ids"], [snapshot_id])

    def test_final_plan_blocks_selected_transport_without_multi_sort_coverage(self) -> None:
        data = self.load_example()
        snapshot_id = add_expired_inventory(data)
        snapshot = next(
            item for item in data["planning"]["source_snapshots"]
            if item["snapshot_id"] == snapshot_id
        )
        snapshot["freshness"] = {
            "checked_at": "2099-01-01T10:00:00+08:00",
            "expires_at": "2099-01-01T10:30:00+08:00",
            "dynamic": True,
        }
        data["workflow"]["phase"] = "final"
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("排序覆盖" in item for item in result["blocking"]))
        self.assertTrue(result["inventory_audit"]["transport_coverage_gaps"])

    def test_self_drive_profile_requires_road_trip_plan(self) -> None:
        data = self.load_example()
        data["planning"]["research_profile"] = {"modules": ["transport.core", "transport.self_drive"]}
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("驾车地图路线不能替代自驾审查" in item for item in result["blocking"]))

    def test_valid_road_trip_references_pass_cross_entity_audit(self) -> None:
        data = self.load_example()
        data["planning"]["research_profile"] = {"modules": ["transport.core", "transport.self_drive"]}
        data["planning"]["vehicles"] = [{"id": "vehicle-1"}]
        data["planning"]["parking_locations"] = [{"id": "parking-1"}]
        data["planning"]["road_trip_plans"] = [{
            "id": "drive-1", "vehicle_id": "vehicle-1", "route_edge_ids": ["r1"],
            "parking_stops": [{"stop_id": "museum", "parking_location_id": "parking-1"}],
        }]
        result = audit_itinerary.audit(data)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["road_trip_audit"]["plan_count"], 1)


if __name__ == "__main__":
    unittest.main()
