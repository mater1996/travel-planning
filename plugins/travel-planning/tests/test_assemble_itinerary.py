from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "skills" / "travel-planning" / "scripts" / "assemble_itinerary.py"
SPEC = importlib.util.spec_from_file_location("assemble_itinerary", MODULE_PATH)
assert SPEC and SPEC.loader
assemble_itinerary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assemble_itinerary)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class AssembleItineraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "trip"
        for name in ("results", "sources", "snapshots", "state", "artifacts"):
            (self.workspace / name).mkdir(parents=True, exist_ok=True)
        write_json(self.workspace / "selected-route.json", {"id": "route-1", "status": "confirmed"})
        research = {"schema_version": "travel-research-state/v2", "trip_id": "trip", "tasks": []}
        write_json(self.workspace / "state" / "research.json", research)
        digest = hashlib.sha256((self.workspace / "state" / "research.json").read_bytes()).hexdigest()
        write_json(self.workspace / "results" / "attractions.json", {
            "task_id": "attractions",
            "source_snapshot_ids": [],
            "entities": {
                "attractions": [{
                    "id": "museum", "name": "城市博物馆",
                    "official": {
                        "physical_address": "测试路1号", "homepage_url": "https://example.com/museum",
                        "notice_url": "https://example.com/museum/notices",
                    },
                    "operations": {"opening_hours": "09:00-17:00", "last_entry": "16:00"},
                    "entrance": {"name": "南门", "location_query": "城市博物馆南门"},
                    "exit": {"name": "东门", "location_query": "城市博物馆东门"},
                    "checkpoint_blueprint": [
                        {"id": "cp-a", "name": "入口"},
                        {"id": "cp-b", "name": "主展厅"},
                    ],
                    "reservation": {"required": False, "target_date": "2026-10-03"},
                    "cost_items": [{
                        "name": "基础票", "kind": "base_ticket", "pricing_role": "baseline",
                        "unit_price_cny": 0, "subtotal_cny": 0, "quantity": 2, "status": "free",
                    }],
                }]
            },
        })
        self.plan = {
            "schema_version": "itinerary-plan/v1",
            "research_state_sha256": digest,
            "trip": {
                "title": "测试行程", "date_range": "2026-10-03", "travelers": "2位成人",
                "updated_at": "2026-09-21",
            },
            "workflow": {"phase": "confirmed_planning", "selected_route_id": "route-1"},
            "collections": {
                "attractions": {
                    "task": "attractions", "path": "entities.attractions", "ids": ["museum"]
                }
            },
            "attraction_events": {
                "museum": {
                    "event_id": "event-museum", "start": "09:00", "end": "11:00",
                    "weather_id": "weather-1", "title": "城市博物馆",
                    "checkpoint_overrides": {"cp-b": {"required": False, "instruction": "时间不足可跳过"}},
                }
            },
            "days": [{
                "date": "2026-10-03",
                "events": [{"type": "attraction", "attraction_id": "museum"}],
            }],
        }
        self.plan_path = self.workspace / "state" / "itinerary-plan.json"
        write_json(self.plan_path, self.plan)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_assembles_selected_research_and_declarative_schedule(self) -> None:
        result = assemble_itinerary.assemble(self.workspace, self.plan_path)
        self.assertEqual(result["workflow"]["selected_route_id"], "route-1")
        self.assertEqual([item["id"] for item in result["planning"]["attractions"]], ["museum"])
        event = result["days"][0]["events"][0]
        self.assertEqual(event["id"], "event-museum")
        self.assertEqual(event["execution"]["entry"]["name"], "南门")
        self.assertFalse(event["execution"]["checkpoints"][1]["required"])
        self.assertEqual(event["execution"]["checkpoints"][1]["instruction"], "时间不足可跳过")
        self.assertNotIn("narration", event["execution"]["checkpoints"][0])
        self.assertNotIn("narration", event["execution"]["checkpoints"][1])
        self.assertEqual(result["planning"]["booking_tasks"][0]["event_id"], "event-museum")

    def test_keeps_researched_checkpoint_narration(self) -> None:
        task = json.loads((self.workspace / "results" / "attractions.json").read_text(encoding="utf-8"))
        task["entities"]["attractions"][0]["checkpoint_blueprint"][0]["narration"] = "观察主展厅入口保留的建筑构件。"
        write_json(self.workspace / "results" / "attractions.json", task)
        result = assemble_itinerary.assemble(self.workspace, self.plan_path)
        checkpoint = result["days"][0]["events"][0]["execution"]["checkpoints"][0]
        self.assertEqual(checkpoint["narration"], "观察主展厅入口保留的建筑构件。")

    def test_uses_verified_wechat_guide_for_booking_actions(self) -> None:
        task = json.loads((self.workspace / "results" / "attractions.json").read_text(encoding="utf-8"))
        attraction = task["entities"]["attractions"][0]
        attraction["reservation"] = {
            "required": True,
            "target_date": "2026-10-03",
            "action": "在微信公众号内预约",
        }
        attraction["official"]["wechat"] = {
            "account_name": "城市博物馆",
            "menu_path": "参观服务 → 预约",
            "guide_url": "https://mp.weixin.qq.com/s/museum-guide",
            "checked_at": "2026-09-22",
        }
        write_json(self.workspace / "results" / "attractions.json", task)
        result = assemble_itinerary.assemble(self.workspace, self.plan_path)
        event = result["days"][0]["events"][0]
        booking = result["planning"]["booking_tasks"][0]
        self.assertEqual(event["action_links"][0]["url"], "https://mp.weixin.qq.com/s/museum-guide")
        self.assertEqual(booking["action_links"][0]["type"], "official_wechat")
        self.assertEqual(booking["action_links"][0]["label"], "打开公众号预约说明")

    def test_rejects_plan_after_research_state_changes(self) -> None:
        write_json(self.workspace / "state" / "research.json", {
            "schema_version": "travel-research-state/v2", "trip_id": "trip", "tasks": ["changed"]
        })
        with self.assertRaisesRegex(assemble_itinerary.AssemblyError, "plan 已过期"):
            assemble_itinerary.assemble(self.workspace, self.plan_path)

    def test_rejects_missing_selected_entity(self) -> None:
        self.plan["collections"]["attractions"]["ids"] = ["missing"]
        write_json(self.plan_path, self.plan)
        with self.assertRaisesRegex(assemble_itinerary.AssemblyError, "缺少选定实体"):
            assemble_itinerary.assemble(self.workspace, self.plan_path)

    def test_rejects_generated_candidate_before_agent_review(self) -> None:
        self.plan["workflow"]["plan_status"] = "candidate"
        write_json(self.plan_path, self.plan)
        with self.assertRaisesRegex(assemble_itinerary.AssemblyError, "仍是 candidate"):
            assemble_itinerary.assemble(self.workspace, self.plan_path)

    def test_carries_research_profile_and_road_trip_collections(self) -> None:
        write_json(self.workspace / "results" / "road-trip.json", {
            "task_id": "road-trip",
            "source_snapshot_ids": [],
            "entities": {
                "vehicles": [{"id": "vehicle-1"}],
                "road_trip_plans": [{"id": "drive-1", "vehicle_id": "vehicle-1"}],
                "rental_options": [],
                "parking_locations": [{"id": "parking-1"}],
            },
        })
        research = json.loads((self.workspace / "state" / "research.json").read_text(encoding="utf-8"))
        research["research_profile"] = {
            "schema_version": "travel-research-profile/v1",
            "modules": ["transport.core", "transport.self_drive"],
        }
        write_json(self.workspace / "state" / "research.json", research)
        self.plan["research_state_sha256"] = hashlib.sha256(
            (self.workspace / "state" / "research.json").read_bytes()
        ).hexdigest()
        self.plan["collections"]["vehicles"] = {
            "task": "road-trip", "path": "entities.vehicles", "ids": ["vehicle-1"]
        }
        self.plan["collections"]["road_trip_plans"] = {
            "task": "road-trip", "path": "entities.road_trip_plans", "ids": ["drive-1"]
        }
        self.plan["collections"]["parking_locations"] = {
            "task": "road-trip", "path": "entities.parking_locations", "ids": ["parking-1"]
        }
        write_json(self.plan_path, self.plan)

        result = assemble_itinerary.assemble(self.workspace, self.plan_path)
        self.assertEqual(result["planning"]["research_profile"]["modules"], ["transport.core", "transport.self_drive"])
        self.assertEqual(result["planning"]["road_trip_plans"][0]["id"], "drive-1")

    def test_deep_merge_replaces_lists_and_merges_objects(self) -> None:
        result = assemble_itinerary.deep_merge(
            {"nested": {"keep": 1, "replace": 2}, "items": [1, 2]},
            {"nested": {"replace": 3}, "items": [4]},
        )
        self.assertEqual(result, {"nested": {"keep": 1, "replace": 3}, "items": [4]})


if __name__ == "__main__":
    unittest.main()
