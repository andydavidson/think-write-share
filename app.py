"""
Think-Write-Share: anonymous facilitation session web app.

Privacy by design:
- No IP addresses are logged or persisted by this application.
- No cookies that identify participants are set.
- No participant identifiers are stored at any layer.
- Rate limiting uses per-session in-memory counters (not per-IP) so no IP
  is retained even transiently for that purpose.
- Answer storage contains only answer text and a submission timestamp.
"""
import os
import re
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db
from words import generate_slug

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # All JS served from /static — no inline scripts needed.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'none'; "
        "frame-ancestors 'none';"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Do not cache pages that carry the admin token in the URL.
    if "/admin/" in str(request.url):
        response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# Constants and validation
# ---------------------------------------------------------------------------

RESERVED_SLUGS = frozenset({
    "admin", "api", "static", "create", "s", "health",
    "favicon.ico", "robots.txt",
})
SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$')
MAX_SLUG_LEN = 60
MIN_SLUG_LEN = 3
MAX_QUESTION_LEN = 500
MAX_ANSWER_LEN = 5000
MIN_TIMER = 10
MAX_TIMER = 3600


def validate_slug(slug: str) -> Optional[str]:
    """Return an error string, or None if the slug is acceptable."""
    if not slug:
        return "Slug is required."
    if len(slug) < MIN_SLUG_LEN:
        return f"Slug must be at least {MIN_SLUG_LEN} characters."
    if len(slug) > MAX_SLUG_LEN:
        return f"Slug must be at most {MAX_SLUG_LEN} characters."
    if not SLUG_RE.match(slug):
        return (
            "Slug may only contain lowercase letters, numbers, and hyphens, "
            "and must start and end with a letter or number."
        )
    if slug in RESERVED_SLUGS:
        return f"'{slug}' is a reserved name. Please choose another."
    return None


# ---------------------------------------------------------------------------
# Rate limiting — per session, not per IP (privacy by design).
# Limits the total submission rate for a session to reduce flooding.
# ---------------------------------------------------------------------------

_rl_lock = Lock()
_rl_sessions: dict[str, list[float]] = defaultdict(list)
RL_WINDOW_SECONDS = 60
RL_MAX_PER_WINDOW = 50


def _is_rate_limited(slug: str) -> bool:
    """Return True if the session has exceeded the submission rate limit."""
    now = time.time()
    with _rl_lock:
        times = _rl_sessions[slug]
        # Evict entries older than the window
        times[:] = [t for t in times if now - t < RL_WINDOW_SECONDS]
        if len(times) >= RL_MAX_PER_WINDOW:
            return True
        times.append(now)
        return False


# ---------------------------------------------------------------------------
# Effective status helper
# ---------------------------------------------------------------------------

def _effective_status(session) -> str:
    """
    Compute the real status, transitioning 'thinking' → 'writing' when the
    timer has elapsed, and persisting that change to the DB.
    """
    status = session["status"]
    if status == "thinking" and session["timer_started_at"]:
        elapsed = time.time() - session["timer_started_at"]
        if elapsed >= session["timer_seconds"]:
            db.set_status(session["slug"], "writing")
            return "writing"
    return status


# ---------------------------------------------------------------------------
# HTML routes
# Note: Starlette 1.x TemplateResponse signature is (request, name, context).
# The request object is NOT included in the context dict.
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "home.html", {
        "example_code": generate_slug(),
    })


@app.get("/new", response_class=HTMLResponse)
async def new_session_page(request: Request):
    return templates.TemplateResponse(request, "create.html", {
        "suggested_slug": generate_slug(),
    })


@app.get("/join")
async def join_session(request: Request, code: str = ""):
    slug = code.strip().lower()
    if not slug:
        return RedirectResponse("/", status_code=302)
    if db.get_session(slug) is not None:
        return RedirectResponse(f"/s/{slug}", status_code=302)
    return templates.TemplateResponse(request, "home.html", {
        "join_error": f"No session found for \u2018{slug}\u2019. Check the code and try again.",
        "join_code": slug,
        "example_code": generate_slug(),
    }, status_code=404)


