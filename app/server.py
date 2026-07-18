from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles


logger = logging.getLogger("tl_logbook")

APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
SESSION_ROOT = DATA_DIR / "sessions"
COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "tl_logbook_session")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "auto").lower()
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(24 * 60 * 60)))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(80 * 1024 * 1024)))
PARSE_TIMEOUT_SECONDS = int(os.getenv("PARSE_TIMEOUT_SECONDS", "120"))
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "500"))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "3600"))

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{24,96}$")

GENERIC_PARSE_ERROR = "Could not process this PDF as a FOCA logbook export."

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' https://unpkg.com; "
        "style-src 'self' https://unpkg.com 'unsafe-inline'; "
        "img-src 'self' data: https://unpkg.com https://*.basemaps.cartocdn.com; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}

INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
LEGAL_HTML = (STATIC_DIR / "legal.html").read_text(encoding="utf-8")


class ParseError(ValueError):
    """A parse failure whose message is safe to show to the client."""


@dataclass
class SessionState:
    session_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = "idle"
    step: str = "Waiting"
    progress: int = 0
    message: str = "Upload a FOCA logbook PDF to start."
    source_filename: str = ""
    summary: dict[str, Any] | None = None
    job_token: str = ""
    lock: threading.RLock = field(default_factory=threading.RLock)


_sessions: dict[str, SessionState] = {}
_sessions_lock = threading.RLock()
_cleanup_task: asyncio.Task | None = None


def now() -> float:
    return time.time()


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def valid_session_id(value: str | None) -> bool:
    return bool(value and SESSION_ID_RE.fullmatch(value))


@lru_cache(maxsize=1)
def session_secret() -> bytes:
    env_secret = os.getenv("SESSION_SECRET", "")
    if env_secret:
        return env_secret.encode("utf-8")
    path = DATA_DIR / ".session_secret"
    try:
        data = path.read_bytes().strip()
        if len(data) >= 32:
            return data
    except OSError:
        pass
    secret = secrets.token_hex(32).encode("ascii")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(secret)
    return secret


def sign_session_id(session_id: str) -> str:
    return hmac.new(session_secret(), session_id.encode("ascii"), hashlib.sha256).hexdigest()[:32]


def cookie_value(session_id: str) -> str:
    return f"{session_id}.{sign_session_id(session_id)}"


def session_id_from_cookie(value: str | None) -> str | None:
    # Only honor IDs this server issued: the cookie carries "<id>.<hmac>".
    if not value or "." not in value:
        return None
    session_id, _, signature = value.rpartition(".")
    if not valid_session_id(session_id):
        return None
    if not hmac.compare_digest(sign_session_id(session_id), signature):
        return None
    return session_id


def cookie_secure_flag(request: Request) -> bool:
    if COOKIE_SECURE == "true":
        return True
    if COOKIE_SECURE == "false":
        return False
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


def session_dir(session_id: str) -> Path:
    if not valid_session_id(session_id):
        raise ValueError("Invalid session id")
    return SESSION_ROOT / session_id


def summary_path(session_id: str) -> Path:
    return session_dir(session_id) / "summary.json"


def count_session_dirs() -> int:
    try:
        return sum(1 for path in SESSION_ROOT.iterdir() if path.is_dir())
    except OSError:
        return 0


def empty_dashboard_summary() -> dict[str, Any]:
    return {
        "meta": {
            "is_empty": True,
            "owner": "",
            "source_filename": "",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "flight_count": 0,
            "first_date": "",
            "last_date": "",
        },
        "totals": {
            "flights": 0,
            "landings": 0,
            "total_minutes": 0,
            "pic_minutes": 0,
            "dual_minutes": 0,
            "copi_minutes": 0,
            "instructor_minutes": 0,
            "xc_minutes": 0,
            "pic_xc_minutes": 0,
            "xc_distance_nm": 0.0,
            "pic_xc_distance_nm": 0.0,
            "unique_airports": 0,
            "unique_routes": 0,
        },
        "aircraft_types": [],
        "registrations": [],
        "pic_names": [],
        "monthly": [],
        "yearly": [],
        "airports": [],
        "routes": [],
        "recent_flights": [],
        "unresolved_airports": [],
    }


def set_state(state: SessionState, **updates: Any) -> None:
    with state.lock:
        for key, value in updates.items():
            setattr(state, key, value)
        state.updated_at = now()


