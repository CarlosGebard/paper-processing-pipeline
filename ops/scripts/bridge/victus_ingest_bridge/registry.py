from typing import Any

from .schemas import PaperStatus

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None
    dict_row = None


class PaperRegistry:
    def __init__(self, dsn: str):
        if psycopg is None:
            raise SystemExit("Missing dependency: psycopg. Install with: cd ops/scripts/bridge && uv sync")
        self.dsn = dsn

    def upsert(self, paper_id: str, doi: str | None, s3_prefix: str) -> PaperStatus:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO paper_registry (paper_id, doi, s3_prefix, last_event)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (paper_id) DO UPDATE
                    SET doi = COALESCE(EXCLUDED.doi, paper_registry.doi),
                        s3_prefix = EXCLUDED.s3_prefix,
                        last_event = now()
                    RETURNING paper_id, doi, s3_prefix, status_proc::text, status_rag::text, last_event
                    """,
                    (paper_id, doi, s3_prefix),
                )
                row = cur.fetchone()
        return PaperStatus(**row)

    def touch(self, paper_id: str) -> PaperStatus:
        return self._update(paper_id)

    def set_processing_status(self, paper_id: str, status: str) -> PaperStatus:
        return self._update(paper_id, status_proc=status)

    def set_rag_status(self, paper_id: str, status: str) -> PaperStatus:
        return self._update(paper_id, status_rag=status)

    def get(self, paper_id: str) -> PaperStatus | None:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT paper_id, doi, s3_prefix, status_proc::text, status_rag::text, last_event
                    FROM paper_registry
                    WHERE paper_id = %s
                    """,
                    (paper_id,),
                )
                row = cur.fetchone()
        return PaperStatus(**row) if row else None

    def require(self, paper_id: str) -> PaperStatus:
        row = self.get(paper_id)
        if row is None:
            raise SystemExit(f"Unknown paper_id: {paper_id}")
        return row

    def _update(
        self,
        paper_id: str,
        status_proc: str | None = None,
        status_rag: str | None = None,
    ) -> PaperStatus:
        assignments = ["last_event = now()"]
        params: list[Any] = []
        if status_proc is not None:
            assignments.append("status_proc = %s")
            params.append(status_proc)
        if status_rag is not None:
            assignments.append("status_rag = %s")
            params.append(status_rag)
        params.append(paper_id)
        sql = f"""
            UPDATE paper_registry
            SET {", ".join(assignments)}
            WHERE paper_id = %s
            RETURNING paper_id, doi, s3_prefix, status_proc::text, status_rag::text, last_event
        """
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
        if not row:
            raise SystemExit(f"Unknown paper_id: {paper_id}")
        return PaperStatus(**row)
