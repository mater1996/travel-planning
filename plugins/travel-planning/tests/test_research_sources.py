from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "skills" / "travel-planning" / "scripts" / "research_sources.py"
SPEC = importlib.util.spec_from_file_location("research_sources", MODULE_PATH)
assert SPEC and SPEC.loader
research_sources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_sources)


class ResearchSourcesTest(unittest.TestCase):
    def test_mcp_preflight_runs_handshake_and_read_only_smoke_query(self) -> None:
        with patch.object(
            research_sources,
            "probe_mcp_stdio",
            return_value={"status": "ready", "tools": ["maps_weather"]},
        ) as probe:
            with patch.object(research_sources, "call_mcp_stdio", return_value={}) as call:
                result = research_sources._mcp_preflight(
                    source_id="amap-maps",
                    command=["mcp"],
                    environment={},
                    expected_tools={"maps_weather"},
                    smoke_tool="maps_weather",
                    smoke_arguments={"city": "杭州"},
                    required=True,
                    timeout=5,
                    skip_upstream=False,
                )
        self.assertEqual(result["status"], "ready")
        probe.assert_called_once_with(["mcp"], {}, 5, {"maps_weather"})
        call.assert_called_once_with(["mcp"], "maps_weather", {"city": "杭州"}, {}, 5)

    def test_preflight_returns_unavailable_for_failed_required_source(self) -> None:
        args = Namespace(
            require=["amap-maps"],
            city="杭州",
            airport="HGH",
            timeout=5,
            skip_upstream=False,
        )
        failed = {
            "source_id": "amap-maps",
            "required": True,
            "status": "unavailable",
        }

        def ready(source_id: str) -> dict[str, object]:
            return {"source_id": source_id, "required": False, "status": "ready"}

        with patch.object(research_sources, "_amap_preflight", return_value=failed):
            with patch.object(
                research_sources,
                "_variflight_preflight",
                side_effect=[
                    ready("variflight-aviation"),
                    ready("variflight-tripmatch"),
                ],
            ):
                with patch.object(
                    research_sources, "_flyai_preflight", return_value=ready("flyai")
                ):
                    with patch.object(
                        research_sources,
                        "_weather_preflight",
                        return_value=ready("open-meteo"),
                    ):
                        with patch.object(
                            research_sources,
                            "_xiaohongshu_preflight",
                            return_value=ready("xiaohongshu"),
                        ):
                            result = research_sources.preflight(args)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["required_failures"], ["amap-maps"])

    def test_capabilities_do_not_expose_key(self) -> None:
        with patch.dict(os.environ, {"AMAP_API_KEY": "secret-value"}, clear=True):
            result = research_sources.capabilities(Namespace())
        self.assertTrue(result["map"]["available"])
        self.assertEqual(result["map"]["providers"][0]["skill"], "$amap-maps")
        self.assertEqual(
            result["travel_inventory"]["providers"]["variflight_aviation"]["skill"],
            "$variflight",
        )
        self.assertFalse(result["travel_inventory"]["consent_required_per_query"])
        self.assertNotIn("secret-value", str(result))

    def test_weather_normalizes_daily_forecast(self) -> None:
        responses = [
            {
                "results": [
                    {
                        "name": "杭州",
                        "admin1": "浙江",
                        "country": "中国",
                        "latitude": 30.29,
                        "longitude": 120.16,
                        "timezone": "Asia/Shanghai",
                    }
                ]
            },
            {
                "timezone": "Asia/Shanghai",
                "daily_units": {"temperature_2m_max": "°C"},
                "daily": {
                    "time": ["2026-10-03"],
                    "weather_code": [61],
                    "temperature_2m_max": [23.0],
                    "temperature_2m_min": [17.0],
                    "precipitation_sum": [4.2],
                    "precipitation_probability_max": [80],
                    "uv_index_max": [3.1],
                    "sunrise": ["2026-10-03T05:54"],
                    "sunset": ["2026-10-03T17:45"],
                },
            },
        ]
        args = Namespace(location="杭州", latitude=None, longitude=None, name=None, days=1)
        with patch.object(research_sources, "request_json", side_effect=responses):
            result = research_sources.weather(args)
        self.assertEqual(result["status"], "platform_reported")
        self.assertEqual(result["forecasts"][0]["summary"], "小雨")
        self.assertEqual(result["forecasts"][0]["icon_code"], "rain")
        self.assertEqual(result["forecasts"][0]["precipitation_probability_max"], 80)
        self.assertEqual(result["action_links"][0]["type"], "weather")
        self.assertEqual(result["action_links"][1]["type"], "weather_warning")

    def test_train_fallback_keeps_query_conditions(self) -> None:
        args = Namespace(
            kind="train",
            date="2026-10-03",
            origin="北京南",
            destination="上海虹桥",
            city=None,
            keywords=None,
            travelers="2 位成人",
            fields="余票",
            product=None,
            url=None,
            recheck="出发前复核",
        )
        result = research_sources.fallback(args)
        link = result["action_links"][0]
        self.assertEqual(result["status"], "to_recheck")
        self.assertIn("北京南 → 上海虹桥", link["label"])
        self.assertEqual(link["url"], "https://www.12306.cn/index/")
        self.assertTrue(link["manual_required"])

    def test_attraction_fallback_requires_verified_official_url(self) -> None:
        args = Namespace(
            kind="attraction",
            date=None,
            origin=None,
            destination=None,
            city=None,
            keywords="开放时间",
            travelers=None,
            fields=None,
            product=None,
            url=None,
            recheck="出发前复核",
        )
        with self.assertRaises(research_sources.SourceError):
            research_sources.fallback(args)

    def test_amap_requires_user_key(self) -> None:
        args = Namespace(keywords="西湖入口", city="杭州", limit=3)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(research_sources.SourceError):
                research_sources.amap_place(args)

    def test_local_config_loads_allowlisted_provider_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sources.local.env"
            config.write_text(
                "# local\nAMAP_API_KEY=test-key\nVARIFLIGHT_API_KEY=flight-key\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                research_sources.load_local_config(config)
                self.assertEqual(research_sources.get_amap_key(), "test-key")
                self.assertEqual(os.environ["VARIFLIGHT_API_KEY"], "flight-key")

    def test_local_config_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sources.local.env"
            config.write_text("UNKNOWN_SECRET=value\n", encoding="utf-8")
            with self.assertRaises(research_sources.SourceError):
                research_sources.load_local_config(config)

    def test_osm_place_normalizes_candidate(self) -> None:
        args = Namespace(
            query="Kiyomizu-dera Niomon, Kyoto, Japan",
            countrycodes="jp",
            language="zh-CN,en",
            limit=1,
        )
        response = [
            {
                "osm_type": "node",
                "osm_id": 123,
                "name": "仁王門",
                "display_name": "仁王門, 京都市, 日本",
                "lat": "34.9941",
                "lon": "135.7850",
                "category": "historic",
                "type": "city_gate",
                "address": {"city": "京都市"},
            }
        ]
        with patch.object(research_sources, "request_json", return_value=response):
            result = research_sources.osm_place(args)
        self.assertEqual(result["status"], "platform_reported")
        self.assertEqual(result["places"][0]["name"], "仁王門")
        self.assertIn("openstreetmap.org", result["places"][0]["map_url"])

    def test_google_map_fallback_preserves_query(self) -> None:
        args = Namespace(
            kind="map",
            date=None,
            origin=None,
            destination=None,
            city="Kyoto",
            keywords="Kiyomizu-dera Niomon entrance",
            travelers=None,
            fields="入口与步行路线",
            product=None,
            url=None,
            recheck="出发前复核",
            map_provider="google",
        )
        result = research_sources.fallback(args)
        link = result["action_links"][0]
        self.assertEqual(link["provider"], "Google Maps")
        self.assertIn("Kiyomizu-dera+Niomon+entrance", link["url"])

    def test_xhs_health_probes_streamable_http_mcp(self) -> None:
        transport = {"status": "ready", "tools": ["check_login_status", "search_feeds", "get_feed_detail"]}
        with patch.object(research_sources, "probe_mcp_http", return_value=transport) as probe:
            result = research_sources.xhs_health(Namespace())
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["provider"], "xpzouying/xiaohongshu-mcp")
        probe.assert_called_once_with(
            "http://127.0.0.1:18060/mcp",
            15,
            {"check_login_status", "search_feeds", "get_feed_detail"},
            None,
        )

    def test_xhs_login_status_uses_read_only_mcp_tool(self) -> None:
        with patch.object(research_sources, "xhs_mcp_call", return_value={"text": "✅ 已登录\n用户名: test"}) as call:
            result = research_sources.xhs_login_status(Namespace(timeout=9))
        self.assertEqual(result["status"], "authenticated")
        call.assert_called_once_with("check_login_status", {}, timeout=9)

    def test_xhs_preflight_requires_protocol_tools_and_login(self) -> None:
        args = Namespace(timeout=7, skip_upstream=False)
        transport = {"status": "ready", "tools": ["check_login_status", "search_feeds", "get_feed_detail"]}
        with (
            patch.object(research_sources, "probe_mcp_http", return_value=transport) as probe,
            patch.object(
                research_sources,
                "xhs_login_status",
                return_value={"status": "authenticated", "session": {"logged_in": True}},
            ),
        ):
            result = research_sources._xiaohongshu_preflight(args, True)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["kind"], "mcp_streamable_http")
        probe.assert_called_once_with(
            "http://127.0.0.1:18060/mcp",
            7,
            {"check_login_status", "search_feeds", "get_feed_detail"},
            None,
        )

    def test_xhs_search_caches_token_but_never_outputs_it(self) -> None:
        response = {
            "feeds": [
                {
                    "id": "note-1",
                    "xsecToken": "secret-token",
                    "modelType": "note",
                    "noteCard": {
                        "type": "normal",
                        "displayTitle": "秋天入口实测",
                        "user": {"nickname": "旅行者"},
                        "interactInfo": {"likedCount": "12", "commentCount": "3"},
                    },
                }
            ],
            "count": 1,
        }
        args = Namespace(
            keyword="景点 10月 入口 避坑",
            sort_by="relevance",
            note_type="all",
            publish_time="half_year",
            search_scope="all",
            location="all",
            limit=10,
        )
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "tokens.json"
            with patch.dict(os.environ, {"XHS_TOKEN_CACHE": str(cache)}, clear=False):
                with patch.object(research_sources, "xhs_mcp_call", return_value=response):
                    result = research_sources.xhs_search(args)
                    call = research_sources.xhs_mcp_call.call_args
            self.assertNotIn("secret-token", json.dumps(result, ensure_ascii=False))
            self.assertEqual(result["results"][0]["note_id"], "note-1")
            self.assertEqual(
                call.args[1]["filters"],
                {"publish_time": "半年内"},
            )
            self.assertEqual(json.loads(cache.read_text(encoding="utf-8"))["notes"]["note-1"]["xsec_token"], "secret-token")
            self.assertEqual(cache.stat().st_mode & 0o777, 0o600)

    def test_xhs_search_cli_defaults_to_one_non_default_filter(self) -> None:
        args = research_sources.build_parser().parse_args([
            "xhs-search",
            "--keyword",
            "昆明 三日游",
        ])

        self.assertEqual(args.sort_by, "relevance")
        self.assertEqual(args.note_type, "all")
        self.assertEqual(args.publish_time, "half_year")
        self.assertEqual(args.search_scope, "all")
        self.assertEqual(args.location, "all")

    def test_xhs_detail_reads_token_from_private_cache(self) -> None:
        response = {
            "feed_id": "note-1",
            "data": {
                "note": {
                    "noteId": "note-1",
                    "title": "路线实测",
                    "desc": "从东门进入步行较少",
                    "time": 1789855200000,
                    "user": {"nickname": "旅行者"},
                    "interactInfo": {"likedCount": "10"},
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "tokens.json"
            cache.write_text(
                json.dumps({"version": 1, "notes": {"note-1": {"xsec_token": "cached-token"}}}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"XHS_TOKEN_CACHE": str(cache)}, clear=False):
                with patch.object(research_sources, "xhs_mcp_call", return_value=response) as call:
                    result = research_sources.xhs_detail(Namespace(note_id="note-1"))
            self.assertEqual(call.call_args.args[0], "get_feed_detail")
            self.assertEqual(call.call_args.args[1]["xsec_token"], "cached-token")
            self.assertNotIn("token", json.dumps(result, ensure_ascii=False).lower())
            self.assertEqual(result["note"]["title"], "路线实测")
            self.assertEqual(result["note"]["description_excerpt"], "从东门进入步行较少")

    def test_xhs_excerpt_is_bounded(self) -> None:
        excerpt = research_sources.xhs_excerpt("  " + "体验很好 " * 100, limit=32)
        self.assertLessEqual(len(excerpt), 33)
        self.assertTrue(excerpt.endswith("…"))

    def test_xhs_fallback_preserves_search_phrase(self) -> None:
        args = Namespace(
            kind="xiaohongshu",
            date=None,
            origin=None,
            destination=None,
            city="杭州",
            keywords="西湖 10月 日落 入口 避坑",
            travelers=None,
            fields=None,
            product=None,
            url=None,
            recheck="规划时复核",
            map_provider="amap",
        )
        result = research_sources.fallback(args)
        self.assertIn("西湖 10月 日落 入口 避坑", result["action_links"][0]["label"])
        self.assertEqual(result["action_links"][0]["url"], "https://www.xiaohongshu.com/explore")

    def test_provider_query_runs_without_external_data_consent_prompt(self) -> None:
        args = Namespace(
            origin="北京",
            destination="上海",
            date="2026-10-03",
            return_date=None,
            journey_type=1,
            seat_class=None,
            max_price=None,
            sort_type=2,
            timeout=30,
            limit=10,
            consent_external_data=False,
        )
        provider = MagicMock()
        provider.query.return_value = {"schema_version": "travel-source-snapshot/v1"}
        with patch.object(research_sources, "adapter", return_value=provider):
            result = research_sources.flyai_flight(args)
        self.assertEqual(result["schema_version"], "travel-source-snapshot/v1")
        provider.query.assert_called_once()

    def test_flyai_flight_coverage_queries_feasibility_sorts(self) -> None:
        args = Namespace(
            origin="北京", destination="重庆", date="2026-10-01",
            return_date=None, journey_type=1, seat_class=None, max_price=None,
            sort_type=2, timeout=30, limit=10, workspace=None, task_id=None,
        )
        provider = MagicMock()
        provider.query.side_effect = [
            {"schema_version": "travel-source-snapshot/v1", "snapshot_id": str(index).zfill(24)}
            for index in range(5)
        ]
        with patch.object(research_sources, "adapter", return_value=provider):
            result = research_sources.flyai_flight_coverage(args)
        self.assertEqual(result["schema_version"], "travel-source-snapshot-batch/v1")
        self.assertEqual(
            [call.kwargs["arguments"]["sort_type"] for call in provider.query.call_args_list],
            [6, 7, 4, 3, 2],
        )
        self.assertEqual(len(result["snapshot_ids"]), 5)

    def test_variflight_flight_maps_city_and_airport_arguments(self) -> None:
        args = Namespace(
            origin="BJS",
            origin_kind="city",
            destination="PVG",
            destination_kind="airport",
            date="2026-10-03",
            timeout=30,
            limit=10,
            consent_external_data=True,
        )
        provider = MagicMock()
        provider.query.return_value = {"schema_version": "travel-source-snapshot/v1"}
        with patch.object(research_sources, "adapter", return_value=provider):
            result = research_sources.variflight_flight_search(args)
        self.assertEqual(result["schema_version"], "travel-source-snapshot/v1")
        self.assertEqual(
            provider.query.call_args.kwargs["arguments"],
            {"depcity": "BJS", "arr": "PVG", "date": "2026-10-03"},
        )

    def test_flyai_hotel_maps_official_cli_parameter_names(self) -> None:
        args = Namespace(
            destination="杭州",
            check_in="2026-10-03",
            check_out="2026-10-05",
            keywords=None,
            poi="西湖",
            hotel_type="酒店",
            sort="rate_desc",
            stars="4,5",
            bed_type="双床房",
            adults=4,
            rooms=2,
            max_price=800,
            timeout=30,
            limit=10,
            consent_external_data=True,
        )
        provider = MagicMock()
        provider.query.return_value = {"schema_version": "travel-source-snapshot/v1"}
        with patch.object(research_sources, "adapter", return_value=provider):
            research_sources.flyai_hotel(args)
        self.assertEqual(
            provider.query.call_args.kwargs["arguments"]["check_in_date"], "2026-10-03"
        )
        self.assertEqual(provider.query.call_args.kwargs["arguments"]["hotel_stars"], "4,5")
        self.assertNotIn("requested_occupancy", provider.query.call_args.kwargs["arguments"])
        self.assertEqual(
            provider.query.call_args.kwargs["query"]["requested_occupancy"],
            {"adults": 4, "rooms": 2},
        )
        self.assertFalse(provider.query.call_args.kwargs["query"]["supplier_capacity_filter_supported"])

    def test_provider_query_stores_snapshot_when_workspace_target_is_given(self) -> None:
        args = Namespace(
            timeout=30, limit=10, consent_external_data=True,
            workspace="/tmp/travel-workspace", task_id="route-data",
        )
        snapshot = {"schema_version": "travel-source-snapshot/v1", "snapshot_id": "0" * 24}
        provider = MagicMock()
        provider.query.return_value = snapshot
        with patch.object(research_sources, "adapter", return_value=provider):
            with patch.object(research_sources, "store_source_snapshot") as store:
                result = research_sources.provider_query(
                    args, "fliggy_flyai", "train", "search-train",
                    {"origin": "北京", "destination": "上海"},
                    {"origin": "北京", "destination": "上海"},
                )
        self.assertIs(result, snapshot)
        store.assert_called_once_with(
            research_sources.Path("/tmp/travel-workspace"), "route-data", snapshot
        )


if __name__ == "__main__":
    unittest.main()
