"""Reads and writes of `ai_analyses` and `ai_analysis_settings` (migration 010).

The app reads and asks through the migration's functions; only the analysis worker writes analyses.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime

from core.integrations.store import StoreError, _error_message, _Rest
from core.integrations.sync_jobs import (
    JOBS_TABLE,
    OPEN_STATUSES,
    SyncJob,
    _in_filter,
    parse_date,
    parse_timestamp,
)

log = logging.getLogger(__name__)

ANALYSES_TABLE = "ai_analyses"
SETTINGS_TABLE = "ai_analysis_settings"
REQUEST_RPC = "request_ai_analysis"
SAVE_SETTINGS_RPC = "save_ai_analysis_settings"
CLAIM_RPC = "claim_ai_jobs"

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
TRIGGER_SCHEDULED = "scheduled"
TRIGGER_MANUAL = "manual"

_SUMMARY_COLUMNS = ("id,module,subject_id,window_start,window_end,lang,params,params_digest,input_digest,"
                    "agent_version,status,trigger,requested_by,job_id,source_last_success_at,result,model,"
                    "duration_ms,created_at,finished_at,negative_records,harvest_records")
_LATEST_COLUMNS = "id,module,subject_id,window_start,window_end,lang,params,finished_at,synthesis:result->synthesis"
_RECORDS_COLUMNS = "id,negative_records,harvest_records,records"
_LATEST_ROWS_PER_SUBJECT = 4
_ERROR_MAX_CHARS = 500


def analysis_job_kind(module: str) -> str:
    return f"ai_{module}_analysis"


@dataclass(frozen=True)
class StoredAnalysis:
    id: int
    module: str
    subject_id: str
    window_start: date | None
    window_end: date | None
    lang: str
    params: dict
    params_digest: str
    input_digest: str
    agent_version: str
    status: str
    trigger: str
    requested_by: str
    job_id: int | None
    source_last_success_at: datetime | None
    result: dict | None
    model: str
    duration_ms: int | None
    created_at: datetime | None
    finished_at: datetime | None
    negative_records: list = field(default_factory=list)
    harvest_records: list = field(default_factory=list)
    # Filas del análisis para los módulos que no son M2, que guarda las suyas en las dos de arriba.
    records: list = field(default_factory=list)
    session_id: str = ""

    @property
    def done(self) -> bool:
        return self.status == STATUS_DONE

    @classmethod
    def from_row(cls, row: dict) -> StoredAnalysis:
        return cls(
            id=int(row["id"]),
            module=row.get("module") or "",
            subject_id=row.get("subject_id") or "",
            window_start=parse_date(row.get("window_start")),
            window_end=parse_date(row.get("window_end")),
            lang=row.get("lang") or "",
            params=dict(row.get("params") or {}),
            params_digest=row.get("params_digest") or "",
            input_digest=row.get("input_digest") or "",
            agent_version=row.get("agent_version") or "",
            status=row.get("status") or "",
            trigger=row.get("trigger") or "",
            requested_by=row.get("requested_by") or "",
            job_id=int(row["job_id"]) if row.get("job_id") is not None else None,
            source_last_success_at=parse_timestamp(row.get("source_last_success_at")),
            result=row.get("result"),
            model=row.get("model") or "",
            duration_ms=int(row["duration_ms"]) if row.get("duration_ms") is not None else None,
            created_at=parse_timestamp(row.get("created_at")),
            finished_at=parse_timestamp(row.get("finished_at")),
            negative_records=list(row.get("negative_records") or []),
            harvest_records=list(row.get("harvest_records") or []),
            records=list(row.get("records") or []),
            session_id=row.get("session_id") or "",
        )


@dataclass(frozen=True)
class AnalysisSettings:
    params: dict
    updated_by: str
    updated_at: datetime | None


@dataclass(frozen=True)
class AnalysisRequest:
    job_id: int | None
    created: bool
    reason: str


@dataclass(frozen=True)
class NewAnalysis:
    """A run about to call the provider: everything but the answer."""

    module: str
    subject_id: str
    window_start: date
    window_end: date
    lang: str
    params: dict
    params_digest: str
    input_digest: str
    agent_version: str
    trigger: str
    requested_by: str
    job_id: int | None
    source_last_success_at: datetime | None
    negative_records: list
    harvest_records: list
    model: str
    records: list = field(default_factory=list)

    def as_row(self) -> dict:
        return {
            "module": self.module, "subject_id": self.subject_id,
            "window_start": self.window_start.isoformat(), "window_end": self.window_end.isoformat(),
            "lang": self.lang, "params": self.params, "params_digest": self.params_digest,
            "input_digest": self.input_digest, "agent_version": self.agent_version, "status": STATUS_RUNNING,
            "trigger": self.trigger, "requested_by": self.requested_by, "job_id": self.job_id,
            "source_last_success_at": (self.source_last_success_at.isoformat()
                                       if self.source_last_success_at else None),
            "negative_records": self.negative_records, "harvest_records": self.harvest_records,
            "records": self.records,
            "model": self.model, "result": None, "error_message": "", "finished_at": None,
        }


class AiAnalysisStore:
    def __init__(self, rest: _Rest):
        self._rest = rest

    # ── app reads ────────────────────────────────────────────────────────────

    def done_for_input(self, module: str, subject_id: str, input_digest: str) -> StoredAnalysis | None:
        """The newest finished analysis of exactly this data, whatever prompt version wrote it."""
        rows = self._rest.select(ANALYSES_TABLE, {
            "select": "*", "module": f"eq.{module}", "subject_id": f"eq.{subject_id}",
            "input_digest": f"eq.{input_digest}", "status": f"eq.{STATUS_DONE}",
            "order": "finished_at.desc,id.desc", "limit": "1",
        })
        return StoredAnalysis.from_row(rows[0]) if rows else None

    def history(self, module: str, subject_id: str, *, limit: int,
                exclude_id: int | None = None) -> list[StoredAnalysis]:
        """Finished analyses of the account, newest first."""
        params = {"select": _SUMMARY_COLUMNS, "module": f"eq.{module}", "subject_id": f"eq.{subject_id}",
                  "status": f"eq.{STATUS_DONE}", "order": "finished_at.desc,id.desc", "limit": str(limit)}
        if exclude_id is not None:
            params["id"] = f"neq.{exclude_id}"
        return [StoredAnalysis.from_row(row) for row in self._rest.select(ANALYSES_TABLE, params)]

    def latest_by_subject(self, module: str, subject_ids: Iterable[str]) -> list[StoredAnalysis]:
        """The newest finished analysis of each subject, with its synthesis and row records, in subject order.

        PostgREST cannot limit rows per subject, so one read covers most of them and a subject whose
        newest analysis did not fit in it is read on its own.
        """
        wanted = list(dict.fromkeys(str(subject_id) for subject_id in subject_ids))
        if not wanted:
            return []
        limit = len(wanted) * _LATEST_ROWS_PER_SUBJECT
        rows = self._rest.select(ANALYSES_TABLE, {
            "select": _LATEST_COLUMNS, "module": f"eq.{module}", "status": f"eq.{STATUS_DONE}",
            "subject_id": _in_filter(wanted), "order": "finished_at.desc,id.desc", "limit": str(limit),
        })
        newest: dict[str, dict] = {}
        for row in rows:
            newest.setdefault(row["subject_id"], row)
        if len(rows) >= limit:
            for subject_id in wanted:
                if subject_id not in newest:
                    found = self._rest.select(ANALYSES_TABLE, {
                        "select": _LATEST_COLUMNS, "module": f"eq.{module}", "status": f"eq.{STATUS_DONE}",
                        "subject_id": f"eq.{subject_id}", "order": "finished_at.desc,id.desc", "limit": "1",
                    })
                    if found:
                        newest[subject_id] = found[0]
        if not newest:
            return []
        records = {row["id"]: row for row in self._rest.select(ANALYSES_TABLE, {
            "select": _RECORDS_COLUMNS, "id": _in_filter(sorted(row["id"] for row in newest.values())),
        })}
        return [_with_synthesis_only({**newest[subject_id], **records.get(newest[subject_id]["id"], {})})
                for subject_id in wanted if subject_id in newest]

    def settings(self, module: str, subject_id: str) -> AnalysisSettings | None:
        rows = self._rest.select(SETTINGS_TABLE, {"select": "params,updated_by,updated_at",
                                                  "module": f"eq.{module}", "subject_id": f"eq.{subject_id}",
                                                  "limit": "1"})
        return _settings(rows[0]) if rows else None

    def settings_by_subject(self, module: str) -> dict[str, AnalysisSettings]:
        rows = self._rest.select(SETTINGS_TABLE, {"select": "subject_id,params,updated_by,updated_at",
                                                  "module": f"eq.{module}"})
        return {row["subject_id"]: _settings(row) for row in rows}

    def latest_job_for_input(self, module: str, subject_id: str, input_digest: str) -> SyncJob | None:
        rows = self._rest.select(JOBS_TABLE, {
            "select": "*", "job_kind": f"eq.{analysis_job_kind(module)}", "external_account_id": f"eq.{subject_id}",
            "params->>input_digest": f"eq.{input_digest}", "order": "created_at.desc,id.desc", "limit": "1",
        })
        return SyncJob.from_row(rows[0]) if rows else None

    def has_open_job(self, module: str, subject_id: str, input_digest: str) -> bool:
        rows = self._rest.select(JOBS_TABLE, {
            "select": "id", "job_kind": f"eq.{analysis_job_kind(module)}", "external_account_id": f"eq.{subject_id}",
            "params->>input_digest": f"eq.{input_digest}", "status": _in_filter(OPEN_STATUSES), "limit": "1",
        })
        return bool(rows)

    def has_analysis_for_input(self, module: str, subject_id: str, input_digest: str) -> bool:
        """A finished or in-flight analysis of this data already exists."""
        rows = self._rest.select(ANALYSES_TABLE, {
            "select": "id", "module": f"eq.{module}", "subject_id": f"eq.{subject_id}",
            "input_digest": f"eq.{input_digest}", "status": f"in.({STATUS_DONE},{STATUS_RUNNING})", "limit": "1",
        })
        return bool(rows)

    # ── app asks ─────────────────────────────────────────────────────────────

    def save_settings(self, module: str, subject_id: str, params: dict, updated_by: str) -> None:
        try:
            saved = self._rest.rpc(SAVE_SETTINGS_RPC, {"p_module": module, "p_subject_id": subject_id,
                                                       "p_params": params, "p_updated_by": updated_by})
        except Exception as exc:
            raise StoreError(_error_message(exc, "guardar los parámetros de la cuenta")) from exc
        if saved is False:
            raise StoreError("No se pudieron guardar los parámetros: la cuenta ya no está sincronizada.")

    def request_analysis(self, module: str, subject_id: str, *, window_start: date, window_end: date, lang: str,
                         params: dict, input_digest: str, requested_by: str) -> AnalysisRequest:
        try:
            rows = self._rest.rpc(REQUEST_RPC, {
                "p_module": module, "p_subject_id": subject_id, "p_window_start": window_start.isoformat(),
                "p_window_end": window_end.isoformat(), "p_lang": lang, "p_params": params,
                "p_input_digest": input_digest, "p_requested_by": requested_by,
            })
        except Exception as exc:
            raise StoreError(_error_message(exc, "pedir el análisis IA")) from exc
        row = (rows or [{}])[0] if isinstance(rows, list) else (rows or {})
        return AnalysisRequest(job_id=int(row["job_id"]) if row.get("job_id") is not None else None,
                               created=bool(row.get("created")), reason=row.get("reason") or "")

    # ── worker writes ────────────────────────────────────────────────────────

    def claim_due(self, holder: str, limit: int, lease_seconds: int) -> list[SyncJob]:
        rows = self._rest.rpc(CLAIM_RPC, {"p_holder": holder, "p_limit": limit, "p_lease_seconds": lease_seconds})
        return [SyncJob.from_row(row) for row in rows or ()]

    def start(self, analysis: NewAnalysis) -> int:
        """The id of the running row for this data and prompt version; a failed or abandoned one is restarted."""
        key = {"module": f"eq.{analysis.module}", "subject_id": f"eq.{analysis.subject_id}",
               "input_digest": f"eq.{analysis.input_digest}", "agent_version": f"eq.{analysis.agent_version}"}
        existing = self._rest.select(ANALYSES_TABLE, {"select": "id,status", **key, "limit": "1"})
        if not existing:
            return int(self._rest.insert_returning(ANALYSES_TABLE, analysis.as_row())["id"])
        if existing[0]["status"] == STATUS_DONE:
            raise StoreError(f"analysis {existing[0]['id']} already holds this data and prompt version")
        self._rest.update(ANALYSES_TABLE, {"id": f"eq.{existing[0]['id']}"}, analysis.as_row())
        return int(existing[0]["id"])

    def finish(self, analysis_id: int, *, result: dict, response: dict, duration_ms: int, now: datetime) -> None:
        self._rest.update(ANALYSES_TABLE, {"id": f"eq.{analysis_id}"}, {
            "status": STATUS_DONE, "result": result, "session_id": response.get("session_id") or "",
            "request_id": response.get("request_id") or "", "usage": response.get("usage") or {},
            "cost_estimate_usd": response.get("cost_estimate_usd"), "duration_ms": duration_ms,
            "finished_at": now.isoformat(), "error_message": "",
        })
        log.info("ai analysis %s done in %d ms", analysis_id, duration_ms)

    def fail(self, analysis_id: int, *, message: str, now: datetime) -> None:
        self._rest.update(ANALYSES_TABLE, {"id": f"eq.{analysis_id}"}, {
            "status": STATUS_FAILED, "error_message": message[:_ERROR_MAX_CHARS], "finished_at": now.isoformat(),
        })


def _with_synthesis_only(row: dict) -> StoredAnalysis:
    return StoredAnalysis.from_row({**row, "result": {"synthesis": row.get("synthesis") or {}}})


def _settings(row: dict) -> AnalysisSettings:
    return AnalysisSettings(params=dict(row.get("params") or {}), updated_by=row.get("updated_by") or "",
                            updated_at=parse_timestamp(row.get("updated_at")))