def load_persisted_summary(session_id: str) -> dict[str, Any] | None:
    path = summary_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_or_create_session(session_id: str) -> SessionState:
    with _sessions_lock:
        state = _sessions.get(session_id)
        if state:
            state.updated_at = now()
            return state

        persisted = load_persisted_summary(session_id)
        state = SessionState(session_id=session_id)
        if persisted:
            state.status = "ready"
            state.step = "Ready"
            state.progress = 100
            state.message = "Logbook loaded for this browser session."
            state.source_filename = persisted.get("meta", {}).get("source_filename", "")
            state.summary = persisted
        _sessions[session_id] = state
        return state


def status_payload(state: SessionState) -> dict[str, Any]:
    with state.lock:
        return {
            "status": state.status,
            "step": state.step,
            "progress": state.progress,
            "message": state.message,
            "source_filename": state.source_filename,
            "updated_at": int(state.updated_at),
            "has_logbook": state.summary is not None,
        }


def cleanup_expired_sessions() -> None:
    cutoff = now() - SESSION_TTL_SECONDS
    # With the parse timeout a session cannot legitimately stay "processing"
    # much longer than PARSE_TIMEOUT_SECONDS; anything older is stuck.
    stuck_cutoff = now() - (PARSE_TIMEOUT_SECONDS + 300)
    with _sessions_lock:
        for session_id, state in list(_sessions.items()):
            if state.updated_at >= cutoff:
                continue
            if state.status == "processing" and state.updated_at >= stuck_cutoff:
                continue
            _sessions.pop(session_id, None)

    SESSION_ROOT.mkdir(parents=True, exist_ok=True)
    for path in SESSION_ROOT.iterdir():
        if not path.is_dir() or not valid_session_id(path.name):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                shutil.rmtree(path)
        except Exception:
            pass


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(cleanup_expired_sessions)
        except Exception:
            logger.exception("Periodic session cleanup failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task
    SESSION_ROOT.mkdir(parents=True, exist_ok=True)
    session_secret()
    await asyncio.to_thread(cleanup_expired_sessions)
    _cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    _cleanup_task.cancel()


app = FastAPI(title="TL-Logbook-Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def session_middleware(request: Request, call_next):
    session_id = session_id_from_cookie(request.cookies.get(COOKIE_NAME))
    should_set_cookie = False
    if not session_id:
        session_id = new_session_id()
        should_set_cookie = True

    request.state.session = get_or_create_session(session_id)
    response = await call_next(request)

    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)

    if should_set_cookie:
        response.set_cookie(
            COOKIE_NAME,
            cookie_value(session_id),
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            samesite="lax",
            secure=cookie_secure_flag(request),
            path="/",
        )
    return response


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/legal", response_class=HTMLResponse)
def legal() -> str:
    return LEGAL_HTML


@app.get("/api/status")
def status(request: Request) -> dict[str, Any]:
    return status_payload(request.state.session)


@app.get("/api/dashboard")
def dashboard(request: Request) -> dict[str, Any]:
    state: SessionState = request.state.session
    with state.lock:
        state.updated_at = now()
        if state.summary:
            return state.summary
    return empty_dashboard_summary()


def run_parser_subprocess(state: SessionState, pdf_path: Path, out_path: Path, filename: str) -> None:
    # Parse in a disposable child process: a crafted PDF cannot pin this
    # process's CPU past the timeout or reach other sessions' data on exploit.
    command = [
        sys.executable,
        str(APP_DIR / "logbook_parser.py"),
        str(pdf_path),
        "--output",
        str(out_path),
        "--source-filename",
        filename,
        "--progress",
    ]
    timed_out = threading.Event()

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(APP_DIR),
    )

    def kill_on_timeout() -> None:
        timed_out.set()
        proc.kill()

    killer = threading.Timer(PARSE_TIMEOUT_SECONDS, kill_on_timeout)
    killer.start()
    user_error = ""
    diagnostics: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("PROGRESS "):
                parts = line.split()
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    page_number, total_pages = int(parts[1]), int(parts[2])
                    progress = 35 + int((page_number / max(total_pages, 1)) * 42)
                    set_state(
                        state,
                        status="processing",
                        step="Parsing",
                        progress=min(progress, 78),
                        message=f"Reading FOCA page {page_number} of {total_pages}.",
                    )
            elif line.startswith("ERROR: "):
                user_error = line[len("ERROR: ") :]
            elif line:
                diagnostics.append(line)
        returncode = proc.wait()
    finally:
        killer.cancel()

    if timed_out.is_set():
        raise ParseError("Parsing took too long and was stopped. Try a smaller export.")
    if returncode == 3:
        raise ParseError(user_error or GENERIC_PARSE_ERROR)
    if returncode != 0:
        logger.error("Parser subprocess failed (rc=%s): %s", returncode, " | ".join(diagnostics[-10:]))
        raise RuntimeError(f"Parser subprocess exited with code {returncode}")


