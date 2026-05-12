from pathlib import Path
from typing import Any

from .config import BridgeConfig
from .events import EventBus
from .hashing import sha256_file
from .registry import PaperRegistry
from .schemas import (
    DEFAULT_RAW_PDF_KEY,
    EVENT_ARTIFACT_DONE,
    EVENT_ERROR,
    EVENT_STAGE_DONE,
    EVENT_STAGE_STARTED,
    PROC_COMPLETED,
    PROC_FAILED,
    PROC_PROCESSING,
    RAG_ERROR,
    RAG_INDEXED,
    ArtifactRef,
    paper_key,
    paper_prefix,
)
from .storage import ObjectStorage


class VictusBridge:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self.registry = PaperRegistry(config.pg_dsn)
        self.events = EventBus(config.redis_url)
        self.storage = ObjectStorage(
            config.s3_endpoint,
            config.s3_access_key,
            config.s3_secret_key,
            config.aws_region,
        )

    def ingest_pdf(self, path: Path, doi: str | None = None) -> dict[str, Any]:
        paper_id = sha256_file(path)
        s3_prefix = paper_prefix(paper_id)
        self.registry.upsert(paper_id, doi, s3_prefix)
        self.registry.set_processing_status(paper_id, PROC_PROCESSING)
        key = paper_key(paper_id, DEFAULT_RAW_PDF_KEY)
        uploaded = self.storage.put_file(
            self.config.s3_bucket,
            key,
            path,
            metadata={"sha256": paper_id, "artifact_kind": "source_pdf"},
        )
        status = self.registry.set_processing_status(paper_id, PROC_COMPLETED)
        return {
            "paper": status.to_dict(),
            "bucket": self.config.s3_bucket,
            "artifact_key": key,
            "uploaded": uploaded,
        }

    def mark_artifact_done(
        self,
        paper_id: str,
        artifact_kind: str,
        artifact_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = self.registry.require(paper_id)
        self.registry.touch(paper_id)
        artifact = ArtifactRef(
            paper_id=paper_id,
            artifact_kind=artifact_kind,
            artifact_key=artifact_key,
            bucket=self.config.s3_bucket,
            metadata=metadata or {},
        )
        result = self.events.publish(EVENT_ARTIFACT_DONE, paper_id, artifact.to_payload())
        return {"paper": status.to_dict(), **result}

    def publish_event(
        self,
        event_type: str,
        paper_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if paper_id:
            self.registry.touch(paper_id)
        return self.events.publish(event_type, paper_id, payload or {})

    def publish_error(
        self,
        service: str,
        error_type: str,
        message: str,
        severity: str,
        paper_id: str | None = None,
        stacktrace: str | None = None,
    ) -> dict[str, Any]:
        if paper_id:
            self.registry.touch(paper_id)
        payload = {
            "service": service,
            "error_type": error_type,
            "message": message,
            "severity": severity,
        }
        if stacktrace:
            payload["stacktrace"] = stacktrace
        return self.events.publish(EVENT_ERROR, paper_id, payload)

    def mark_stage_started(
        self,
        paper_id: str,
        stage: str,
        worker_id: str | None = None,
    ) -> dict[str, Any]:
        status = self._apply_stage_start(paper_id, stage)
        payload = {"stage": stage}
        if worker_id:
            payload["worker_id"] = worker_id
        result = self.events.publish(EVENT_STAGE_STARTED, paper_id, payload)
        return {"paper": status.to_dict(), **result}

    def mark_stage_done(
        self,
        paper_id: str,
        stage: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = self._apply_stage_done(paper_id, stage)
        payload = {"stage": stage, "metadata": metadata or {}}
        result = self.events.publish(EVENT_STAGE_DONE, paper_id, payload)
        return {"paper": status.to_dict(), **result}

    def status(self, paper_id: str) -> dict[str, Any]:
        return self.registry.require(paper_id).to_dict()

    def _apply_stage_start(self, paper_id: str, stage: str):
        if stage == "processing":
            return self.registry.set_processing_status(paper_id, PROC_PROCESSING)
        return self.registry.touch(paper_id)

    def _apply_stage_done(self, paper_id: str, stage: str):
        if stage == "processing":
            return self.registry.set_processing_status(paper_id, PROC_COMPLETED)
        if stage == "processing_failed":
            return self.registry.set_processing_status(paper_id, PROC_FAILED)
        if stage == "rag":
            return self.registry.set_rag_status(paper_id, RAG_INDEXED)
        if stage == "rag_error":
            return self.registry.set_rag_status(paper_id, RAG_ERROR)
        return self.registry.touch(paper_id)