@app.post("/create")
async def create_session(
    request: Request,
    slug: str = Form(...),
    question: str = Form(...),
    timer_seconds: int = Form(...),
):
    slug = slug.strip().lower()
    question = question.strip()
    errors = []

    slug_error = validate_slug(slug)
    if slug_error:
        errors.append(slug_error)

    if not question:
        errors.append("Question is required.")
    elif len(question) > MAX_QUESTION_LEN:
        errors.append(f"Question must be at most {MAX_QUESTION_LEN} characters.")

    if not (MIN_TIMER <= timer_seconds <= MAX_TIMER):
        errors.append(f"Timer must be between {MIN_TIMER} and {MAX_TIMER} seconds.")

    if not errors and db.get_session(slug) is not None:
        errors.append(f"The slug '{slug}' is already taken. Please choose another.")

    if errors:
        return templates.TemplateResponse(request, "create.html", {
            "suggested_slug": slug,
            "errors": errors,
            "question": question,
            "timer_seconds": timer_seconds,
        }, status_code=400)

    # Admin token: cryptographically secure random token.
    admin_token = secrets.token_urlsafe(32)
    db.create_session(
        slug=slug,
        question=question,
        admin_token=admin_token,
        timer_seconds=timer_seconds,
        created_at=time.time(),
    )
    return RedirectResponse(f"/admin/{slug}/{admin_token}", status_code=303)


@app.get("/s/{slug}", response_class=HTMLResponse)
async def participant_page(request: Request, slug: str):
    session = db.get_session(slug)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return templates.TemplateResponse(request, "participant.html", {
        "session": session,
    })


@app.get("/admin/{slug}/{admin_token}", response_class=HTMLResponse)
async def admin_page(request: Request, slug: str, admin_token: str):
    session = db.get_session(slug)
    if session is None or not secrets.compare_digest(session["admin_token"], admin_token):
        raise HTTPException(status_code=404, detail="Session not found.")

    # Lazily advance status if timer has expired
    status = _effective_status(session)
    if status != session["status"]:
        session = db.get_session(slug)

    answer_count = db.count_answers(slug)
    base = str(request.base_url).rstrip("/")
    participant_url = f"{base}/s/{slug}"

    return templates.TemplateResponse(request, "admin.html", {
        "session": session,
        "status": status,
        "answer_count": answer_count,
        "participant_url": participant_url,
        "admin_token": admin_token,
    })


@app.post("/admin/{slug}/{admin_token}/start")
async def start_timer(slug: str, admin_token: str):
    session = db.get_session(slug)
    if session is None or not secrets.compare_digest(session["admin_token"], admin_token):
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] != "waiting":
        raise HTTPException(status_code=400, detail="Timer can only be started from the 'waiting' state.")
    db.start_timer(slug, time.time())
    return RedirectResponse(f"/admin/{slug}/{admin_token}", status_code=303)


@app.post("/admin/{slug}/{admin_token}/close")
async def close_submissions(slug: str, admin_token: str):
    session = db.get_session(slug)
    if session is None or not secrets.compare_digest(session["admin_token"], admin_token):
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] == "closed":
        raise HTTPException(status_code=400, detail="Session is already closed.")
    db.close_session(slug, time.time())
    return RedirectResponse(f"/admin/{slug}/{admin_token}", status_code=303)


