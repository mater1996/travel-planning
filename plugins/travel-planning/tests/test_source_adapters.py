from __future__ import annotations

import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "travel-planning" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import source_adapters


class SourceAdaptersTest(unittest.TestCase):
    def test_probe_mcp_stdio_initializes_and_lists_expected_tools(self) -> None:
        process = MagicMock()
        process.poll.return_value = 0
        initialized = {
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "test-mcp", "version": "1.0"},
            }
        }
        listed = {"result": {"tools": [{"name": "maps_weather"}]}}
        with patch.object(source_adapters.subprocess, "Popen", return_value=process):
            with patch.object(source_adapters, "_send_message") as send:
                with patch.object(
                    source_adapters,
                    "_read_response",
                    side_effect=[initialized, listed],
                ):
                    result = source_adapters.probe_mcp_stdio(
                        ["mcp"], {}, 5, {"maps_weather"}
                    )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["tools"], ["maps_weather"])
        self.assertEqual(send.call_args_list[2].args[1]["method"], "tools/list")

    def test_probe_mcp_stdio_rejects_missing_contract_tool(self) -> None:
        process = MagicMock()
        process.poll.return_value = 0
        with patch.object(source_adapters.subprocess, "Popen", return_value=process):
            with patch.object(source_adapters, "_send_message"):
                with patch.object(
                    source_adapters,
                    "_read_response",
                    side_effect=[{"result": {}}, {"result": {"tools": []}}],
                ):
                    with self.assertRaises(source_adapters.AdapterError) as raised:
                        source_adapters.probe_mcp_stdio(
                            ["mcp"], {}, 5, {"required_tool"}
                        )
        self.assertEqual(raised.exception.failure_kind, "contract_mismatch")

    def test_probe_mcp_http_initializes_and_lists_expected_tools(self) -> None:
        initialized = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2025-03-26",
                "serverInfo": {"name": "xiaohongshu-mcp", "version": "2.0.0"},
            },
        }
        listed = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"tools": [{"name": "check_login_status"}, {"name": "search_feeds"}]},
        }
        with patch.object(
            source_adapters,
            "_mcp_http_exchange",
            side_effect=[(initialized, None), (None, None), (listed, None)],
        ) as exchange:
            result = source_adapters.probe_mcp_http(
                "http://127.0.0.1:18060/mcp",
                5,
                {"check_login_status", "search_feeds"},
            )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["tools"], ["check_login_status", "search_feeds"])
        self.assertEqual(exchange.call_args_list[2].args[1]["method"], "tools/list")

    def test_parse_mcp_http_sse_response(self) -> None:
        payload = source_adapters._parse_mcp_http_body(
            'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        )
        self.assertEqual(payload["result"], {"ok": True})

    def test_provider_commands_are_version_pinned(self) -> None:
        with patch.object(source_adapters.shutil, "which", return_value="/usr/local/bin/npx"):
            for spec in source_adapters.PROVIDERS.values():
                command = source_adapters.provider_command(spec)
                self.assertIn(f"{spec.package}@{spec.version}", command)
                self.assertIn("--registry=https://registry.npmjs.org", command)

    def test_flyai_flight_is_normalized_to_snapshot(self) -> None:
        raw = {
            "data": {
                "itemList": [
                    {
                        "id": "offer-1",
                        "ticketPrice": "688.00",
                        "jumpUrl": "https://example.test/book/1",
                        "journeys": [
                            {
                                "segments": [
                                    {
                                        "transportType": "flight",
                                        "marketingTransportNo": "MU5101",
                                        "marketingTransportName": "东方航空",
                                        "depCityName": "上海",
                                        "depStationName": "虹桥机场",
                                        "depDateTime": "2026-10-03 08:00",
                                        "arrCityName": "北京",
                                        "arrStationName": "首都机场",
                                        "arrDateTime": "2026-10-03 10:10",
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        }
        adapter = source_adapters.FlyAiAdapter(source_adapters.PROVIDERS["fliggy_flyai"])
        with patch.object(source_adapters, "provider_command", return_value=["flyai"]):
            with patch.object(source_adapters, "run_json_cli", return_value=raw):
                result = adapter.query(
                    "flight",
                    "search-flight",
                    {"origin": "上海", "destination": "北京", "dep_date": "2026-10-03"},
                    {"origin": "上海", "destination": "北京", "date": "2026-10-03"},
                    30,
                    5,
                )
        self.assertEqual(result["schema_version"], "travel-source-snapshot/v1")
        self.assertEqual(result["snapshot_kind"], "quote")
        self.assertEqual(result["status"], "platform_reported")
        self.assertEqual(result["provider"]["id"], "fliggy_flyai")
        self.assertEqual(result["items"][0]["name"], "MU5101")
        self.assertEqual(result["items"][0]["price"]["amount"], 688.0)
        self.assertEqual(result["items"][0]["price"]["currency"], "CNY")
        self.assertEqual(result["items"][0]["action_link"], "https://example.test/book/1")
        self.assertTrue(result["raw_response_hash"].startswith("sha256:"))
        self.assertNotIn("itemList", result)

    def test_flyai_hotel_rejects_non_https_action_link(self) -> None:
        item = {
            "shId": "hotel-1",
            "name": "示例酒店",
            "price": "¥599",
            "detailUrl": "http://unsafe.example.test/hotel/1",
            "address": "西湖区",
            "score": "4.8",
        }
        normalized = source_adapters.normalize_flyai_item("hotel", item)
        self.assertEqual(normalized["price"]["currency"], "CNY")
        self.assertIsNone(normalized["action_link"])

    def test_obfuscated_trial_price_is_not_parsed_as_exact_amount(self) -> None:
        normalized = source_adapters.normalize_flyai_item(
            "hotel", {"name": "示例酒店", "price": "¥3xx"}
        )
        self.assertIsNone(normalized["price"]["amount"])
        self.assertEqual(normalized["price"]["currency"], "CNY")
        self.assertEqual(normalized["price"]["display"], "¥3xx")

    def test_variflight_requires_credential_before_starting_mcp(self) -> None:
        adapter = source_adapters.McpStdioAdapter(
            source_adapters.PROVIDERS["variflight_aviation"]
        )
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.env"
            with patch.dict(
                os.environ,
                {"TRAVEL_SOURCES_CONFIG": str(missing)},
                clear=True,
            ):
                with self.assertRaises(source_adapters.AdapterError) as raised:
                    adapter.query(
                        "flight",
                        "searchFlightsByNumber",
                        {"fnum": "MU2157", "date": "2026-10-03"},
                        {"fnum": "MU2157", "date": "2026-10-03"},
                        30,
                        5,
                    )
        self.assertEqual(raised.exception.failure_kind, "credential_missing")

    def test_variflight_snapshot_sanitizes_secret_fields(self) -> None:
        raw = {
            "flights": [
                {
                    "fnum": "MU2157",
                    "price": "CNY 720",
                    "apiKey": "must-not-leak",
                    "bookingUrl": "https://example.test/flight/MU2157",
                }
            ]
        }
        adapter = source_adapters.McpStdioAdapter(
            source_adapters.PROVIDERS["variflight_aviation"]
        )
        with patch.dict(os.environ, {"VARIFLIGHT_API_KEY": "secret-value"}, clear=True):
            with patch.object(source_adapters, "provider_command", return_value=["mcp"]):
                with patch.object(source_adapters, "call_mcp_stdio", return_value=raw):
                    result = adapter.query(
                        "flight",
                        "getFlightPriceByCities",
                        {"dep_city": "BJS", "arr_city": "SHA", "dep_date": "2026-10-03"},
                        {"origin": "BJS", "destination": "SHA", "date": "2026-10-03"},
                        30,
                        5,
                    )
        self.assertEqual(result["items"][0]["name"], "MU2157")
        self.assertNotIn("must-not-leak", str(result))
        self.assertNotIn("secret-value", str(result))
        self.assertNotIn("provider_fields", result["items"][0])

    def test_variflight_live_flight_shape_is_normalized(self) -> None:
        normalized = source_adapters.normalize_variflight_item(
            "flight",
            {
                "FlightNo": "MU5138",
                "FlightCompany": "中国东方航空股份有限公司",
                "FlightDep": "北京",
                "FlightDepAirport": "北京大兴",
                "FlightDepcode": "PKX",
                "FlightHTerminal": "",
                "FlightDeptimePlanDate": "2026-10-01 07:00:00",
                "FlightArr": "上海",
                "FlightArrAirport": "上海虹桥",
                "FlightArrcode": "SHA",
                "FlightTerminal": "T2",
                "FlightArrtimePlanDate": "2026-10-01 09:10:00",
                "FlightState": "计划",
                "OntimeRate": "100.00%",
                "ftype": "325",
                "FlightDuration": "130",
            },
        )
        self.assertEqual(normalized["name"], "MU5138")
        self.assertEqual(normalized["departure"]["station_code"], "PKX")
        self.assertEqual(normalized["arrival"]["station_code"], "SHA")
        self.assertEqual(normalized["operational"]["status"], "计划")
        self.assertEqual(normalized["total_duration"], "130")

    def test_variflight_live_train_shape_is_normalized(self) -> None:
        normalized = source_adapters.normalize_variflight_item(
            "train",
            {
                "trainNumber": "G565",
                "fromStation": "北京南",
                "fromTccode": "VNP",
                "fromTime": "07:07",
                "toStation": "上海虹桥",
                "toTccode": "AOH",
                "toTime": "13:12",
                "useTime": 365,
                "seatLists": [
                    {"seatName": "二等座", "seatPrice": 662, "ticketLeft": 10},
                    {"seatName": "一等座", "seatPrice": 1058, "ticketLeft": 3},
                ],
            },
        )
        self.assertEqual(normalized["name"], "G565")
        self.assertEqual(normalized["price"]["amount"], 662.0)
        self.assertEqual(normalized["availability"]["remaining"], 13)
        self.assertEqual(normalized["operational"]["seat_class"], "二等座")
        self.assertEqual(len(normalized["seat_options"]), 2)

    def test_variflight_station_lookup_shape_is_normalized(self) -> None:
        normalized = source_adapters.normalize_variflight_item(
            "train_station",
            {"station_name": "北京南", "station_code": "VNP", "city_name": "北京"},
        )
        self.assertEqual(normalized["offer_id"], "VNP")
        self.assertEqual(normalized["name"], "北京南")
        self.assertEqual(normalized["location"]["city"], "北京")

    def test_snapshot_has_nonempty_offer_id_and_expiry(self) -> None:
        normalized = source_adapters.normalize_flyai_item("hotel", {"price": "¥599"})
        self.assertTrue(normalized["offer_id"].startswith("provider-"))
        result = source_adapters.make_snapshot(
            source_adapters.PROVIDERS["fliggy_flyai"],
            "hotel",
            {"destination": "杭州"},
            {"data": {"itemList": []}},
            [],
            "search-hotel",
        )
        self.assertIsNotNone(result["freshness"]["expires_at"])
        self.assertGreater(
            source_adapters.datetime.fromisoformat(result["freshness"]["expires_at"]),
            source_adapters.datetime.fromisoformat(result["freshness"]["checked_at"]),
        )
        self.assertEqual(result["freshness"]["planning_validity"], "historical_snapshot")
        self.assertEqual(result["freshness"]["refresh_before"], "purchase")

    def test_non_quote_snapshot_uses_its_actual_refresh_boundary(self) -> None:
        result = source_adapters.make_snapshot(
            source_adapters.PROVIDERS["variflight_aviation"],
            "flight",
            {"flight_number": "CA123"},
            {},
            [],
            "flight_status",
        )
        self.assertEqual(result["snapshot_kind"], "operational")
        self.assertEqual(result["freshness"]["planning_validity"], "historical_snapshot")
        self.assertEqual(result["freshness"]["refresh_before"], "departure")

    def test_unauthorized_is_distinct_from_missing_credential(self) -> None:
        self.assertEqual(
            source_adapters._classify_failure("HTTP 403 unauthorized"),
            "authorization_failed",
        )

    def test_mcp_metadata_only_response_is_no_results(self) -> None:
        adapter = source_adapters.McpStdioAdapter(
            source_adapters.PROVIDERS["variflight_tripmatch"]
        )
        with patch.dict(os.environ, {"VARIFLIGHT_API_KEY": "secret"}, clear=True):
            with patch.object(source_adapters, "provider_command", return_value=["mcp"]):
                with patch.object(source_adapters, "call_mcp_stdio", return_value={"code": 0, "message": "ok"}):
                    result = adapter.query(
                        "train", "searchTrainTickets", {"from": "北京", "to": "上海", "date": "2026-10-03"},
                        {"origin": "北京", "destination": "上海", "date": "2026-10-03"}, 30, 5,
                    )
        self.assertEqual(result["status"], "no_results")
        self.assertEqual(result["items"], [])

    def test_generated_snapshot_covers_machine_schema_required_fields(self) -> None:
        schema_path = SCRIPTS_DIR.parent / "schemas" / "travel-source-snapshot.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        result = source_adapters.make_snapshot(
            source_adapters.PROVIDERS["fliggy_flyai"],
            "hotel",
            {"destination": "杭州"},
            {"data": {"itemList": []}},
            [],
            "search-hotel",
        )
        self.assertTrue(set(schema["required"]).issubset(result))
        self.assertEqual(result["snapshot_kind"], "quote")
        self.assertEqual(result["status"], "no_results")


if __name__ == "__main__":
    unittest.main()