def process_upload(session_id: str, token: str, pdf_path: Path, filename: str) -> None:
    state = get_or_create_session(session_id)
    out_path = pdf_path.with_name(f"{token}.summary.tmp.json")
    try:
        set_state(state, status="processing", step="Parsing", progress=35, message="Reading FOCA tables and flight remarks.")

        run_parser_subprocess(state, pdf_path, out_path, filename)
        summary = json.loads(out_path.read_text(encoding="utf-8"))

        set_state(state, status="processing", step="Building analytics", progress=82, message="Calculating routes, PIC XC, aircraft, and registrations.")
        summary_path(session_id).write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")

        with state.lock:
            if state.job_token != token:
                return
            state.summary = summary
            state.source_filename = filename
            state.status = "ready"
            state.step = "Ready"
            state.progress = 100
            state.message = "Logbook processed for this browser session."
            state.updated_at = now()
    except Exception as exc:
        if isinstance(exc, ParseError):
            message = str(exc)
            logger.info("Parse rejected for session upload: %s", message)
        else:
            message = GENERIC_PARSE_ERROR
            logger.exception("Upload processing failed")
        with state.lock:
            if state.job_token == token:
                state.status = "error"
                state.step = "Error"
                state.progress = 100
                state.message = message
                state.updated_at = now()
    finally:
        # Data minimization: only the derived summary is kept, never the PDF.
        for path in (pdf_path, out_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        # Drop the session dir if nothing was persisted so failed uploads
        # do not count toward MAX_SESSIONS.
        try:
            pdf_path.parent.rmdir()
        except OSError:
            pass


@app.post("/api/upload")
async def upload_logbook(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    state: SessionState = request.state.session
    filename = Path(file.filename or "logbook.pdf").name
    content_type = (file.content_type or "").lower()
    if not (filename.lower().endswith(".pdf") or content_type in {"application/pdf", "application/octet-stream"}):
        raise HTTPException(status_code=400, detail="Upload a PDF file.")

    session_path = session_dir(state.session_id)
    if not session_path.exists() and await asyncio.to_thread(count_session_dirs) >= MAX_SESSIONS:
        raise HTTPException(status_code=429, detail="The server is at capacity. Try again later.")

    with state.lock:
        if state.status == "processing":
            raise HTTPException(status_code=409, detail="This session is already processing an upload.")
        token = secrets.token_hex(16)
        state.job_token = token
        state.status = "uploading"
        state.step = "Uploading"
        state.progress = 8
        state.message = "Receiving PDF."
        state.updated_at = now()

    session_path.mkdir(parents=True, exist_ok=True)
    tmp_path = session_path / f"{token}.uploading.pdf"

    total = 0
    first_chunk = b""
    try:
        handle = await asyncio.to_thread(tmp_path.open, "wb")
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                if not first_chunk:
                    first_chunk = chunk[:1024]
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="PDF is larger than the configured upload limit.")
                await asyncio.to_thread(handle.write, chunk)
        finally:
            await asyncio.to_thread(handle.close)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        finally:
            raise

    if total < 512 or b"%PDF" not in first_chunk:
        try:
            tmp_path.unlink()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="The uploaded file does not look like a valid PDF.")

    set_state(state, status="processing", step="Queued", progress=20, message="Starting parser.", source_filename=filename)
    thread = threading.Thread(target=process_upload, args=(state.session_id, token, tmp_path, filename), daemon=True)
    thread.start()

    return JSONResponse({"status": "ok", "message": "Upload received.", "bytes": total})


@app.post("/api/reset")
def reset_session(request: Request) -> dict[str, Any]:
    state: SessionState = request.state.session
    with state.lock:
        if state.status == "processing":
            raise HTTPException(status_code=409, detail="Wait for the current upload to finish before clearing the session.")
        state.summary = None
        state.source_filename = ""
        state.status = "idle"
        state.step = "Waiting"
        state.progress = 0
        state.message = "Upload a FOCA logbook PDF to start."
        state.job_token = ""
        state.updated_at = now()

    path = session_dir(state.session_id)
    if path.exists():
        shutil.rmtree(path)
    return {"status": "ok"}
