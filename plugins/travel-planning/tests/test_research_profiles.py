from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "skills" / "travel-planning" / "scripts" / "research_profiles.py"
SPEC = importlib.util.spec_from_file_location("research_profiles", MODULE_PATH)
assert SPEC and SPEC.loader
research_profiles = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_profiles)


class ResearchProfilesTest(unittest.TestCase):
    def test_registry_dependencies_and_paths_are_valid(self) -> None:
        modules = research_profiles.load_registry()
        self.assertIn("transport.self_drive", modules)
        self.assertEqual(modules["transport.car_rental"]["depends_on"], ["transport.self_drive"])
        self.assertEqual(
            research_profiles.guides_for_stage("restaurant_discovery"),
            ["references/dining/discovery.md", "references/dining/operations.md"],
        )

    def test_rental_self_drive_and_mountain_profiles_compose(self) -> None:
        profile = research_profiles.resolve_profile({
            "id": "route-road-trip",
            "research_features": {
                "transport_modes": ["rail", "self_drive"],
                "attraction_types": ["mountain_outdoor"],
                "scenarios": ["car_rental"],
            },
        }, generated_at="2026-09-22T12:00:00+08:00")
        self.assertEqual(profile["compatibility_mode"], "structured")
        self.assertIn("transport.rail", profile["modules"])
        self.assertIn("transport.self_drive", profile["modules"])
        self.assertIn("transport.car_rental", profile["modules"])
        self.assertIn("attractions.mountain_outdoor", profile["modules"])
        self.assertIn("dining.driving_parking", profile["modules"])

    def test_unstructured_legacy_route_activates_only_domain_cores(self) -> None:
        profile = research_profiles.resolve_profile({"id": "route-legacy", "cities": ["杭州"]})
        self.assertEqual(profile["compatibility_mode"], "legacy_core_only")
        self.assertEqual(profile["modules"], list(research_profiles.CORE_MODULES))

    def test_assignment_filters_modules_by_domain(self) -> None:
        profile = research_profiles.resolve_profile({
            "id": "route-rental", "research_features": {"scenarios": ["car_rental"]},
        })
        road_trip = research_profiles.modules_for_assignment(profile, "road-trip")
        self.assertEqual(
            road_trip["required_modules"],
            ["transport.core", "transport.self_drive", "transport.car_rental"],
        )
        lodging = research_profiles.modules_for_assignment(profile, "lodging")
        self.assertEqual(lodging["required_modules"], ["lodging.core"])

    def test_lodging_inventory_and_constrained_dining_profiles_are_routed(self) -> None:
        profile = research_profiles.resolve_profile({
            "id": "route-scenarios",
            "research_features": {"scenarios": ["multi_room", "constrained_venue"]},
        })
        self.assertIn("lodging.inventory_occupancy", profile["modules"])
        self.assertIn("dining.constrained_venue", profile["modules"])
        self.assertIn(
            "references/lodging/inventory-and-occupancy.md",
            research_profiles.modules_for_assignment(profile, "lodging")["required_guides"],
        )

    def test_urban_walk_alias_routes_the_specific_guide(self) -> None:
        profile = research_profiles.resolve_profile({
            "id": "route-citywalk",
            "research_features": {"attraction_types": ["老街"]},
        })
        self.assertIn("attractions.urban_walk", profile["modules"])
        assignment = research_profiles.modules_for_assignment(profile, "attractions")
        self.assertIn("references/attractions/urban-walk.md", assignment["required_guides"])
        self.assertIn("checkpoint_content", assignment["completion_checks"])

    def test_assignment_rejects_unknown_or_dependency_incomplete_profile(self) -> None:
        with self.assertRaisesRegex(research_profiles.ProfileError, "未知模块"):
            research_profiles.modules_for_assignment(
                {"modules": ["transport.unknown"]}, "road-trip"
            )
        with self.assertRaisesRegex(research_profiles.ProfileError, "缺少.*依赖"):
            research_profiles.modules_for_assignment(
                {"modules": ["transport.car_rental"]}, "road-trip"
            )


if __name__ == "__main__":
    unittest.main()
