"""Safe JSON-based arq job serializer and deserializer (avoids pickle RCE)."""

import json
from typing import Any, cast


def arq_json_serializer(data: dict[str, Any]) -> bytes:
    """Serialize an arq job/result payload to UTF-8 JSON bytes."""
    return json.dumps(data, default=str, separators=(",", ":")).encode("utf-8")


def arq_json_deserializer(raw: bytes) -> dict[str, Any]:
    """Deserialize an arq job/result payload from UTF-8 JSON bytes."""
    parsed: object = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Invalid arq payload: expected JSON object")
    payload = cast(dict[str, Any], parsed)
    if "a" in payload and isinstance(payload["a"], list):
        payload["a"] = tuple(cast(list[Any], payload["a"]))
    return payload
