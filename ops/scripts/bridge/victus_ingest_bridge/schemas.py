import time
from dataclasses import asdict, dataclass, field
from typing import Any


DEFAULT_BUCKET = "victus-corpus"
DEFAULT_RAW_PDF_KEY = "raw/source.pdf"

EVENT_PREFIX = "victus"
EVENT_ARTIFACT_DONE = "artifact:done"
EVENT_STAGE_STARTED = "stage:started"
EVENT_STAGE_DONE = "stage:done"
EVENT_ERROR = "error"

PROC_PENDING = "pending"
PROC_PROCESSING = "processing"
PROC_COMPLETED = "completed"
PROC_FAILED = "failed"
RAG_PENDING = "pending"
RAG_INDEXED = "indexed"
RAG_ERROR = "error"


def now_ts() -> int:
    return int(time.time())


def paper_prefix(paper_id: str) -> str:
    return f"papers/{paper_id}/"


def paper_key(paper_id: str, relative_key: str) -> str:
    return f"{paper_prefix(paper_id)}{relative_key.lstrip('/')}"


def normalize_event_type(event_type: str) -> str:
    value = event_type.strip()
    if not value:
        raise ValueError("event_type is required")
    if value.startswith(f"{EVENT_PREFIX}:"):
        return value
    return f"{EVENT_PREFIX}:{value}"


@dataclass(frozen=True)
class PaperStatus:
    paper_id: str
    doi: str | None
    s3_prefix: str
    status_proc: str
    status_rag: str
    last_event: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EventEnvelope:
    event_type: str
    paper_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def channel(self) -> str:
        return normalize_event_type(self.event_type)

    def body(self) -> dict[str, Any]:
        body = {"timestamp": now_ts(), **self.payload}
        if self.paper_id is not None:
            body.setdefault("id", self.paper_id)
        return body


@dataclass(frozen=True)
class ArtifactRef:
    paper_id: str
    artifact_kind: str
    artifact_key: str
    bucket: str = DEFAULT_BUCKET
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.paper_id,
            "artifact_kind": self.artifact_kind,
            "artifact_key": self.artifact_key,
            "bucket": self.bucket,
            "metadata": self.metadata,
        }
