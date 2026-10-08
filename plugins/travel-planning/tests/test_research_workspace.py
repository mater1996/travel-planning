from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "skills" / "travel-planning" / "scripts" / "research_workspace.py"
SPEC = importlib.util.spec_from_file_location("research_workspace", MODULE_PATH)
assert SPEC and SPEC.loader
research_workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_workspace)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def inventory_snapshot(snapshot_id: str = "0123456789abcdef01234567") -> dict:
    return {
        "schema_version": "travel-source-snapshot/v1",
        "snapshot_id": snapshot_id,
        "snapshot_kind": "quote",
        "status": "platform_reported",
        "provider": {
            "id": "fliggy_flyai", "name": "飞猪 FlyAI", "authority": "official_platform",
            "transport": "cli_to_vendor_mcp_api", "package": "@fly-ai/flyai-cli", "version": "1.0.16",
        },
        "product_type": "train",
        "tool": "search-train",
        "query": {"origin": "上海", "destination": "杭州", "dep_date": "2026-10-03"},
        "freshness": {
            "checked_at": "2026-09-21T10:00:00+08:00",
            "expires_at": "2026-09-21T10:30:00+08:00",
            "dynamic": True,
        },
        "items": [{
            "offer_id": "g1234-second", "name": "G1234", "price": {"amount": 73.0, "currency": "CNY", "display": "¥73", "basis": "per_adult"},
            "availability": {"status": "provider_returned", "remaining": None}, "action_link": "https://example.com/train/g1234",
        }],
        "count": 1,
        "raw_response_hash": "sha256:" + "a" * 64,
        "source": {"title": "飞猪 FlyAI", "url": "https://github.com/alibaba-flyai/flyai-skill", "kind": "official_platform_api"},
        "disclaimer": "查询时快照，下单前复核",
    }


class ResearchWorkspaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        args = Namespace(
            trip_id="hangzhou-2026-10",
            root=str(self.root),
            destination="杭州",
            date_range="2026-10-03 至 2026-10-05",
            travelers="2 位成人",
            origin="上海",
            budget="中等",
            preferences=["人文"],
            constraints=[],
            brief_file=None,
        )
        result = research_workspace.init_workspace(args)
        self.workspace = Path(result["workspace"])
        route_file = self.root / "route.json"
        write_json(route_file, {"id": "route-1", "cities": ["杭州"], "status": "confirmed"})
        research_workspace.select_route(Namespace(workspace=str(self.workspace), route_file=str(route_file)))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_assignment_submission_and_merge(self) -> None:
        assignment = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="transport",
                domain="transport",
                instructions="比较铁路与包车",
                depends_on=None,
            )
        )["assignment"]
        result_file = self.root / "result.json"
        sources_file = self.root / "sources.json"
        write_json(result_file, {
            "schema_version": assignment["result_schema_version"],
            "template_version": assignment["template_version"],
            "template_digest": assignment["template_digest"],
            "status": "complete",
            "input_revision": assignment["input_revision"],
            "summary": "包车换乘少",
            "entities": {"transport_edges": [{"id": "transport-edge-1"}]},
            "shared_entities": [{
                "entity_id": "hub-hangzhou-east",
                "entity_type": "transport_hub",
                "canonical_name": "杭州东站",
                "facts": {"city": "杭州"},
                "source_ids": ["transport-source-1"],
            }],
            "event_bindings": [],
            "constraints": [],
            "unresolved": [],
            "source_ids": ["transport-source-1"],
        })
        write_json(
            sources_file,
            [
                {
                    "id": "transport-source-1",
                    "title": "杭州交通官方入口",
                    "url": "https://example.com/official",
                    "kind": "transport_official",
                    "location": "杭州",
                    "topic": "公共交通",
                    "tags": ["hangzhou", "transport"],
                    "freshness": "stable",
                }
            ],
        )
        research_workspace.submit(
            Namespace(
                workspace=str(self.workspace),
                task_id="transport",
                result_file=str(result_file),
                sources_file=str(sources_file),
            )
        )
        merged = research_workspace.merge(Namespace(workspace=str(self.workspace), allow_partial=False))
        self.assertEqual(merged["result_count"], 1)
        self.assertEqual(merged["source_count"], 1)
        self.assertEqual(merged["archive_count"], 1)
        self.assertEqual(merged["shared_entity_count"], 1)
        self.assertEqual(merged["shared_entity_conflict_count"], 0)
        state = json.loads((self.workspace / "state" / "research.json").read_text(encoding="utf-8"))
        self.assertEqual(state["schema_version"], "travel-research-state/v2")
        self.assertEqual(state["tasks"][0]["task_id"], "transport")
        self.assertEqual(state["tasks"][0]["result_path"], "results/transport.json")
        self.assertNotIn("entities", state["tasks"][0])
        self.assertEqual(state["global_state"]["shared_entities"][0]["entity_id"], "hub-hangzhou-east")
        self.assertEqual(state["global_state"]["shared_entities"][0]["origin_task_ids"], ["transport"])
        self.assertEqual(state["global_state"]["conflicts"], [])
        self.assertEqual(state["indexes"]["source_snapshots"], "state/source-snapshots.json")
        self.assertNotIn("source_snapshots", state)
        archive = json.loads((self.workspace / "state" / "archive.json").read_text(encoding="utf-8"))
        self.assertEqual(archive["records"][0]["freshness"], "stable")

    def test_merge_revalidates_persisted_result(self) -> None:
        assignment = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace), task_id="weather", domain="weather",
                instructions="查天气", depends_on=None,
            )
        )["assignment"]
        result_file = self.root / "weather-result.json"
        write_json(result_file, {
            "schema_version": assignment["result_schema_version"],
            "template_version": assignment["template_version"],
            "template_digest": assignment["template_digest"],
            "status": "complete",
            "input_revision": assignment["input_revision"],
            "summary": "天气结果",
            "entities": {"weather": []},
            "shared_entities": [], "event_bindings": [], "constraints": [],
            "unresolved": [], "source_ids": [],
        })
        research_workspace.submit(Namespace(
            workspace=str(self.workspace), task_id="weather",
            result_file=str(result_file), sources_file=None,
        ))
        persisted = self.workspace / "results" / "weather.json"
        tampered = json.loads(persisted.read_text(encoding="utf-8"))
        del tampered["unresolved"]
        write_json(persisted, tampered)

        with self.assertRaisesRegex(research_workspace.WorkspaceError, "result.unresolved"):
            research_workspace.merge(Namespace(workspace=str(self.workspace), allow_partial=False))

    def test_merge_includes_main_agent_sources(self) -> None:
        source = {
            "id": "main-route-notice",
            "task_id": "main",
            "title": "路线公告",
            "url": "https://example.com/route-notice",
            "kind": "official",
            "checked_at": "2026-09-21T10:00:00+08:00",
            "freshness": "dynamic",
        }
        (self.workspace / "sources" / "main.jsonl").write_text(
            json.dumps(source, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        merged = research_workspace.merge(Namespace(workspace=str(self.workspace), allow_partial=False))
        self.assertEqual(merged["source_count"], 1)
        state = json.loads((self.workspace / "state" / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual(state["sources"][0]["id"], "main-route-notice")

    def test_merge_canonicalizes_duplicate_shared_entities(self) -> None:
        for task_id, submitted_at, code, aliases in (
            ("transport-a", "2026-09-21T10:00:00+08:00", "HZD", ["杭州东"]),
            ("transport-b", "2026-09-21T11:00:00+08:00", "HGH-E", ["杭州东站"]),
        ):
            assignment = research_workspace.assign(
                Namespace(
                    workspace=str(self.workspace), task_id=task_id, domain="transport",
                    instructions="核验交通枢纽", depends_on=None,
                )
            )["assignment"]
            result_file = self.root / f"{task_id}-result.json"
            write_json(result_file, {
                "schema_version": assignment["result_schema_version"],
                "template_version": assignment["template_version"],
                "template_digest": assignment["template_digest"],
                "status": "complete",
                "input_revision": assignment["input_revision"],
                "summary": "交通枢纽",
                "entities": {"transport_edges": []},
                "shared_entities": [{
                    "entity_id": "hub-hangzhou-east",
                    "entity_type": "transport_hub",
                    "canonical_name": "杭州东站",
                    "aliases": aliases,
                    "facts": {"station_code": code, "city": "杭州"},
                    "source_ids": [],
                }],
                "event_bindings": [], "constraints": [], "unresolved": [], "source_ids": [],
            })
            research_workspace.submit(Namespace(
                workspace=str(self.workspace), task_id=task_id,
                result_file=str(result_file), sources_file=None,
            ))
            persisted = self.workspace / "results" / f"{task_id}.json"
            payload = json.loads(persisted.read_text(encoding="utf-8"))
            payload["submitted_at"] = submitted_at
            write_json(persisted, payload)

        merged = research_workspace.merge(Namespace(workspace=str(self.workspace), allow_partial=False))
        self.assertEqual(merged["shared_entity_count"], 1)
        self.assertEqual(merged["shared_entity_conflict_count"], 1)
        state = json.loads((self.workspace / "state" / "research.json").read_text(encoding="utf-8"))
        entity = state["global_state"]["shared_entities"][0]
        self.assertEqual(entity["facts"]["station_code"], "HGH-E")
        self.assertEqual(entity["aliases"], ["杭州东", "杭州东站"])
        self.assertEqual(entity["origin_task_ids"], ["transport-a", "transport-b"])
        conflict = state["global_state"]["conflicts"][0]
        self.assertEqual(conflict["field"], "facts.station_code")
        self.assertEqual(conflict["resolution"], "latest_submission_wins")

    def test_assignment_declares_task_write_ownership(self) -> None:
        assigned = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="weather",
                domain="weather",
                instructions="查天气",
                depends_on=None,
            )
        )["assignment"]
        self.assertEqual(assigned["source_id_prefix"], "weather-")
        self.assertIn("results/weather.json", assigned["owned_paths"])
        self.assertIn("snapshots/weather/", assigned["owned_paths"])
        self.assertIn("artifacts/", assigned["forbidden_paths"])
        self.assertIn("assignments/weather.json", assigned["input_paths"])
        self.assertEqual(assigned["read_first"], ["manifest.json", "brief.json", "route-context.json", "selected-route.json", "research-profile.json"])
        self.assertEqual(assigned["required_modules"], [])
        self.assertEqual(assigned["required_guides"], [])
        self.assertIn("route-context.json", assigned["forbidden_paths"])
        self.assertTrue(assigned["result_template"].endswith("weather.result-template.json"))
        self.assertIn("shared_entities", assigned["shared_state_policy"])
        self.assertEqual(len(assigned["input_revision"]), 64)

    def test_transport_assignment_materializes_profile_guides(self) -> None:
        route_file = self.root / "route-with-rail.json"
        write_json(route_file, {
            "id": "route-rail",
            "research_features": {"transport_modes": ["rail"]},
        })
        research_workspace.select_route(Namespace(workspace=str(self.workspace), route_file=str(route_file)))
        assigned = research_workspace.assign(Namespace(
            workspace=str(self.workspace), task_id="rail-plan", domain="transport-intercity",
            instructions="比较铁路候选", depends_on=None,
        ))["assignment"]
        self.assertEqual(assigned["required_modules"], ["transport.core", "transport.rail"])
        self.assertIn("references/transport/index.md", assigned["required_guides"])
        self.assertIn("references/transport/rail.md", assigned["required_guides"])
        self.assertIn("rail_verification", assigned["completion_checks"])
        self.assertIn("transport.rail", assigned["module_reasons"])
        self.assertIn("skill:references/transport/rail.md", assigned["revision_inputs"])
        self.assertIn("skill:registries/research-modules.json", assigned["revision_inputs"])

    def test_road_trip_complete_requires_profile_fields(self) -> None:
        assignment = {
            "domain": "road-trip",
            "required_modules": ["transport.core", "transport.self_drive", "transport.car_rental"],
        }
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "road_trip_plans"):
            research_workspace.validate_profile_completion(assignment, {
                "status": "complete", "entities": {"road_trip_plans": [], "rental_options": []},
            })

    def test_complete_road_trip_accepts_structured_self_drive_and_rental_contracts(self) -> None:
        assignment = {
            "domain": "road-trip",
            "required_modules": ["transport.core", "transport.self_drive", "transport.car_rental"],
        }
        research_workspace.validate_profile_completion(assignment, {
            "status": "complete",
            "entities": {
                "road_trip_plans": [{
                    "id": "drive-1", "vehicle_id": "vehicle-1", "route_edge_ids": ["edge-1"],
                    "drivers": [{"id": "driver-1", "eligible": True}],
                    "driving_duration": {
                        "total_minutes": 240, "max_continuous_minutes": 120,
                        "rest_plan": [{"after_minutes": 120}],
                    },
                    "road_restrictions": [{"rule": "按适用日期复核"}],
                    "parking_stops": [{"stop_id": "spot-1", "parking_location_id": "parking-1"}],
                    "energy_plan": {
                        "energy_type": "gasoline", "primary": {"station": "A"},
                        "fallback": {"station": "B"},
                    },
                    "emergency_plan": {
                        "roadside_assistance": {"channel": "rental-company"},
                        "route_failure_fallback": {"mode": "rail"},
                    },
                    "source_ids": ["road-trip-source-1"],
                }],
                "rental_options": [{
                    "id": "rental-1", "vehicle_id": "vehicle-1",
                    "pickup": {
                        "location": {"name": "机场门店"},
                        "event_at": "2026-10-03T10:00:00+08:00", "opening_hours": "08:00-22:00",
                    },
                    "return": {
                        "location": {"name": "车站门店"},
                        "event_at": "2026-10-05T16:00:00+08:00", "opening_hours": "08:00-20:00",
                    },
                    "driver_requirements": {"minimum_age": 21}, "price": {"amount": 900},
                    "deposit": {"amount": 3000}, "insurance": {"excess": 1000},
                    "fuel_or_charge_policy": {"policy": "same-to-same"},
                    "mileage_policy": {"unlimited": True}, "cancellation": {"deadline": "取车前24小时"},
                    "source_ids": ["road-trip-source-1"],
                }],
            },
        })

    def test_car_rental_quotes_bind_only_to_rental_options(self) -> None:
        snapshot = inventory_snapshot()
        snapshot["product_type"] = "car_rental"
        result = {
            "domain": "road-trip",
            "entities": {"rental_options": [{
                "id": "rental-1",
                "inventory_refs": [{
                    "snapshot_id": snapshot["snapshot_id"], "offer_id": "g1234-second",
                    "role": "candidate_quote",
                }],
            }]},
        }
        research_workspace.validate_inventory_bindings(result, [snapshot])
        snapshot["product_type"] = "train"
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "只能引用 car_rental"):
            research_workspace.validate_inventory_bindings(result, [snapshot])

    def test_workspace_initializes_route_context_for_bounded_community_research(self) -> None:
        context = json.loads((self.workspace / "route-context.json").read_text(encoding="utf-8"))
        self.assertEqual(context["status"], "pending")
        self.assertEqual(context["route_signals"], [])
        self.assertEqual(context["food_themes"], [])
        manifest = json.loads((self.workspace / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("route-context.json", manifest["write_ownership"]["main_agent"])

    def test_provider_snapshot_is_stored_bound_submitted_and_merged(self) -> None:
        assignment = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace), task_id="live-route", domain="route-data",
                instructions="查询并比较铁路", depends_on=None,
            )
        )["assignment"]
        snapshot = inventory_snapshot()
        stored = research_workspace.store_source_snapshot(self.workspace, "live-route", snapshot)
        self.assertEqual(stored["status"], "stored")
        result_file = self.root / "live-route-result.json"
        write_json(result_file, {
            "schema_version": assignment["result_schema_version"],
            "template_version": assignment["template_version"],
            "template_digest": assignment["template_digest"],
            "status": "complete",
            "input_revision": assignment["input_revision"],
            "summary": "铁路候选",
            "source_snapshot_ids": [snapshot["snapshot_id"]],
            "entities": {
                "transport_edges": [], "route_anchors": [], "meal_baseline_routes": [], "meal_route_evaluations": [],
                "intercity_options": [{
                    "id": "train-g1234",
                    "inventory_refs": [{"snapshot_id": snapshot["snapshot_id"], "offer_id": "g1234-second", "role": "candidate_quote"}],
                }],
            },
            "shared_entities": [], "event_bindings": [], "constraints": [], "unresolved": [], "source_ids": [],
        })
        submitted = research_workspace.submit(Namespace(
            workspace=str(self.workspace), task_id="live-route", result_file=str(result_file), sources_file=None,
        ))
        self.assertEqual(submitted["source_snapshot_count"], 1)
        merged = research_workspace.merge(Namespace(workspace=str(self.workspace), allow_partial=False))
        self.assertEqual(merged["source_snapshot_count"], 1)
        state = json.loads((self.workspace / "state" / "source-snapshots.json").read_text(encoding="utf-8"))
        self.assertEqual(state["source_snapshots"][0]["snapshot_id"], snapshot["snapshot_id"])

    def test_nonempty_quote_snapshot_must_be_bound_to_candidate(self) -> None:
        result = {
            "domain": "route-data",
            "entities": {"intercity_options": []},
        }
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "必须投影为候选并绑定"):
            research_workspace.validate_inventory_bindings(result, [inventory_snapshot()])

    def test_restaurant_assignment_uses_v5_template_and_owned_entities(self) -> None:
        assigned = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="restaurant-research",
                domain="restaurant-research",
                instructions="为每个正式用餐时段研究2至3个候选",
                depends_on=None,
            )
        )["assignment"]
        self.assertEqual(assigned["template_version"], 5)
        self.assertIn("references/dining/index.md", assigned["required_guides"])
        template = json.loads((self.workspace / assigned["result_template"]).read_text(encoding="utf-8"))
        self.assertEqual(set(template["entities"]), {"restaurants", "restaurant_snapshots", "meal_candidate_sets", "meal_options"})

    def test_staged_restaurant_assignment_adds_only_relevant_guides(self) -> None:
        assigned = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace), task_id="restaurant-discovery",
                domain="restaurant-research", instructions="发现并核验餐厅候选",
                depends_on=None,
            )
        )["assignment"]
        self.assertEqual(assigned["stage"], "restaurant_discovery")
        self.assertIn("references/dining/index.md", assigned["required_guides"])
        self.assertIn("references/dining/discovery.md", assigned["required_guides"])
        self.assertIn("references/dining/operations.md", assigned["required_guides"])
        self.assertNotIn("references/dining/ranking.md", assigned["required_guides"])
        self.assertIn("skill:references/dining/discovery.md", assigned["revision_inputs"])

    def test_stay_food_cannot_submit_restaurant_shared_entity(self) -> None:
        result = {
            "domain": "stay-food",
            "entities": {"lodging_options": [], "meal_options": []},
            "shared_entities": [{
                "entity_id": "restaurant-demo",
                "entity_type": "restaurant",
                "canonical_name": "示例餐厅",
                "facts": {
                    "physical_address": "示例地址",
                    "coordinates": "120.1,30.2",
                    "amap_poi_id": "demo-poi",
                    "signature_dishes": ["示例菜"],
                    "cuisine": ["示例菜系"],
                    "official_endpoints": {"map": "https://example.com/restaurant"},
                    "image_refs": [{
                        "kind": "link_preview",
                        "source_url": "https://example.com/restaurant/gallery",
                        "alt": "查看相册",
                        "source_label": "商家页面",
                        "checked_at": "2026-09-21",
                    }],
                },
                "source_ids": ["stay-food-restaurant-demo"],
            }],
            "event_bindings": [],
            "constraints": [],
            "unresolved": [],
            "source_ids": [],
        }
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "不能提交共享实体类型"):
            research_workspace.validate_result_contract(result)

    def test_task_source_requires_task_prefix(self) -> None:
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "任务前缀 transport-"):
            research_workspace.normalize_sources(
                [{"id": "official-1", "url": "https://example.com"}],
                "transport",
            )

    def test_deep_research_requires_selected_route(self) -> None:
        (self.workspace / "selected-route.json").unlink()
        with self.assertRaises(research_workspace.WorkspaceError):
            research_workspace.assign(
                Namespace(
                    workspace=str(self.workspace),
                    task_id="weather",
                    domain="weather",
                    instructions="查天气",
                    depends_on=None,
                )
            )

    def test_task_result_cannot_be_overwritten(self) -> None:
        assignment = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="attractions",
                domain="attractions",
                instructions="查景点",
                depends_on=None,
            )
        )["assignment"]
        result_file = self.root / "result.json"
        write_json(result_file, {
            "schema_version": assignment["result_schema_version"],
            "template_version": assignment["template_version"],
            "template_digest": assignment["template_digest"],
            "status": "complete",
            "input_revision": assignment["input_revision"],
            "entities": {},
            "shared_entities": [],
            "event_bindings": [],
            "constraints": [],
            "unresolved": [],
            "source_ids": [],
        })
        args = Namespace(
            workspace=str(self.workspace),
            task_id="attractions",
            result_file=str(result_file),
            sources_file=None,
        )
        research_workspace.submit(args)
        with self.assertRaises(research_workspace.WorkspaceError):
            research_workspace.submit(args)

    def test_rejects_report_like_result_without_merge_contract(self) -> None:
        assignment = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="food",
                domain="stay_food",
                instructions="查餐饮",
                depends_on=None,
            )
        )["assignment"]
        result_file = self.root / "report.json"
        write_json(result_file, {
            "schema_version": assignment["result_schema_version"],
            "template_version": assignment["template_version"],
            "template_digest": assignment["template_digest"],
            "status": "complete",
            "input_revision": assignment["input_revision"],
            "summary": "一篇很长的餐饮调研",
            "data": {"restaurants": []},
        })
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "result.entities"):
            research_workspace.submit(
                Namespace(
                    workspace=str(self.workspace),
                    task_id="food",
                    result_file=str(result_file),
                    sources_file=None,
                )
            )

    def test_event_binding_uses_typed_target_and_operation(self) -> None:
        valid = {
            "entities": {},
            "shared_entities": [],
            "event_bindings": [{
                "id": "weather-bind-cp-1",
                "day_id": "d1",
                "target": {"type": "checkpoint", "entity_id": "attractions-west-lake", "checkpoint_id": "cp-1"},
                "operation": "merge",
                "snapshot_ids": ["weather-snapshot-1"],
                "event_patch": {"fallback": "雨天缩短"},
                "source_ids": [],
            }],
            "constraints": [],
            "unresolved": [],
            "source_ids": [],
        }
        research_workspace.validate_result_contract(valid)
        valid["event_bindings"][0]["operation"] = "replace"
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "operation 无效"):
            research_workspace.validate_result_contract(valid)

    def test_domain_ownership_rejects_cross_domain_entities(self) -> None:
        result = {
            "domain": "weather-risk",
            "entities": {"attractions": []},
            "shared_entities": [],
            "event_bindings": [],
            "constraints": [],
            "unresolved": [],
            "source_ids": [],
        }
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "不能提交 entities 字段"):
            research_workspace.validate_result_contract(result)

    def test_weather_domain_rejects_shared_entity(self) -> None:
        candidate = {
            "entity_id": "attraction-west-lake",
            "entity_type": "attraction",
            "canonical_name": "西湖",
            "facts": {"official_endpoints": {}, "entrances": [], "checkpoint_blueprint": [], "typical_visit_duration": "2小时"},
            "source_ids": ["weather-source-1"],
        }
        result = {
            "domain": "weather-risk",
            "entities": {"weather": []},
            "shared_entities": [candidate],
            "event_bindings": [],
            "constraints": [],
            "unresolved": [],
            "source_ids": ["weather-source-1"],
        }
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "不能提交共享实体类型"):
            research_workspace.validate_result_contract(result)

    def test_assignment_dependency_must_exist(self) -> None:
        with self.assertRaises(research_workspace.WorkspaceError):
            research_workspace.assign(
                Namespace(
                    workspace=str(self.workspace),
                    task_id="audit",
                    domain="audit",
                    instructions="核验所有结果",
                    depends_on=["missing-task"],
                )
            )

    def test_assignment_dependency_must_be_submitted_and_complete(self) -> None:
        research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="restaurant-discovery",
                domain="restaurant-research",
                instructions="发现餐厅候选",
                depends_on=None,
            )
        )
        dependent_args = Namespace(
            workspace=str(self.workspace),
            task_id="route-data-meals",
            domain="route-data",
            instructions="计算餐厅双腿路线",
            depends_on=["restaurant-discovery"],
        )
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "依赖任务尚未提交"):
            research_workspace.assign(dependent_args)

        write_json(self.workspace / "results" / "restaurant-discovery.json", {"status": "partial"})
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "依赖任务尚未完成"):
            research_workspace.assign(dependent_args)

    def test_dependency_result_is_part_of_input_revision(self) -> None:
        dependency_assignment = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="restaurant-discovery",
                domain="restaurant-research",
                instructions="发现餐厅候选",
                depends_on=None,
            )
        )["assignment"]
        dependency_path = self.workspace / "results" / "restaurant-discovery.json"
        write_json(dependency_path, {
            "status": "complete",
            "task_id": "restaurant-discovery",
            "domain": "restaurant-research",
            "stage": "restaurant_discovery",
            "submitted_at": "2026-09-21T12:00:00+08:00",
            "input_revision": dependency_assignment["input_revision"],
            "template_digest": dependency_assignment["template_digest"],
            "entities": {"restaurants": []},
        })
        assignment = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="route-data-meals",
                domain="route-data",
                instructions="计算餐厅双腿路线",
                depends_on=["restaurant-discovery"],
            )
        )["assignment"]
        self.assertIn("results/restaurant-discovery.json", assignment["revision_inputs"])

        result_file = self.root / "route-data-meals-result.json"
        write_json(result_file, {
            "schema_version": assignment["result_schema_version"],
            "template_version": assignment["template_version"],
            "template_digest": assignment["template_digest"],
            "status": "complete",
            "input_revision": assignment["input_revision"],
            "entities": {},
            "shared_entities": [],
            "event_bindings": [],
            "constraints": [],
            "unresolved": [],
            "source_ids": [],
        })
        write_json(dependency_path, {"status": "complete", "entities": {"restaurants": [{"id": "changed"}]}})
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "输入文件已变化"):
            research_workspace.submit(
                Namespace(
                    workspace=str(self.workspace),
                    task_id="route-data-meals",
                    result_file=str(result_file),
                    sources_file=None,
                )
            )

    def test_restaurant_discovery_cannot_submit_empty_complete(self) -> None:
        assignment = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="restaurant-discovery",
                domain="restaurant-research",
                instructions="发现餐厅候选",
                depends_on=None,
            )
        )["assignment"]
        result_file = self.root / "empty-discovery.json"
        write_json(result_file, {
            "schema_version": assignment["result_schema_version"],
            "template_version": assignment["template_version"],
            "template_digest": assignment["template_digest"],
            "status": "complete",
            "input_revision": assignment["input_revision"],
            "entities": {"restaurants": [], "restaurant_snapshots": [], "meal_candidate_sets": [], "meal_options": []},
            "shared_entities": [],
            "event_bindings": [],
            "constraints": [],
            "unresolved": [],
            "source_ids": [],
        })
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "必须包含餐厅、动态快照和逐餐候选集"):
            research_workspace.submit(
                Namespace(workspace=str(self.workspace), task_id="restaurant-discovery", result_file=str(result_file), sources_file=None)
            )

    def test_restaurant_discovery_v5_requires_value_first_route_assessment(self) -> None:
        assignment = {"stage": "restaurant_discovery", "template_version": 5, "dependency_paths": []}
        result = {
            "status": "complete",
            "entities": {
                "restaurants": [{"id": "r1"}, {"id": "r2"}],
                "restaurant_snapshots": [
                    {"snapshot_id": "s1", "restaurant_id": "r1"},
                    {"snapshot_id": "s2", "restaurant_id": "r2"},
                ],
                "meal_candidate_sets": [{
                    "id": "meal-1",
                    "meal_intent": "destination",
                    "candidate_ids": ["r1", "r2"],
                    "candidates": [
                        {"restaurant_id": "r1", "snapshot_id": "s1", "value_assessment": {
                            "status": "supported", "route_worthy": True,
                            "summary": "近期多位作者认为值得专程前往", "source_ids": ["xhs-1", "xhs-2"],
                        }},
                        {"restaurant_id": "r2", "snapshot_id": "s2", "value_assessment": {
                            "status": "supported", "route_worthy": False,
                            "summary": "适合作为附近备选", "source_ids": ["xhs-3"],
                        }},
                    ],
                    "route_influence": {
                        "status": "review_route", "restaurant_ids": ["r1"],
                        "reason": "主候选值得成为当日路线锚点",
                    },
                    "candidate_policy": {"status": "normal", "searched_count": 4},
                    "constraints": {"max_detour_minutes": 45},
                    "previous_anchor": {"name": "A", "physical_address": "A路1号", "coordinates": "120.1,30.1"},
                    "next_anchor": {"name": "B", "physical_address": "B路1号", "coordinates": "120.2,30.2"},
                }],
            },
        }
        research_workspace.validate_stage_result(self.workspace, assignment, result)

        result["entities"]["meal_candidate_sets"][0]["candidates"][0]["value_assessment"]["source_ids"] = ["xhs-1"]
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "至少两条近期社区来源"):
            research_workspace.validate_stage_result(self.workspace, assignment, result)

    def test_audit_agent_assignment_is_rejected(self) -> None:
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "不再分配独立 audit Agent"):
            research_workspace.assign(
                Namespace(
                    workspace=str(self.workspace), task_id="audit", domain="audit",
                    instructions="独立审查", depends_on=None,
                )
            )

    def test_meal_route_stage_must_cover_all_discovery_candidates(self) -> None:
        dependency = self.workspace / "results" / "restaurant-discovery.json"
        write_json(dependency, {
            "stage": "restaurant_discovery",
            "entities": {"meal_candidate_sets": [{"id": "meal-1", "candidate_ids": ["r1", "r2"]}]},
        })
        assignment = {"stage": "meal_route_evaluation", "dependency_paths": ["results/restaurant-discovery.json"]}
        result = {
            "status": "complete",
            "entities": {
                "meal_baseline_routes": [{"meal_id": "meal-1"}],
                "meal_route_evaluations": [{"meal_id": "meal-1", "restaurant_id": "r1"}],
            },
        }
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "覆盖 discovery 的全部餐厅候选"):
            research_workspace.validate_stage_result(self.workspace, assignment, result)

    def test_restaurant_ranking_cannot_invent_or_drop_candidates(self) -> None:
        write_json(self.workspace / "results" / "restaurant-discovery.json", {
            "stage": "restaurant_discovery",
            "entities": {"meal_candidate_sets": [{"id": "meal-1", "candidate_ids": ["r1", "r2"]}]},
        })
        write_json(self.workspace / "results" / "route-data-meals.json", {
            "stage": "meal_route_evaluation",
            "entities": {"meal_route_evaluations": [{"meal_id": "meal-1", "restaurant_id": "r1"}, {"meal_id": "meal-1", "restaurant_id": "r2"}]},
        })
        assignment = {
            "stage": "restaurant_ranking",
            "dependency_paths": ["results/restaurant-discovery.json", "results/route-data-meals.json"],
        }
        result = {
            "status": "complete",
            "entities": {
                "restaurants": [], "restaurant_snapshots": [], "meal_candidate_sets": [],
                "meal_options": [{"id": "meal-1", "candidate_ids": ["r1"], "selected_candidate_id": "r1", "fallback_candidate_ids": []}],
            },
        }
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "完整覆盖 discovery 候选"):
            research_workspace.validate_stage_result(self.workspace, assignment, result)

    def test_assignment_is_invalidated_when_brief_changes(self) -> None:
        assignment = research_workspace.assign(
            Namespace(
                workspace=str(self.workspace),
                task_id="attractions",
                domain="attractions",
                instructions="查景点",
                depends_on=None,
            )
        )["assignment"]
        brief = self.workspace / "brief.json"
        payload = json.loads(brief.read_text(encoding="utf-8"))
        payload["preferences"].append("新增偏好")
        write_json(brief, payload)
        result_file = self.root / "stale-result.json"
        write_json(result_file, {
            "schema_version": assignment["result_schema_version"],
            "template_version": assignment["template_version"],
            "template_digest": assignment["template_digest"],
            "status": "complete",
            "input_revision": assignment["input_revision"],
            "entities": {},
            "shared_entities": [],
            "event_bindings": [],
            "constraints": [],
            "unresolved": [],
            "source_ids": [],
        })
        with self.assertRaisesRegex(research_workspace.WorkspaceError, "输入文件已变化"):
            research_workspace.submit(Namespace(workspace=str(self.workspace), task_id="attractions", result_file=str(result_file), sources_file=None))

    def test_archive_document_inside_workspace(self) -> None:
        document = self.root / "official-notice.pdf"
        document.write_bytes(b"%PDF-1.4\narchive test\n")
        archived = research_workspace.archive(
            Namespace(
                workspace=str(self.workspace),
                record_id="west-lake-notice",
                task_id="main",
                kind="document",
                title="西湖官方公告",
                url="https://example.com/west-lake-notice",
                file=str(document),
                source_kind="official",
                summary="景区公告归档测试",
                query="杭州 西湖 官方公告",
                location="杭州西湖",
                topic="景区公告",
                tag=["hangzhou", "attraction"],
                checked_at="2026-09-20T10:00:00+08:00",
                valid_until=None,
                freshness="seasonal",
            )
        )
        stored = self.workspace / archived["record"]["stored_path"]
        self.assertTrue(stored.is_file())
        self.assertEqual(archived["record"]["sha256"], research_workspace.hashlib.sha256(document.read_bytes()).hexdigest())

    def test_source_ids_cannot_escape_archive_directory(self) -> None:
        with self.assertRaises(research_workspace.WorkspaceError):
            research_workspace.normalize_sources(
                [{"id": "../escape", "url": "https://example.com"}],
                "transport",
            )


if __name__ == "__main__":
    unittest.main()
