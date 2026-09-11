"""
Upload sandbox — per-session, capped, disposable.

PRD section 3 lists live CSV/Excel upload as a Non-Goal, for a reason that is
still valid: tabular ingestion costs ONE Groq call per row, so a 200-row upload
is 200 calls, several minutes of waiting, and a large slice of a capped daily
quota — per upload, per visitor.

This is the translation rather than a reversal. Uploads work, but:

  * CSV/Excel is capped at MAX_TABULAR_ROWS, because each row is an API call.
  * DOCX gets a far larger cap, because chunking is local and free.
  * Everything lands in a collection named for the SESSION, never in the
    curated `medical` / `financial` indexes. Two visitors cannot see or poison
    each other's data, and the demo corpora stay exactly as evaluated.
  * Sessions expire, and their collections are deleted with them.

The curated corpora remain read-only at query time and are still ingested
offline, which is what PRD section 3 actually protects.
"""
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

import chromadb

from src.build_index import build_index
from src.config import CHROMA_DIR
from src.schema import KnowledgeUnit

# One Groq call per row. Twenty-five is enough to demonstrate the extractor on
# a visitor's own data and small enough that nobody can drain the day's quota.
MAX_TABULAR_ROWS = 25
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
SESSION_TTL_SECONDS = 60 * 60
MAX_SESSIONS = 50

TABULAR_SUFFIXES = {".csv", ".xlsx", ".xls"}
TEXTUAL_SUFFIXES = {".docx"}


class SandboxError(Exception):
    """A refusal the user should see verbatim — cap exceeded, bad format."""


@dataclass
class Job:
    """Ingestion runs in the background because 25 rows is 25 sequential API
    calls; a request that blocks on that times out on any sane proxy."""

    id: str
    status: str = "pending"  # pending | running | done | failed
    total: int = 0
    done: int = 0
    message: str = ""
    unit_count: int = 0

    def as_dict(self) -> dict:
        return {
            "job_id": self.id, "status": self.status, "total": self.total,
            "done": self.done, "message": self.message, "unit_count": self.unit_count,
            "progress": round(self.done / self.total, 3) if self.total else 0.0,
        }


@dataclass
class Session:
    id: str
    created_at: float = field(default_factory=time.time)
    units: list[KnowledgeUnit] = field(default_factory=list)
    jobs: dict[str, Job] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    @property
    def collection(self) -> str:
        return f"session_{self.id}"

    @property
    def expired(self) -> bool:
        return time.time() - self.created_at > SESSION_TTL_SECONDS

    def as_dict(self) -> dict:
        return {
            "session_id": self.id,
            "collection": self.collection,
            "unit_count": len(self.units),
            "sources": self.sources,
            "expires_in_s": max(0, int(SESSION_TTL_SECONDS - (time.time() - self.created_at))),
        }


class SessionStore:
    """In-memory registry of sandbox sessions.

    Deliberately not persisted: sandbox data is disposable by design, and on
    Render's ephemeral filesystem persisting it would be a lie anyway.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def create(self) -> Session:
        with self._lock:
            self._evict_locked()
            session = Session(id=uuid.uuid4().hex[:12])
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None or session.expired:
            if session is not None:
                self.drop(session_id)
            raise SandboxError(f"Session {session_id} not found or expired.")
        return session

    def drop(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            _delete_collection(session.collection)

    def _evict_locked(self) -> None:
        """Drop expired sessions, then the oldest if still over the cap.

        Without this an unbounded number of Chroma collections accumulates on a
        512MB instance until it is killed.
        """
        for sid in [s.id for s in self._sessions.values() if s.expired]:
            self._sessions.pop(sid, None)
            _delete_collection(f"session_{sid}")

        while len(self._sessions) >= MAX_SESSIONS:
            oldest = min(self._sessions.values(), key=lambda s: s.created_at)
            self._sessions.pop(oldest.id, None)
            _delete_collection(oldest.collection)

    def active(self) -> list[Session]:
        with self._lock:
            return [s for s in self._sessions.values() if not s.expired]


def _delete_collection(name: str) -> None:
    try:
        chromadb.PersistentClient(path=CHROMA_DIR).delete_collection(name)
    except Exception:
        pass  # already gone, or never created — either way there is nothing to clean


def validate_upload(filename: str, size_bytes: int) -> str:
    """Check format and size before anything is written to disk.

    Returns the normalized suffix. Raises SandboxError with a message written
    for the person who will read it in the UI.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in TABULAR_SUFFIXES | TEXTUAL_SUFFIXES:
        supported = ", ".join(sorted(TABULAR_SUFFIXES | TEXTUAL_SUFFIXES))
        raise SandboxError(f"Unsupported file type '{suffix}'. Supported: {supported}")
    if size_bytes > MAX_UPLOAD_BYTES:
        raise SandboxError(
            f"File is {size_bytes / 1024 / 1024:.1f} MB; the limit is "
            f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB."
        )
    return suffix


def count_rows(path: Path) -> int:
    from src.loader import load_tabular

    return len(load_tabular(str(path)))


def check_row_cap(rows: int) -> None:
    if rows > MAX_TABULAR_ROWS:
        raise SandboxError(
            f"That file has {rows} rows; the sandbox accepts {MAX_TABULAR_ROWS}. "
            f"Each row costs one LLM call to turn into a narrative, so an "
            f"unbounded upload would exhaust the shared daily quota. Trim the "
            f"file, or run the offline extractor locally for the full dataset."
        )


def ingest_into_session(session: Session, path: Path, domain: str, job: Job) -> None:
    """Extract and index one uploaded file into the session's own collection.

    Runs in a background thread. Progress is polled via the job id.
    """
    from src.extractors.tabular_extractor import extract_tabular
    from src.extractors.text_extractor import extract_text
    from src.hybrid_retrieval import refresh_caches

    job.status = "running"
    try:
        suffix = path.suffix.lower()
        if suffix in TABULAR_SUFFIXES:
            job.total = count_rows(path)
            check_row_cap(job.total)
            units = extract_tabular(str(path), domain=domain)
        else:
            units = extract_text(str(path))
            job.total = len(units)

        job.done = len(units)

        # Re-tag IDs so a sandbox unit can never collide with a curated one,
        # even if a visitor uploads a file named sample_stocks.csv.
        for unit in units:
            unit.id = f"{session.collection}_{unit.id}"

        session.units.extend(units)
        session.sources.append(path.name)

        # Session collections are named per session, not per domain, so the
        # collection-name guard cannot apply — but the units still carry a real
        # domain tag and that is still worth checking.
        build_index(units, session.collection, expected_domains={"medical", "financial"})
        refresh_caches()

        job.unit_count = len(units)
        job.status = "done"
        job.message = f"Indexed {len(units)} units from {path.name}."
    except SandboxError as exc:
        job.status = "failed"
        job.message = str(exc)
    except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
        job.status = "failed"
        job.message = f"{type(exc).__name__}: {exc}"


STORE = SessionStore()