@app.get("/admin/{slug}/{admin_token}/download.md")
async def download_answers(slug: str, admin_token: str):
    session = db.get_session(slug)
    if session is None or not secrets.compare_digest(session["admin_token"], admin_token):
        raise HTTPException(status_code=404, detail="Session not found.")

    answers = db.get_answers(slug)

    def fmt_ts(ts) -> str:
        if ts is None:
            return "\u2014"
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"# Think\u2013Write\u2013Share: {session['question']}",
        "",
        f"Session: /s/{slug}",
        f"Created: {fmt_ts(session['created_at'])}",
        f"Closed:  {fmt_ts(session['closed_at'])}",
        "",
        "## Answers",
        "",
    ]
    for i, row in enumerate(answers, 1):
        lines.append(f"{i}. {row['answer_text']}")
        lines.append("")

    if not answers:
        lines.append("*(No answers were submitted.)*")
        lines.append("")

    content = "\n".join(lines)
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="tws-{slug}.md"'},
    )


@app.get("/admin/{slug}/{admin_token}/download.pdf")
async def download_pdf(slug: str, admin_token: str):
    session = db.get_session(slug)
    if session is None or not secrets.compare_digest(session["admin_token"], admin_token):
        raise HTTPException(status_code=404, detail="Session not found.")

    answers = db.get_answers(slug)

    def fmt_ts(ts) -> str:
        if ts is None:
            return "\u2014"
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    from pdf_export import generate_pdf
    pdf_bytes = generate_pdf(
        session, answers,
        fmt_ts(session["created_at"]),
        fmt_ts(session["closed_at"]),
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="tws-{slug}.pdf"'},
    )


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/random-slug")
async def api_random_slug():
    return JSONResponse({"slug": generate_slug()})


@app.get("/api/check-slug/{slug}")
async def api_check_slug(slug: str):
    slug = slug.strip().lower()
    error = validate_slug(slug)
    if error:
        return JSONResponse({"available": False, "error": error})
    if db.get_session(slug) is not None:
        return JSONResponse({"available": False, "error": "This slug is already taken."})
    return JSONResponse({"available": True})


@app.get("/api/s/{slug}/state")
async def api_state(slug: str):
    session = db.get_session(slug)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    status = _effective_status(session)
    remaining: Optional[float] = None

    if status == "thinking" and session["timer_started_at"]:
        elapsed = time.time() - session["timer_started_at"]
        remaining = max(0.0, session["timer_seconds"] - elapsed)

    return JSONResponse({
        "status": status,
        "question": session["question"],
        "timer_seconds": session["timer_seconds"],
        "remaining_seconds": remaining,
        "answer_count": db.count_answers(slug),
    })


@app.post("/api/s/{slug}/answer")
async def api_submit_answer(slug: str, request: Request):
    # Rate limit by session — no IP addresses are examined or stored.
    if _is_rate_limited(slug):
        raise HTTPException(status_code=429, detail="Too many submissions. Please wait and try again.")

    session = db.get_session(slug)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    status = _effective_status(session)
    if status != "writing":
        raise HTTPException(status_code=400, detail="Submissions are not open right now.")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.")

    answer_text = str(body.get("answer", "")).strip()
    if not answer_text:
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")
    if len(answer_text) > MAX_ANSWER_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Answer must be at most {MAX_ANSWER_LEN} characters.",
        )

    # Store only the text and timestamp — no participant identifier.
    db.add_answer(slug, answer_text, time.time())
    return JSONResponse({"ok": True})


@app.get("/api/s/{slug}/random-answer")
async def api_random_answer(slug: str):
    session = db.get_session(slug)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] != "closed":
        raise HTTPException(status_code=400, detail="Session is not closed yet.")

    row = db.get_next_answer(slug)
    if row is None:
        return JSONResponse({"answer": None, "message": "No answers were submitted."})
    return JSONResponse({"answer": row["answer_text"]})


# ---------------------------------------------------------------------------
# Custom error pages
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    return templates.TemplateResponse(request, "error.html", {
        "status_code": 404,
        "detail": exc.detail,
    }, status_code=404)


@app.exception_handler(400)
async def bad_request(request: Request, exc: HTTPException):
    return templates.TemplateResponse(request, "error.html", {
        "status_code": 400,
        "detail": exc.detail,
    }, status_code=400)
