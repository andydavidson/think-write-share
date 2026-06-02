"""Tests for slug validation, _effective_status, and rate limiting."""
import time
import pytest
from unittest.mock import patch

from app import (
    validate_slug,
    _effective_status,
    _is_rate_limited,
    _rl_sessions,
    RL_MAX_PER_WINDOW,
    MIN_SLUG_LEN,
    MAX_SLUG_LEN,
)


# ---------------------------------------------------------------------------
# validate_slug
# ---------------------------------------------------------------------------

class TestValidateSlug:
    def test_valid_simple_slug(self):
        assert validate_slug("my-cool-slug") is None

    def test_valid_alphanumeric(self):
        assert validate_slug("abc123") is None

    def test_valid_hyphens_in_middle(self):
        assert validate_slug("one-two-three") is None

    def test_empty_slug(self):
        assert validate_slug("") is not None

    def test_too_short(self):
        assert validate_slug("ab") is not None

    def test_exactly_min_length(self):
        assert validate_slug("a" * MIN_SLUG_LEN) is None

    def test_too_long(self):
        assert validate_slug("a" * (MAX_SLUG_LEN + 1)) is not None

    def test_exactly_max_length(self):
        assert validate_slug("a" * MAX_SLUG_LEN) is None

    def test_uppercase_rejected(self):
        assert validate_slug("My-Slug") is not None

    def test_starts_with_hyphen(self):
        assert validate_slug("-my-slug") is not None

    def test_ends_with_hyphen(self):
        assert validate_slug("my-slug-") is not None

    def test_spaces_rejected(self):
        assert validate_slug("my slug") is not None

    def test_underscore_rejected(self):
        assert validate_slug("my_slug") is not None

    def test_dot_rejected(self):
        assert validate_slug("my.slug") is not None

    def test_reserved_admin(self):
        assert validate_slug("admin") is not None

    def test_reserved_api(self):
        assert validate_slug("api") is not None

    def test_reserved_create(self):
        assert validate_slug("create") is not None

    def test_reserved_static(self):
        assert validate_slug("static") is not None

    def test_reserved_health(self):
        assert validate_slug("health") is not None

    def test_error_message_for_empty(self):
        err = validate_slug("")
        assert "required" in err.lower()

    def test_error_message_for_reserved(self):
        err = validate_slug("admin")
        assert "reserved" in err.lower()


# ---------------------------------------------------------------------------
# _effective_status
# ---------------------------------------------------------------------------

class TestEffectiveStatus:
    """_effective_status reads session dict keys; a plain dict works as a stub."""

    def _session(self, status, timer_started_at=None, timer_seconds=60, slug="test-slug"):
        return {
            "slug": slug,
            "status": status,
            "timer_started_at": timer_started_at,
            "timer_seconds": timer_seconds,
        }

    def test_waiting_unchanged(self):
        with patch("app.db.set_status") as mock_set:
            result = _effective_status(self._session("waiting"))
        assert result == "waiting"
        mock_set.assert_not_called()

    def test_writing_unchanged(self):
        with patch("app.db.set_status") as mock_set:
            result = _effective_status(self._session("writing"))
        assert result == "writing"
        mock_set.assert_not_called()

    def test_closed_unchanged(self):
        with patch("app.db.set_status") as mock_set:
            result = _effective_status(self._session("closed"))
        assert result == "closed"
        mock_set.assert_not_called()

    def test_thinking_before_timer_expiry_stays_thinking(self):
        started = time.time() - 10  # 10 s elapsed, timer is 60 s
        session = self._session("thinking", timer_started_at=started, timer_seconds=60)
        with patch("app.db.set_status") as mock_set:
            result = _effective_status(session)
        assert result == "thinking"
        mock_set.assert_not_called()

    def test_thinking_after_timer_expiry_transitions_to_writing(self):
        started = time.time() - 120  # 120 s elapsed, timer is 60 s
        session = self._session("thinking", timer_started_at=started, timer_seconds=60)
        with patch("app.db.set_status") as mock_set:
            result = _effective_status(session)
        assert result == "writing"
        mock_set.assert_called_once_with("test-slug", "writing")

    def test_thinking_exactly_at_expiry_transitions(self):
        started = time.time() - 60  # exactly at boundary
        session = self._session("thinking", timer_started_at=started, timer_seconds=60)
        with patch("app.db.set_status"):
            result = _effective_status(session)
        assert result == "writing"

    def test_thinking_with_no_timer_started_stays_thinking(self):
        session = self._session("thinking", timer_started_at=None)
        with patch("app.db.set_status") as mock_set:
            result = _effective_status(session)
        assert result == "thinking"
        mock_set.assert_not_called()

    def test_db_updated_on_transition(self, db_path, monkeypatch):
        import db as db_module
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        db_module.init_db()
        db_module.create_session("trans-slug", "Q?", "tok", 30, time.time())
        db_module.start_timer("trans-slug", time.time() - 60)

        session = db_module.get_session("trans-slug")
        _effective_status(session)

        updated = db_module.get_session("trans-slug")
        assert updated["status"] == "writing"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    def test_first_call_not_limited(self):
        _rl_sessions.clear()
        assert _is_rate_limited("slug-a") is False

    def test_under_limit_never_blocked(self):
        _rl_sessions.clear()
        slug = "under-limit"
        for _ in range(RL_MAX_PER_WINDOW - 1):
            assert _is_rate_limited(slug) is False

    def test_blocked_after_max_submissions(self):
        _rl_sessions.clear()
        slug = "at-limit"
        for _ in range(RL_MAX_PER_WINDOW):
            _is_rate_limited(slug)
        # One over the limit
        assert _is_rate_limited(slug) is True

    def test_different_sessions_are_independent(self):
        _rl_sessions.clear()
        slug_a = "session-a"
        slug_b = "session-b"
        for _ in range(RL_MAX_PER_WINDOW):
            _is_rate_limited(slug_a)
        # session-a is exhausted; session-b should be unaffected
        assert _is_rate_limited(slug_b) is False

    def test_old_entries_evicted(self):
        _rl_sessions.clear()
        slug = "evict-test"
        # Manually insert timestamps that are outside the window
        import app as app_module
        old_time = time.time() - app_module.RL_WINDOW_SECONDS - 1
        app_module._rl_sessions[slug] = [old_time] * RL_MAX_PER_WINDOW
        # Old entries should be evicted; the call should succeed
        assert _is_rate_limited(slug) is False
