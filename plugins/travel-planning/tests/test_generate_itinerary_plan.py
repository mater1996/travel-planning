from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "skills" / "travel-planning" / "scripts" / "generate_itinerary_plan.py"
SPEC = importlib.util.spec_from_file_location("generate_itinerary_plan", MODULE_PATH)
assert SPEC and SPEC.loader
generate_itinerary_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_itinerary_plan)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class GenerateItineraryPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "trip"
        for name in ("results", "state"):
            (self.workspace / name).mkdir(parents=True, exist_ok=True)
        write_json(self.workspace / "brief.json", {
            "destination": "测试城",
            "date_range": "2026-10-03 至 2026-10-04",
            "travelers": "2位成人",
            "budget": "中等",
            "updated_at": "2026-09-22T10:00:00+08:00",
        })
        write_json(self.workspace / "selected-route.json", {
            "id": "route-1",
            "title": "测试路线",
            "selected_at": "2026-09-22T09:00:00+08:00",
            "fixed_plan": [
                {"date": "2026-10-03", "city": "甲城", "intent": "甲城完整日"},
                {"date": "2026-10-04", "city": "乙城", "intent": "乙城返程日"},
            ],
        })
        write_json(self.workspace / "route-proposals.json", [{"id": "route-1", "title": "测试路线"}])
        write_json(self.workspace / "results" / "attractions.json", {
            "entities": {"attractions": [{
                "id": "museum", "name": "测试博物馆",
                "checkpoint_blueprint": [
                    {"id": "entry", "name": "入口", "duration_minutes": 30},
                    {"id": "gallery", "name": "展厅", "duration_minutes": 60},
                ],
                "reservation": {"target_date": "2026-10-03"},
            }]},
            "event_bindings": [{
                "day_id": "day-2026-10-03",
                "target": {"type": "attraction", "entity_id": "museum"},
                "event_patch": {"preferred_window": "09:00-11:00"},
            }],
        })
        write_json(self.workspace / "results" / "route-data.json", {
            "entities": {
                "transport_edges": [{"id": "edge-airport-hotel", "from": "机场", "to": "酒店"}],
                "intercity_options": [{
                    "id": "flight-1", "date": "2026-10-04", "recommended": True,
                    "from": "乙城机场", "to": "家", "departure_at": "2026-10-04T18:00:00+08:00",
                    "arrival_at": "2026-10-04T20:00:00+08:00",
                }],
            },
            "event_bindings": [{
                "day_id": "day-2026-10-03", "target": {"type": "day", "entity_id": "day-2026-10-03"},
                "event_patch": {"arrival_ground_edge_id": "edge-airport-hotel"},
            }],
        })
        write_json(self.workspace / "results" / "stay-food.json", {
            "entities": {
                "lodging_options": [{
                    "id": "hotel-1", "rank": 1, "name": "测试酒店",
                    "check_in": "2026-10-03", "check_out": "2026-10-04",
                }],
                "meal_options": [{"id": "old-meal-window", "date": "2026-10-03"}],
            },
        })
        write_json(self.workspace / "results" / "restaurant-ranking.json", {
            "entities": {"meal_options": [{
                "id": "meal-lunch", "date": "2026-10-03", "meal_type": "lunch",
                "time_window": "12:00-13:00", "name": "午餐",
            }]},
        })
        write_json(self.workspace / "results" / "weather-risk.json", {
            "entities": {"weather": [{"id": "weather-day-1", "date": "2026-10-03"}]},
        })
        write_json(self.workspace / "results" / "road-trip.json", {
            "entities": {
                "vehicles": [{"id": "vehicle-1", "energy_type": "electric"}],
                "road_trip_plans": [{"id": "road-trip-1", "vehicle_id": "vehicle-1"}],
                "rental_options": [{"id": "rental-1", "vehicle_id": "vehicle-1"}],
                "parking_locations": [{"id": "parking-1"}],
            },
        })
        write_json(self.workspace / "state" / "research.json", {
            "schema_version": "travel-research-state/v2",
            "trip_id": "trip",
            "merged_at": "2026-09-22T10:30:00+08:00",
            "tasks": [
                {"task_id": "attractions", "domain": "attractions", "stage": None, "result_path": "results/attractions.json"},
                {"task_id": "route-data", "domain": "route-data", "stage": None, "result_path": "results/route-data.json"},
                {"task_id": "stay-food", "domain": "stay-food", "stage": None, "result_path": "results/stay-food.json"},
                {"task_id": "restaurant-ranking", "domain": "restaurant-research", "stage": "restaurant_ranking", "result_path": "results/restaurant-ranking.json"},
                {"task_id": "weather-risk", "domain": "weather-risk", "stage": None, "result_path": "results/weather-risk.json"},
                {"task_id": "road-trip", "domain": "road-trip", "stage": None, "result_path": "results/road-trip.json"},
            ],
        })
        self.base_path = self.workspace / "state" / "itinerary-plan.base.json"
        self.decisions_path = self.workspace / "state" / "planning-decisions.json"
        self.output_path = self.workspace / "state" / "itinerary-plan.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_generate(self, **options: object) -> dict[str, object]:
        return generate_itinerary_plan.generate(
            self.workspace,
            self.base_path,
            self.decisions_path,
            self.output_path,
            **options,
        )

    def test_generates_candidate_base_decisions_and_materialized_plan(self) -> None:
        result = self.run_generate()
        self.assertEqual(result["plan_status"], "candidate")
        base = json.loads(self.base_path.read_text(encoding="utf-8"))
        decisions = json.loads(self.decisions_path.read_text(encoding="utf-8"))
        plan = json.loads(self.output_path.read_text(encoding="utf-8"))

        self.assertEqual(base["collections"]["meal_options"]["task"], "restaurant-ranking")
        self.assertEqual(base["collections"]["road_trip_plans"]["task"], "road-trip")
        self.assertEqual(base["collections"]["rental_options"]["task"], "road-trip")
        self.assertEqual(plan["workflow"]["selected_route_id"], "route-1")
        self.assertEqual(plan["planning"]["route_continuity_version"], 1)
        self.assertEqual(set(decisions["days"]), {"2026-10-03", "2026-10-04"})
        self.assertEqual(plan["attraction_events"]["museum"]["weather_id"], "weather-day-1")
        day_one = plan["days"][0]["events"]
        self.assertTrue(any(item.get("meal_id") == "meal-lunch" for item in day_one))
        self.assertTrue(any(item.get("route_id") == "edge-airport-hotel" for item in day_one))
        self.assertTrue(any(item.get("lodging_id") == "hotel-1" for item in day_one))
        self.assertTrue(plan["generation"]["pending_decisions"])
        self.assertTrue(any(
            item.get("id") == "review-route-continuity-2026-10-03"
            for item in plan["generation"]["pending_decisions"]
        ))

    def test_agent_decisions_are_small_overlays_and_survive_regeneration(self) -> None:
        self.run_generate()
        decisions = json.loads(self.decisions_path.read_text(encoding="utf-8"))
        decisions["workflow"]["plan_status"] = "reviewed"
        decisions["attraction_events"]["museum"] = {"start": "09:30", "end": "11:30"}
        decisions["days"]["2026-10-03"]["event_overrides"]["event-meal-meal-lunch"] = {
            "title": "已复核午餐"
        }
        write_json(self.decisions_path, decisions)

        result = self.run_generate()
        plan = json.loads(self.output_path.read_text(encoding="utf-8"))
        self.assertEqual(result["plan_status"], "reviewed")
        self.assertEqual(plan["attraction_events"]["museum"]["start"], "09:30")
        meal = next(item for item in plan["days"][0]["events"] if item.get("meal_id") == "meal-lunch")
        self.assertEqual(meal["title"], "已复核午餐")

    def test_rejects_stale_decisions_after_research_changes(self) -> None:
        self.run_generate()
        research = json.loads((self.workspace / "state" / "research.json").read_text(encoding="utf-8"))
        research["merged_at"] = "2026-09-22T11:00:00+08:00"
        write_json(self.workspace / "state" / "research.json", research)
        with self.assertRaisesRegex(generate_itinerary_plan.PlanGenerationError, "planning-decisions 已过期"):
            self.run_generate()

    def test_does_not_overwrite_a_manual_plan_without_force(self) -> None:
        write_json(self.output_path, {"schema_version": "itinerary-plan/v1", "manual": True})
        with self.assertRaisesRegex(generate_itinerary_plan.PlanGenerationError, "拒绝覆盖非生成计划"):
            self.run_generate()


if __name__ == "__main__":
    unittest.main()
