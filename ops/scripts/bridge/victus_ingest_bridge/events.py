import json
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from .schemas import EventEnvelope


@dataclass(frozen=True)
class RedisTarget:
    host: str
    port: int
    db: int


def parse_redis_url(url: str) -> RedisTarget:
    parsed = urlparse(url)
    if parsed.scheme != "redis":
        raise SystemExit("Redis URL must use redis://")
    db_text = parsed.path.strip("/") or "0"
    return RedisTarget(parsed.hostname or "redis", parsed.port or 6379, int(db_text))


def _encode_command(*parts: str) -> bytes:
    payload = [f"*{len(parts)}\r\n".encode("utf-8")]
    for part in parts:
        data = part.encode("utf-8")
        payload.append(f"${len(data)}\r\n".encode("utf-8"))
        payload.append(data + b"\r\n")
    return b"".join(payload)


def _read_line(sock: socket.socket) -> bytes:
    chunks = []
    while True:
        byte = sock.recv(1)
        if not byte:
            raise RuntimeError("Redis connection closed")
        chunks.append(byte)
        if b"".join(chunks).endswith(b"\r\n"):
            return b"".join(chunks)


class EventBus:
    def __init__(self, redis_url: str):
        self.target = parse_redis_url(redis_url)

    def publish(self, event_type: str, paper_id: str | None = None, payload: dict | None = None) -> dict:
        envelope = EventEnvelope(event_type=event_type, paper_id=paper_id, payload=payload or {})
        body = envelope.body()
        receivers = self.publish_json(envelope.channel(), body)
        return {"event": envelope.channel(), "payload": body, "receivers": receivers}

    def publish_json(self, channel: str, payload: dict) -> int:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with socket.create_connection((self.target.host, self.target.port), timeout=5) as sock:
            if self.target.db:
                sock.sendall(_encode_command("SELECT", str(self.target.db)))
                response = _read_line(sock)
                if not response.startswith(b"+OK"):
                    raise RuntimeError(f"Redis SELECT failed: {response!r}")
            sock.sendall(_encode_command("PUBLISH", channel, body))
            response = _read_line(sock)
        if not response.startswith(b":"):
            raise RuntimeError(f"Redis PUBLISH failed: {response!r}")
        return int(response[1:-2])
