"""Integration tests for all HTTP routes via FastAPI TestClient."""
import time
import pytest
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_session(client, slug="my-session", question="Focus question?", timer_seconds=60):
    """POST /create and return (slug, admin_token). Asserts the redirect."""
    resp = client.post(
        "/create",
        data={"slug": slug, "question": question, "timer_seconds": timer_seconds},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    path = urlparse(resp.headers["location"]).path  # works for relative or absolute
    # path: /admin/{slug}/{token}
    parts = path.strip("/").split("/")
    return parts[1], parts[2]  # slug, admin_token


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------

class TestHomepage:
    def test_get_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_contains_slug_input(self, client):
        assert 'name="slug"' in client.get("/").text

    def test_contains_question_input(self, client):
        assert 'name="question"' in client.get("/").text


# ---------------------------------------------------------------------------
# POST /create
# ---------------------------------------------------------------------------

class TestCreateSession:
    def test_valid_data_redirects_to_admin(self, client):
        resp = client.post(
            "/create",
            data={"slug": "good-slug", "question": "Q?", "timer_seconds": 60},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/admin/good-slug/" in resp.headers["location"]

    def test_admin_token_is_in_redirect_url(self, client):
        _, token = _create_session(client)
        assert len(token) > 20  # token_urlsafe(32) produces ~43 chars

    def test_slug_normalised_to_lowercase(self, client):
        # The app calls slug.strip().lower() before validation, so an
        # uppercase slug is accepted after normalisation.
        resp = client.post(
            "/create",
            data={"slug": "UPPERCASE", "question": "Q?", "timer_seconds": 60},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "uppercase" in resp.headers["location"]

    def test_special_chars_in_slug_rejected(self, client):
        resp = client.post(
            "/create",
            data={"slug": "bad_slug!", "question": "Q?", "timer_seconds": 60},
        )
        assert resp.status_code == 400

    def test_slug_with_spaces_rejected(self, client):
        resp = client.post(
            "/create",
            data={"slug": "bad slug", "question": "Q?", "timer_seconds": 60},
        )
        assert resp.status_code == 400

    def test_reserved_slug_rejected(self, client):
        for reserved in ("admin", "api", "create", "static"):
            resp = client.post(
                "/create",
                data={"slug": reserved, "question": "Q?", "timer_seconds": 60},
            )
            assert resp.status_code == 400, f"Expected 400 for reserved slug '{reserved}'"

    def test_empty_question_rejected(self, client):
        resp = client.post(
            "/create",
            data={"slug": "valid-slug", "question": "", "timer_seconds": 60},
        )
        # FastAPI may return 422 (form validation) or the app's own 400
        assert resp.status_code in (400, 422)

    def test_question_too_long_rejected(self, client):
        resp = client.post(
            "/create",
            data={"slug": "valid-slug", "question": "Q" * 501, "timer_seconds": 60},
        )
        assert resp.status_code == 400

    def test_timer_below_minimum_rejected(self, client):
        resp = client.post(
            "/create",
            data={"slug": "valid-slug", "question": "Q?", "timer_seconds": 5},
        )
        assert resp.status_code == 400

    def test_timer_above_maximum_rejected(self, client):
        resp = client.post(
            "/create",
            data={"slug": "valid-slug", "question": "Q?", "timer_seconds": 3601},
        )
        assert resp.status_code == 400

    def test_duplicate_slug_rejected(self, client):
        _create_session(client, slug="taken-slug")
        resp = client.post(
            "/create",
            data={"slug": "taken-slug", "question": "Q?", "timer_seconds": 60},
        )
        assert resp.status_code == 400

    def test_slug_stripped_and_lowercased(self, client):
        # The app calls slug.strip().lower() — a lowercase slug should still work
        resp = client.post(
            "/create",
            data={"slug": " valid-slug ", "question": "Q?", "timer_seconds": 60},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "valid-slug" in resp.headers["location"]


# ---------------------------------------------------------------------------
# GET /s/{slug}  — participant page
# ---------------------------------------------------------------------------

class TestParticipantPage:
    def test_existing_session_returns_200(self, client):
        _create_session(client)
        assert client.get("/s/my-session").status_code == 200

    def test_question_displayed(self, client):
        _create_session(client, question="What is the meaning of life?")
        resp = client.get("/s/my-session")
        assert "What is the meaning of life?" in resp.text

    def test_unknown_session_returns_404(self, client):
        assert client.get("/s/no-such-session").status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/{slug}/{token}
# ---------------------------------------------------------------------------

class TestAdminPage:
    def test_valid_token_returns_200(self, client):
        slug, token = _create_session(client)
        assert client.get(f"/admin/{slug}/{token}").status_code == 200

    def test_wrong_token_returns_404(self, client):
        slug, _ = _create_session(client)
        assert client.get(f"/admin/{slug}/wrong-token").status_code == 404

    def test_unknown_slug_returns_404(self, client):
        assert client.get("/admin/no-slug/any-token").status_code == 404

    def test_participant_url_displayed(self, client):
        slug, token = _create_session(client)
        resp = client.get(f"/admin/{slug}/{token}")
        assert f"/s/{slug}" in resp.text

    def test_question_displayed(self, client):
        slug, token = _create_session(client, question="Team question here")
        resp = client.get(f"/admin/{slug}/{token}")
        assert "Team question here" in resp.text

    def test_cache_control_no_store(self, client):
        slug, token = _create_session(client)
        resp = client.get(f"/admin/{slug}/{token}")
        assert "no-store" in resp.headers.get("cache-control", "")


# ---------------------------------------------------------------------------
# POST /admin/{slug}/{token}/start
# ---------------------------------------------------------------------------

class TestStartTimer:
    def test_start_redirects(self, client):
        slug, token = _create_session(client)
        resp = client.post(f"/admin/{slug}/{token}/start", follow_redirects=False)
        assert resp.status_code == 303

    def test_start_sets_status_thinking(self, client, db_path):
        import db as db_module
        slug, token = _create_session(client)
        client.post(f"/admin/{slug}/{token}/start", follow_redirects=False)
        assert db_module.get_session(slug)["status"] == "thinking"

    def test_start_records_timer_started_at(self, client, db_path):
        import db as db_module
        slug, token = _create_session(client)
        before = time.time()
        client.post(f"/admin/{slug}/{token}/start", follow_redirects=False)
        after = time.time()
        s = db_module.get_session(slug)
        assert before <= s["timer_started_at"] <= after

    def test_wrong_token_returns_404(self, client):
        slug, _ = _create_session(client)
        assert client.post(f"/admin/{slug}/bad-token/start").status_code == 404

    def test_start_twice_returns_400(self, client):
        slug, token = _create_session(client)
        client.post(f"/admin/{slug}/{token}/start", follow_redirects=False)
        resp = client.post(f"/admin/{slug}/{token}/start", follow_redirects=False)
        assert resp.status_code == 400

    def test_start_on_closed_session_returns_400(self, client, db_path):
        import db as db_module
        slug, token = _create_session(client)
        db_module.close_session(slug, time.time())
        resp = client.post(f"/admin/{slug}/{token}/start", follow_redirects=False)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /admin/{slug}/{token}/close
# ---------------------------------------------------------------------------

class TestCloseSubmissions:
    def test_close_redirects(self, client):
        slug, token = _create_session(client)
        resp = client.post(f"/admin/{slug}/{token}/close", follow_redirects=False)
        assert resp.status_code == 303

    def test_close_sets_status_closed(self, client, db_path):
        import db as db_module
        slug, token = _create_session(client)
        client.post(f"/admin/{slug}/{token}/close", follow_redirects=False)
        assert db_module.get_session(slug)["status"] == "closed"

    def test_close_records_closed_at(self, client, db_path):
        import db as db_module
        slug, token = _create_session(client)
        before = time.time()
        client.post(f"/admin/{slug}/{token}/close", follow_redirects=False)
        after = time.time()
        s = db_module.get_session(slug)
        assert before <= s["closed_at"] <= after

    def test_close_twice_returns_400(self, client):
        slug, token = _create_session(client)
        client.post(f"/admin/{slug}/{token}/close", follow_redirects=False)
        resp = client.post(f"/admin/{slug}/{token}/close", follow_redirects=False)
        assert resp.status_code == 400

    def test_wrong_token_returns_404(self, client):
        slug, _ = _create_session(client)
        assert client.post(f"/admin/{slug}/bad-token/close").status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/{slug}/{token}/download.md
# ---------------------------------------------------------------------------

class TestDownloadMarkdown:
    def test_returns_200(self, client):
        slug, token = _create_session(client)
        assert client.get(f"/admin/{slug}/{token}/download.md").status_code == 200

    def test_content_type_is_markdown(self, client):
        slug, token = _create_session(client)
        resp = client.get(f"/admin/{slug}/{token}/download.md")
        assert "markdown" in resp.headers["content-type"]

    def test_content_disposition_filename(self, client):
        slug, token = _create_session(client)
        resp = client.get(f"/admin/{slug}/{token}/download.md")
        assert f"tws-{slug}.md" in resp.headers.get("content-disposition", "")

    def test_contains_question(self, client):
        slug, token = _create_session(client, question="My facilitation question")
        resp = client.get(f"/admin/{slug}/{token}/download.md")
        assert "My facilitation question" in resp.text

    def test_think_write_share_heading(self, client):
        slug, token = _create_session(client)
        resp = client.get(f"/admin/{slug}/{token}/download.md")
        # em-dash: U+2013
        assert "Think\u2013Write\u2013Share" in resp.text

    def test_session_url_in_output(self, client):
        slug, token = _create_session(client)
        resp = client.get(f"/admin/{slug}/{token}/download.md")
        assert f"/s/{slug}" in resp.text

    def test_answers_numbered(self, client, db_path):
        import db as db_module
        slug, token = _create_session(client)
        db_module.set_status(slug, "writing")
        db_module.add_answer(slug, "Answer one", time.time())
        db_module.add_answer(slug, "Answer two", time.time())
        resp = client.get(f"/admin/{slug}/{token}/download.md")
        assert "Answer one" in resp.text
        assert "Answer two" in resp.text
        assert "1." in resp.text
        assert "2." in resp.text

    def test_no_answers_placeholder(self, client):
        slug, token = _create_session(client)
        resp = client.get(f"/admin/{slug}/{token}/download.md")
        assert "No answers" in resp.text

    def test_no_participant_identifiers_in_output(self, client):
        slug, token = _create_session(client)
        text = client.get(f"/admin/{slug}/{token}/download.md").text.lower()
        for forbidden in ("participant_id", "user_id", "ip address", "cookie"):
            assert forbidden not in text

    def test_wrong_token_returns_404(self, client):
        slug, _ = _create_session(client)
        assert client.get(f"/admin/{slug}/bad-token/download.md").status_code == 404


# ---------------------------------------------------------------------------
# GET /api/random-slug
# ---------------------------------------------------------------------------

class TestApiRandomSlug:
    def test_returns_slug(self, client):
        resp = client.get("/api/random-slug")
        assert resp.status_code == 200
        data = resp.json()
        assert "slug" in data
        assert isinstance(data["slug"], str)
        assert len(data["slug"]) > 0

    def test_slug_looks_valid(self, client):
        import re
        slug = client.get("/api/random-slug").json()["slug"]
        assert re.fullmatch(r"[a-z][a-z\-]*[a-z]", slug)


# ---------------------------------------------------------------------------
# GET /api/check-slug/{slug}
# ---------------------------------------------------------------------------

class TestApiCheckSlug:
    def test_fresh_slug_available(self, client):
        resp = client.get("/api/check-slug/fresh-new-slug")
        assert resp.status_code == 200
        assert resp.json()["available"] is True

    def test_taken_slug_not_available(self, client):
        _create_session(client, slug="taken-slug")
        resp = client.get("/api/check-slug/taken-slug")
        assert resp.json()["available"] is False
        assert "error" in resp.json()

    def test_invalid_format_not_available(self, client):
        resp = client.get("/api/check-slug/INVALID_SLUG")
        assert resp.json()["available"] is False
        assert "error" in resp.json()

    def test_reserved_slug_not_available(self, client):
        assert client.get("/api/check-slug/admin").json()["available"] is False


# ---------------------------------------------------------------------------
# GET /api/s/{slug}/state
# ---------------------------------------------------------------------------

class TestApiState:
    def test_valid_session_returns_200(self, client):
        _create_session(client)
        assert client.get("/api/s/my-session/state").status_code == 200

    def test_returns_correct_fields(self, client):
        _create_session(client, question="Focus question?")
        data = client.get("/api/s/my-session/state").json()
        assert data["status"] == "waiting"
        assert data["question"] == "Focus question?"
        assert "timer_seconds" in data
        assert "remaining_seconds" in data
        assert "answer_count" in data

    def test_remaining_seconds_null_when_not_thinking(self, client):
        _create_session(client)
        assert client.get("/api/s/my-session/state").json()["remaining_seconds"] is None

    def test_remaining_seconds_set_when_thinking(self, client, db_path):
        slug, token = _create_session(client)
        client.post(f"/admin/{slug}/{token}/start", follow_redirects=False)
        data = client.get(f"/api/s/{slug}/state").json()
        assert data["status"] == "thinking"
        assert data["remaining_seconds"] is not None
        assert data["remaining_seconds"] > 0

    def test_answer_count_reflects_submissions(self, client, db_path):
        import db as db_module
        _create_session(client)
        db_module.add_answer("my-session", "Answer text", time.time())
        assert client.get("/api/s/my-session/state").json()["answer_count"] == 1

    def test_unknown_session_returns_404(self, client):
        assert client.get("/api/s/no-such/state").status_code == 404

    def test_timer_exhausted_transitions_to_writing(self, client, db_path):
        import db as db_module
        slug, token = _create_session(client, timer_seconds=10)
        db_module.start_timer(slug, time.time() - 60)  # started 60s ago, timer is 10s
        data = client.get(f"/api/s/{slug}/state").json()
        assert data["status"] == "writing"


# ---------------------------------------------------------------------------
# POST /api/s/{slug}/answer
# ---------------------------------------------------------------------------

class TestApiSubmitAnswer:
    @pytest.fixture()
    def writing_slug(self, client, db_path):
        import db as db_module
        slug, _ = _create_session(client)
        db_module.set_status(slug, "writing")
        return slug

    def test_valid_submission_returns_ok(self, writing_slug, client):
        resp = client.post(f"/api/s/{writing_slug}/answer", json={"answer": "My answer"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_answer_persisted_to_db(self, writing_slug, client, db_path):
        import db as db_module
        client.post(f"/api/s/{writing_slug}/answer", json={"answer": "Stored answer"})
        texts = [r["answer_text"] for r in db_module.get_answers(writing_slug)]
        assert "Stored answer" in texts

    def test_empty_answer_rejected(self, writing_slug, client):
        resp = client.post(f"/api/s/{writing_slug}/answer", json={"answer": ""})
        assert resp.status_code == 400

    def test_whitespace_only_answer_rejected(self, writing_slug, client):
        resp = client.post(f"/api/s/{writing_slug}/answer", json={"answer": "   "})
        assert resp.status_code == 400

    def test_answer_over_limit_rejected(self, writing_slug, client):
        resp = client.post(f"/api/s/{writing_slug}/answer", json={"answer": "x" * 5001})
        assert resp.status_code == 400

    def test_answer_at_max_length_accepted(self, writing_slug, client):
        resp = client.post(f"/api/s/{writing_slug}/answer", json={"answer": "x" * 5000})
        assert resp.status_code == 200

    def test_submit_while_waiting_rejected(self, client):
        _create_session(client)  # status is 'waiting'
        resp = client.post("/api/s/my-session/answer", json={"answer": "Too early"})
        assert resp.status_code == 400

    def test_submit_while_thinking_rejected(self, client, db_path):
        slug, token = _create_session(client)
        client.post(f"/admin/{slug}/{token}/start", follow_redirects=False)
        resp = client.post(f"/api/s/{slug}/answer", json={"answer": "Too early"})
        assert resp.status_code == 400

    def test_submit_after_close_rejected(self, client, db_path):
        import db as db_module
        slug, _ = _create_session(client)
        db_module.close_session(slug, time.time())
        resp = client.post(f"/api/s/{slug}/answer", json={"answer": "Too late"})
        assert resp.status_code == 400

    def test_unknown_session_returns_404(self, client):
        resp = client.post("/api/s/unknown/answer", json={"answer": "Hello"})
        assert resp.status_code == 404

    def test_invalid_json_returns_400(self, writing_slug, client):
        resp = client.post(
            f"/api/s/{writing_slug}/answer",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_no_participant_id_stored(self, writing_slug, client, db_path):
        import db as db_module
        client.post(f"/api/s/{writing_slug}/answer", json={"answer": "anon"})
        row = db_module.get_answers(writing_slug)[0]
        col_names = [k.lower() for k in row.keys()]
        for forbidden in ("participant", "user_id", "ip", "cookie"):
            assert forbidden not in col_names


# ---------------------------------------------------------------------------
# GET /api/s/{slug}/random-answer
# ---------------------------------------------------------------------------

class TestApiRandomAnswer:
    def test_returns_answer_when_closed_with_answers(self, client, db_path):
        import db as db_module
        slug, _ = _create_session(client)
        db_module.add_answer(slug, "Great insight", time.time())
        db_module.close_session(slug, time.time())
        resp = client.get(f"/api/s/{slug}/random-answer")
        assert resp.status_code == 200
        assert resp.json()["answer"] == "Great insight"

    def test_returns_null_answer_when_closed_with_no_answers(self, client, db_path):
        import db as db_module
        slug, _ = _create_session(client)
        db_module.close_session(slug, time.time())
        resp = client.get(f"/api/s/{slug}/random-answer")
        assert resp.status_code == 200
        assert resp.json()["answer"] is None

    def test_returns_one_of_many_answers(self, client, db_path):
        import db as db_module
        slug, _ = _create_session(client)
        for text in ("Alpha", "Beta", "Gamma"):
            db_module.add_answer(slug, text, time.time())
        db_module.close_session(slug, time.time())
        answer = client.get(f"/api/s/{slug}/random-answer").json()["answer"]
        assert answer in ("Alpha", "Beta", "Gamma")

    def test_fails_when_not_closed(self, client):
        _create_session(client)  # status: waiting
        resp = client.get("/api/s/my-session/random-answer")
        assert resp.status_code == 400

    def test_fails_when_thinking(self, client, db_path):
        slug, token = _create_session(client)
        client.post(f"/admin/{slug}/{token}/start", follow_redirects=False)
        assert client.get(f"/api/s/{slug}/random-answer").status_code == 400

    def test_unknown_session_returns_404(self, client):
        assert client.get("/api/s/unknown/random-answer").status_code == 404


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    def test_csp_present(self, client):
        assert "content-security-policy" in client.get("/").headers

    def test_csp_script_src_self_only(self, client):
        csp = client.get("/").headers["content-security-policy"]
        assert "script-src 'self'" in csp
        assert "unsafe-inline" not in csp

    def test_csp_frame_ancestors_none(self, client):
        csp = client.get("/").headers["content-security-policy"]
        assert "frame-ancestors 'none'" in csp

    def test_x_frame_options_deny(self, client):
        assert client.get("/").headers.get("x-frame-options") == "DENY"

    def test_x_content_type_options_nosniff(self, client):
        assert client.get("/").headers.get("x-content-type-options") == "nosniff"

    def test_referrer_policy_present(self, client):
        assert "referrer-policy" in client.get("/").headers

    def test_admin_page_no_cache(self, client):
        slug, token = _create_session(client)
        cc = client.get(f"/admin/{slug}/{token}").headers.get("cache-control", "")
        assert "no-store" in cc

    def test_non_admin_page_no_forced_no_cache(self, client):
        # /s/{slug} is not an admin route; it should not be forced to no-store
        _create_session(client)
        cc = client.get("/s/my-session").headers.get("cache-control", "")
        assert "no-store" not in cc
