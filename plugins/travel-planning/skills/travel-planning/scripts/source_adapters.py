#!/usr/bin/env python3
"""Read-only provider adapters and normalized travel source snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.providers.flyai_cli import (  # noqa: E402
    command as flyai_command,
    load_config as load_flyai_environment,
)
from scripts.providers.variflight_mcp import (  # noqa: E402
    command as variflight_command,
    load_config as load_variflight_environment,
)


SNAPSHOT_SCHEMA_VERSION = "travel-source-snapshot/v1"
QUOTE_TOOLS = {
    "search-flight",
    "search-train",
    "search-hotel",
    "searchFlightsByDepArr",
    "getFlightPriceByCities",
    "searchTrainTickets",
    "searchTrainTicketsByCity",
    "searchTrainTicketsByStation",
    "getFlightAndTrainTransferInfo",
}
LOOKUP_TOOLS = {"searchTrainStations"}


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    name: str
    authority: str
    transport: str
    package: str
    version: str
    executable: str
    credential_env: str | None
    source_url: str
    products: tuple[str, ...]


PROVIDERS = {
    "fliggy_flyai": ProviderSpec(
        provider_id="fliggy_flyai",
        name="飞猪 FlyAI",
        authority="official_platform",
        transport="cli_to_vendor_mcp_api",
        package="@fly-ai/flyai-cli",
        version="1.0.16",
        executable="flyai",
        credential_env="FLYAI_API_KEY",
        source_url="https://github.com/alibaba-flyai/flyai-skill",
        products=("flight", "train", "hotel"),
    ),
    "variflight_aviation": ProviderSpec(
        provider_id="variflight_aviation",
        name="飞常准 Aviation MCP",
        authority="official_provider",
        transport="mcp_stdio",
        package="@variflight-ai/variflight-mcp",
        version="1.0.3",
        executable="variflight-mcp",
        credential_env="VARIFLIGHT_API_KEY",
        source_url="https://github.com/variflight/variflight-mcp",
        products=("flight",),
    ),
    "variflight_tripmatch": ProviderSpec(
        provider_id="variflight_tripmatch",
        name="飞常准 Tripmatch MCP",
        authority="official_provider",
        transport="mcp_stdio",
        package="@variflight-ai/tripmatch-mcp",
        version="0.0.5",
        executable="variflight-mcp",
        credential_env="VARIFLIGHT_API_KEY",
        source_url="https://github.com/variflight/tripmatch-mcp",
        products=("flight", "train", "air_rail_transfer"),
    ),
}


class AdapterError(RuntimeError):
    """A provider failed with a stable, machine-readable failure kind."""

    def __init__(self, failure_kind: str, message: str):
        super().__init__(message)
        self.failure_kind = failure_kind


def checked_at() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def provider_command(spec: ProviderSpec) -> list[str]:
    """Return the plugin-level, version-pinned provider command."""
    try:
        if spec.provider_id == "fliggy_flyai":
            return flyai_command([])
        if spec.provider_id == "variflight_aviation":
            return variflight_command("aviation")
        if spec.provider_id == "variflight_tripmatch":
            return variflight_command("tripmatch")
    except RuntimeError as error:
        raise AdapterError("runtime_unavailable", str(error)) from error
    raise AdapterError("unsupported_provider", f"不支持的数据源：{spec.provider_id}")


def provider_capabilities() -> dict[str, dict[str, Any]]:
    runtime_available = shutil.which("npx") is not None
    result: dict[str, dict[str, Any]] = {}
    for provider_id, spec in PROVIDERS.items():
        credential_configured = bool(spec.credential_env and os.environ.get(spec.credential_env))
        credential_required = provider_id.startswith("variflight_")
        result[provider_id] = {
            "name": spec.name,
            "authority": spec.authority,
            "transport": spec.transport,
            "adapter_available": runtime_available,
            "live_query_available": runtime_available and (credential_configured or not credential_required),
            "credential_required": credential_required,
            "credential_configured": credential_configured,
            "package": spec.package,
            "pinned_version": spec.version,
            "products": list(spec.products),
            "source_url": spec.source_url,
            "skill": "$flyai" if provider_id == "fliggy_flyai" else "$variflight",
        }
    return result


def _redact(text: str, env: dict[str, str]) -> str:
    redacted = text
    for key in (
        "FLYAI_API_KEY",
        "FLYAI_SIGN_SECRET",
        "VARIFLIGHT_API_KEY",
        "X_VARIFLIGHT_KEY",
    ):
        value = env.get(key)
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def _classify_failure(message: str) -> str:
    lower = message.lower()
    if any(token in lower for token in ("401", "403", "api key", "apikey", "unauthorized")):
        return "authorization_failed"
    if any(token in lower for token in ("429", "quota", "rate limit", "too many requests")):
        return "quota_exceeded"
    if any(token in lower for token in ("not found", "enoent", "command not found")):
        return "runtime_unavailable"
    return "provider_error"


def _parse_json_output(stdout: str) -> Any:
    clean = stdout.strip()
    if not clean:
        raise AdapterError("invalid_response", "供应商命令未返回 JSON")
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        for line in reversed(clean.splitlines()):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise AdapterError("invalid_response", "供应商命令输出无法解析为 JSON")


def run_json_cli(command: list[str], env: dict[str, str], timeout: int) -> Any:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            env=env,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise AdapterError("timeout", f"供应商查询超过 {timeout} 秒") from error
    except OSError as error:
        raise AdapterError("runtime_unavailable", f"无法启动供应商命令：{error}") from error
    if completed.returncode != 0:
        message = _redact((completed.stderr or completed.stdout).strip(), env)
        raise AdapterError(_classify_failure(message), message or "供应商命令执行失败")
    return _parse_json_output(completed.stdout)


def _send_message(process: subprocess.Popen[str], message: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    process.stdin.flush()


def _read_response(
    process: subprocess.Popen[str], request_id: int, timeout: int
) -> dict[str, Any]:
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            if not selector.select(remaining):
                break
            line = process.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == request_id:
                return message
    finally:
        selector.close()
    raise AdapterError("timeout", f"MCP 请求 {request_id} 在 {timeout} 秒内未返回")


def _mcp_result_payload(result: dict[str, Any]) -> Any:
    if result.get("isError"):
        text = " ".join(
            str(block.get("text", ""))
            for block in result.get("content", [])
            if isinstance(block, dict)
        ).strip()
        raise AdapterError(_classify_failure(text), text or "MCP 工具返回错误")
    structured = result.get("structuredContent")
    if structured is not None:
        return structured
    texts = [
        block.get("text", "")
        for block in result.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    if not texts:
        return result
    joined = "\n".join(texts).strip()
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return {"text": joined}


def _stop_mcp_process(process: subprocess.Popen[str]) -> None:
    if process.stdin:
        process.stdin.close()
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def probe_mcp_stdio(
    command: list[str],
    env: dict[str, str],
    timeout: int,
    expected_tools: set[str] | None = None,
) -> dict[str, Any]:
    """Start an MCP server and verify initialize plus tools/list."""
    stderr_file = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
    started_at = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            env=env,
            text=True,
            bufsize=1,
        )
    except OSError as error:
        stderr_file.close()
        raise AdapterError("runtime_unavailable", f"无法启动 MCP：{error}") from error
    try:
        _send_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "travel-planning-preflight",
                        "version": "1.0",
                    },
                },
            },
        )
        initialized = _read_response(process, 1, timeout)
        if "error" in initialized:
            raise AdapterError("provider_error", str(initialized["error"]))
        _send_message(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send_message(
            process,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        listed = _read_response(process, 2, timeout)
        if "error" in listed:
            raise AdapterError("provider_error", str(listed["error"]))
        tools = listed.get("result", {}).get("tools", [])
        names = sorted(
            str(tool["name"])
            for tool in tools
            if isinstance(tool, dict) and tool.get("name")
        )
        missing = sorted((expected_tools or set()) - set(names))
        if missing:
            raise AdapterError(
                "contract_mismatch",
                f"MCP tools/list 缺少预期工具：{', '.join(missing)}",
            )
        initialized_result = initialized.get("result") or {}
        return {
            "status": "ready",
            "protocol_version": initialized_result.get("protocolVersion"),
            "server_info": initialized_result.get("serverInfo"),
            "tool_count": len(names),
            "tools": names,
            "latency_ms": round((time.monotonic() - started_at) * 1000),
        }
    except AdapterError as error:
        if error.failure_kind == "timeout":
            stderr_file.seek(0)
            diagnostic = _redact(stderr_file.read().strip(), env)
            if process.poll() is not None and diagnostic:
                raise AdapterError(_classify_failure(diagnostic), diagnostic) from error
        raise
    finally:
        _stop_mcp_process(process)
        stderr_file.close()


def call_mcp_stdio(
    command: list[str], tool: str, arguments: dict[str, Any], env: dict[str, str], timeout: int
) -> Any:
    stderr_file = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            env=env,
            text=True,
            bufsize=1,
        )
    except OSError as error:
        stderr_file.close()
        raise AdapterError("runtime_unavailable", f"无法启动 MCP：{error}") from error
    try:
        _send_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "travel-planning", "version": "1.0"},
                },
            },
        )
        initialized = _read_response(process, 1, timeout)
        if "error" in initialized:
            raise AdapterError("provider_error", str(initialized["error"]))
        _send_message(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            },
        )
        response = _read_response(process, 2, timeout)
        if "error" in response:
            message = _redact(json.dumps(response["error"], ensure_ascii=False), env)
            raise AdapterError(_classify_failure(message), message)
        return _mcp_result_payload(response.get("result") or {})
    except AdapterError as error:
        if error.failure_kind == "timeout":
            stderr_file.seek(0)
            diagnostic = _redact(stderr_file.read().strip(), env)
            if process.poll() is not None and diagnostic:
                raise AdapterError(_classify_failure(diagnostic), diagnostic) from error
        raise
    finally:
        _stop_mcp_process(process)
        stderr_file.close()


def _parse_mcp_http_body(body: str) -> dict[str, Any] | None:
    clean = body.strip()
    if not clean:
        return None
    candidates = [
        line.removeprefix("data:").strip()
        for line in clean.splitlines()
        if line.startswith("data:")
    ]
    for candidate in reversed(candidates or [clean]):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise AdapterError("invalid_response", "HTTP MCP 未返回有效 JSON-RPC")


def _mcp_http_exchange(
    endpoint: str,
    payload: dict[str, Any],
    timeout: int,
    *,
    session_id: str | None = None,
    auth_token: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AdapterError("invalid_configuration", f"无效的 HTTP MCP 地址：{endpoint}")
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": "travel-planning-mcp-preflight/1.0",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            returned_session = response.headers.get("Mcp-Session-Id") or session_id
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        message = body.strip() or f"HTTP {error.code}"
        raise AdapterError(_classify_failure(f"HTTP {error.code}: {message}"), message) from error
    except (URLError, OSError) as error:
        raise AdapterError("runtime_unavailable", f"无法连接 HTTP MCP {endpoint}：{error}") from error
    return _parse_mcp_http_body(body), returned_session


def _initialize_mcp_http(
    endpoint: str, timeout: int, auth_token: str | None = None
) -> tuple[dict[str, Any], str | None]:
    initialized, session_id = _mcp_http_exchange(
        endpoint,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "travel-planning-preflight", "version": "1.0"},
            },
        },
        timeout,
        auth_token=auth_token,
    )
    if not initialized:
        raise AdapterError("invalid_response", "HTTP MCP initialize 未返回结果")
    if "error" in initialized:
        raise AdapterError("provider_error", str(initialized["error"]))
    _mcp_http_exchange(
        endpoint,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        timeout,
        session_id=session_id,
        auth_token=auth_token,
    )
    return initialized, session_id


def probe_mcp_http(
    endpoint: str,
    timeout: int,
    expected_tools: set[str] | None = None,
    auth_token: str | None = None,
) -> dict[str, Any]:
    """Verify HTTP MCP initialize and tools/list without mutating upstream state."""
    started_at = time.monotonic()
    initialized, session_id = _initialize_mcp_http(endpoint, timeout, auth_token)
    listed, _ = _mcp_http_exchange(
        endpoint,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        timeout,
        session_id=session_id,
        auth_token=auth_token,
    )
    if not listed:
        raise AdapterError("invalid_response", "HTTP MCP tools/list 未返回结果")
    if "error" in listed:
        raise AdapterError("provider_error", str(listed["error"]))
    tools = listed.get("result", {}).get("tools", [])
    names = sorted(
        str(tool["name"])
        for tool in tools
        if isinstance(tool, dict) and tool.get("name")
    )
    missing = sorted((expected_tools or set()) - set(names))
    if missing:
        raise AdapterError("contract_mismatch", f"MCP tools/list 缺少预期工具：{', '.join(missing)}")
    initialized_result = initialized.get("result") or {}
    return {
        "status": "ready",
        "protocol_version": initialized_result.get("protocolVersion"),
        "server_info": initialized_result.get("serverInfo"),
        "tool_count": len(names),
        "tools": names,
        "latency_ms": round((time.monotonic() - started_at) * 1000),
    }


def call_mcp_http(
    endpoint: str,
    tool: str,
    arguments: dict[str, Any],
    timeout: int,
    auth_token: str | None = None,
) -> Any:
    initialized, session_id = _initialize_mcp_http(endpoint, timeout, auth_token)
    request_id = 2 if initialized.get("id") == 1 else 3
    response, _ = _mcp_http_exchange(
        endpoint,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
        timeout,
        session_id=session_id,
        auth_token=auth_token,
    )
    if not response:
        raise AdapterError("invalid_response", f"HTTP MCP 工具 {tool} 未返回结果")
    if "error" in response:
        message = json.dumps(response["error"], ensure_ascii=False)
        raise AdapterError(_classify_failure(message), message)
    return _mcp_result_payload(response.get("result") or {})


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _https_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.netloc else None


PRICE_PATTERN = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")


def _price(value: Any, basis: str, default_currency: str | None = None) -> dict[str, Any]:
    display = None if value is None else str(value)
    amount = None
    currency = default_currency
    if display:
        match = PRICE_PATTERN.search(display)
        if match and not re.search(r"[xX*?]", display):
            try:
                amount = float(match.group(0).replace(",", ""))
            except ValueError:
                amount = None
        upper = display.upper()
        if "¥" in display or "CNY" in upper or "RMB" in upper:
            currency = "CNY"
        elif "$" in display or "USD" in upper:
            currency = "USD"
    return {"amount": amount, "currency": currency, "display": display, "basis": basis}


def _segments(item: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for journey in item.get("journeys") or []:
        for segment in journey.get("segments") or []:
            normalized.append(
                {
                    "transport_type": segment.get("transportType"),
                    "transport_number": segment.get("marketingTransportNo"),
                    "operator": segment.get("marketingTransportName"),
                    "seat_class": segment.get("seatClassName"),
                    "departure": {
                        "city": segment.get("depCityName"),
                        "city_code": segment.get("depCityCode"),
                        "station": segment.get("depStationName"),
                        "station_code": segment.get("depStationCode"),
                        "terminal": segment.get("depTerm"),
                        "local_datetime": segment.get("depDateTime"),
                    },
                    "arrival": {
                        "city": segment.get("arrCityName"),
                        "city_code": segment.get("arrCityCode"),
                        "station": segment.get("arrStationName"),
                        "station_code": segment.get("arrStationCode"),
                        "terminal": segment.get("arrTerm"),
                        "local_datetime": segment.get("arrDateTime"),
                    },
                    "duration": segment.get("duration"),
                }
            )
    return normalized


def _item_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if not isinstance(raw, dict):
        return []
    for key in ("itemList", "items", "results", "flights", "trains", "hotels", "list"):
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    data = raw.get("data")
    if data is not None and data is not raw:
        nested = _item_list(data)
        if nested:
            return nested
    return []


def _looks_like_single_item(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    identity_fields = {
        "id", "offerId", "flightId", "fnum", "flightNo", "flight_no",
        "trainNo", "train_no", "trainNumber", "FlightNo", "station_name", "name",
    }
    return any(raw.get(field) not in (None, "") for field in identity_fields)


def _sanitize_provider_data(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize_provider_data(item) for item in value]
    if not isinstance(value, dict):
        return value
    clean = {}
    for key, item in value.items():
        lower = key.lower()
        if any(secret in lower for secret in ("token", "cookie", "authorization", "api_key", "apikey")):
            continue
        clean[key] = _sanitize_provider_data(item)
    return clean


def _stable_offer_id(item: dict[str, Any], *candidates: Any) -> str:
    for candidate in candidates:
        if candidate not in (None, ""):
            return str(candidate)
    digest = hashlib.sha256(
        json.dumps(_sanitize_provider_data(item), ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"provider-{digest}"


def normalize_flyai_item(product_type: str, item: dict[str, Any]) -> dict[str, Any]:
    if product_type in {"flight", "train"}:
        segments = _segments(item)
        first = segments[0] if segments else {}
        last = segments[-1] if segments else {}
        number = first.get("transport_number")
        return {
            "offer_id": _stable_offer_id(item, item.get("id"), item.get("offerId"), number),
            "name": number or f"{product_type} option",
            "price": _price(
                item.get("adultPrice") or item.get("ticketPrice") or item.get("price"),
                "per_adult",
                "CNY",
            ),
            "availability": {"status": "provider_returned", "remaining": None},
            "departure": first.get("departure"),
            "arrival": last.get("arrival"),
            "total_duration": item.get("totalDuration"),
            "segments": segments,
            "action_link": _https_url(item.get("jumpUrl")),
        }
    return {
        "offer_id": _stable_offer_id(item, item.get("shId"), item.get("id"), item.get("name")),
        "name": item.get("name"),
        "price": _price(item.get("price"), "per_room_per_night", "CNY"),
        "availability": {"status": "provider_returned", "remaining": None},
        "location": {
            "address": item.get("address"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "nearby": item.get("interestsPoi"),
        },
        "hotel": {
            "brand": item.get("brandName"),
            "star": item.get("star"),
            "score": item.get("score"),
            "score_description": item.get("scoreDesc"),
            "review_summary": item.get("review"),
        },
        "action_link": _https_url(item.get("detailUrl")),
    }


def normalize_variflight_item(product_type: str, item: dict[str, Any]) -> dict[str, Any]:
    if product_type == "train_station":
        station_name = item.get("station_name") or item.get("stationName") or item.get("name")
        station_code = item.get("station_code") or item.get("stationCode")
        return {
            "offer_id": _stable_offer_id(item, station_code, station_name),
            "name": station_name,
            "price": _price(None, "not_applicable"),
            "availability": {"status": "provider_returned", "remaining": None},
            "location": {
                "city": item.get("city_name") or item.get("cityName"),
                "station_code": station_code,
            },
            "action_link": None,
        }

    seat_options = [seat for seat in (item.get("seatLists") or []) if isinstance(seat, dict)]
    priced_seats = [
        seat for seat in seat_options if isinstance(seat.get("seatPrice"), (int, float))
    ]
    cheapest_seat = min(priced_seats, key=lambda seat: seat["seatPrice"]) if priced_seats else {}
    remaining_values = [
        seat.get("ticketLeft")
        for seat in seat_options
        if isinstance(seat.get("ticketLeft"), (int, float))
    ]
    name = (
        item.get("fnum")
        or item.get("flightNo")
        or item.get("flight_no")
        or item.get("FlightNo")
        or item.get("trainNo")
        or item.get("train_no")
        or item.get("trainNumber")
        or item.get("name")
    )
    price_value = (
        item.get("price")
        or item.get("lowestPrice")
        or item.get("lowest_price")
        or item.get("adultPrice")
        or item.get("fare")
        or cheapest_seat.get("seatPrice")
    )
    departure = {
        "city": item.get("depCityName") or item.get("dep_city") or item.get("depcity") or item.get("FlightDep"),
        "station": item.get("depAirportName") or item.get("depStationName") or item.get("dep_station") or item.get("dep") or item.get("FlightDepAirport") or item.get("fromStation"),
        "station_code": item.get("FlightDepcode") or item.get("fromTccode"),
        "terminal": item.get("depTerminal") or item.get("dep_terminal") or item.get("FlightHTerminal"),
        "datetime": item.get("depTime") or item.get("depDateTime") or item.get("dep_time") or item.get("FlightDeptimePlanDate") or item.get("VeryZhunReadyDeptimeDate") or item.get("fromTime"),
    }
    arrival = {
        "city": item.get("arrCityName") or item.get("arr_city") or item.get("arrcity") or item.get("FlightArr"),
        "station": item.get("arrAirportName") or item.get("arrStationName") or item.get("arr_station") or item.get("arr") or item.get("FlightArrAirport") or item.get("toStation"),
        "station_code": item.get("FlightArrcode") or item.get("toTccode"),
        "terminal": item.get("arrTerminal") or item.get("arr_terminal") or item.get("FlightTerminal"),
        "datetime": item.get("arrTime") or item.get("arrDateTime") or item.get("arr_time") or item.get("FlightArrtimePlanDate") or item.get("VeryZhunReadyArrtimeDate") or item.get("toTime"),
    }
    operational = {
        "operator": item.get("airlineName") or item.get("operator") or item.get("railwayBureau") or item.get("FlightCompany"),
        "status": item.get("status") or item.get("flightStatus") or item.get("trainStatus") or item.get("FlightState"),
        "on_time_rate": item.get("onTimeRate") or item.get("on_time_rate") or item.get("OntimeRate"),
        "aircraft": item.get("aircraftType") or item.get("aircraft") or item.get("equipment") or item.get("ftype") or item.get("generic"),
        "seat_class": item.get("seatClass") or item.get("seat_class") or item.get("seatType") or cheapest_seat.get("seatName"),
        "comfort": item.get("happinessIndex") or item.get("comfort") or item.get("comfortIndex"),
    }
    return {
        "offer_id": _stable_offer_id(
            item, item.get("id"), item.get("offerId"), item.get("flightId"), name
        ),
        "name": name or f"{product_type} record",
        "price": _price(price_value, "provider_reported", "CNY" if price_value is not None else None),
        "availability": {
            "status": "provider_returned",
            "remaining": item.get("remaining") if item.get("remaining") is not None else (sum(remaining_values) if remaining_values else None),
        },
        "departure": {key: value for key, value in departure.items() if value not in (None, "")},
        "arrival": {key: value for key, value in arrival.items() if value not in (None, "")},
        "operational": {key: value for key, value in operational.items() if value not in (None, "")},
        "total_duration": item.get("duration") or item.get("FlightDuration") or item.get("useTime"),
        "seat_options": [
            {
                "name": seat.get("seatName"),
                "price": seat.get("seatPrice"),
                "remaining": seat.get("ticketLeft"),
            }
            for seat in seat_options
        ],
        "action_link": _https_url(item.get("jumpUrl") or item.get("bookingUrl") or item.get("url")),
    }


def make_snapshot(
    spec: ProviderSpec,
    product_type: str,
    query: dict[str, Any],
    raw: Any,
    items: list[dict[str, Any]],
    tool: str,
    limit: int | None = None,
) -> dict[str, Any]:
    if limit is not None:
        items = items[:limit]
    raw_hash = _canonical_hash(raw)
    snapshot_seed = {
        "provider": spec.provider_id,
        "product_type": product_type,
        "query": query,
        "checked_at": checked_at(),
        "raw_response_hash": raw_hash,
    }
    captured = snapshot_seed["checked_at"]
    snapshot_id = hashlib.sha256(
        json.dumps(snapshot_seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    snapshot_kind = "quote" if tool in QUOTE_TOOLS else "lookup" if tool in LOOKUP_TOOLS else "operational"
    expires_after = {"quote": 30, "operational": 15, "lookup": 24 * 60}[snapshot_kind]
    refresh_before = {"quote": "purchase", "operational": "departure", "lookup": "use"}[snapshot_kind]
    expires_at = (
        datetime.fromisoformat(captured).astimezone() + timedelta(minutes=expires_after)
    ).isoformat(timespec="seconds")
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "snapshot_kind": snapshot_kind,
        "status": "platform_reported" if items else "no_results",
        "provider": {
            "id": spec.provider_id,
            "name": spec.name,
            "authority": spec.authority,
            "transport": spec.transport,
            "package": spec.package,
            "version": spec.version,
        },
        "product_type": product_type,
        "tool": tool,
        "query": {key: value for key, value in query.items() if value not in (None, "")},
        "freshness": {
            "checked_at": captured,
            "expires_at": expires_at,
            "dynamic": True,
            "planning_validity": "historical_snapshot",
            "refresh_before": refresh_before,
        },
        "items": items,
        "count": len(items),
        "raw_response_hash": raw_hash,
        "source": {
            "title": spec.name,
            "url": spec.source_url,
            "kind": "official_provider_api" if spec.authority == "official_provider" else "official_platform_api",
        },
        "disclaimer": (
            "结果是查询时的平台快照，不代表价格或库存持续有效；提交订单前必须在承运方、"
            "12306 或预订平台重新核验，不得据此声明已经预订。"
        ),
    }


class SourceAdapter(ABC):
    def __init__(self, spec: ProviderSpec):
        self.spec = spec

    def environment(self) -> dict[str, str]:
        if self.spec.provider_id == "fliggy_flyai":
            return load_flyai_environment(os.environ.copy())
        if self.spec.provider_id.startswith("variflight_"):
            return load_variflight_environment(os.environ.copy())
        return os.environ.copy()

    @abstractmethod
    def query(
        self,
        product_type: str,
        tool: str,
        arguments: dict[str, Any],
        query: dict[str, Any],
        timeout: int,
        limit: int | None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class FlyAiAdapter(SourceAdapter):
    def query(
        self,
        product_type: str,
        tool: str,
        arguments: dict[str, Any],
        query: dict[str, Any],
        timeout: int,
        limit: int | None,
    ) -> dict[str, Any]:
        command = provider_command(self.spec) + [tool]
        for key, value in arguments.items():
            if value in (None, ""):
                continue
            command.extend([f"--{key.replace('_', '-')}", str(value)])
        raw = run_json_cli(command, self.environment(), timeout)
        items = [normalize_flyai_item(product_type, item) for item in _item_list(raw)]
        return make_snapshot(self.spec, product_type, query, raw, items, tool, limit)


class McpStdioAdapter(SourceAdapter):
    def query(
        self,
        product_type: str,
        tool: str,
        arguments: dict[str, Any],
        query: dict[str, Any],
        timeout: int,
        limit: int | None,
    ) -> dict[str, Any]:
        environment = self.environment()
        if self.spec.credential_env and not environment.get(self.spec.credential_env):
            raise AdapterError("credential_missing", f"未配置 {self.spec.credential_env}")
        raw = call_mcp_stdio(provider_command(self.spec), tool, arguments, environment, timeout)
        records = _item_list(raw)
        if not records and _looks_like_single_item(raw):
            records = [raw]
        items = [normalize_variflight_item(product_type, item) for item in records]
        return make_snapshot(self.spec, product_type, query, raw, items, tool, limit)


def adapter(provider_id: str) -> SourceAdapter:
    spec = PROVIDERS.get(provider_id)
    if not spec:
        raise AdapterError("unsupported_provider", f"不支持的数据源：{provider_id}")
    if provider_id == "fliggy_flyai":
        return FlyAiAdapter(spec)
    return McpStdioAdapter(spec)


def provider_manifest() -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "providers": {provider_id: asdict(spec) for provider_id, spec in PROVIDERS.items()},
    }
