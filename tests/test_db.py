"""Tests for the database layer (db.py)."""
import time
import pytest
import db


@pytest.fixture(autouse=True)
def setup_db(db_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()


def _make_session(slug="test-slug", **overrides):
    params = dict(
        question="What should we focus on?",
        admin_token="secret-admin-token",
        timer_seconds=60,
        created_at=time.time(),
    )
    params.update(overrides)
    db.create_session(slug=slug, **params)
    return slug


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

class TestSessionCRUD:
    def test_create_and_retrieve(self):
        _make_session("slug-one")
        s = db.get_session("slug-one")
        assert s is not None
        assert s["slug"] == "slug-one"
        assert s["question"] == "What should we focus on?"
        assert s["admin_token"] == "secret-admin-token"
        assert s["timer_seconds"] == 60
        assert s["status"] == "waiting"

    def test_new_session_has_null_timer_and_closed_at(self):
        _make_session()
        s = db.get_session("test-slug")
        assert s["timer_started_at"] is None
        assert s["closed_at"] is None

    def test_get_nonexistent_returns_none(self):
        assert db.get_session("does-not-exist") is None

    def test_created_at_persisted(self):
        t = time.time()
        _make_session(created_at=t)
        s = db.get_session("test-slug")
        assert abs(s["created_at"] - t) < 0.001


class TestStartTimer:
    def test_sets_status_to_thinking(self):
        _make_session()
        db.start_timer("test-slug", time.time())
        assert db.get_session("test-slug")["status"] == "thinking"

    def test_records_started_at(self):
        _make_session()
        t = time.time()
        db.start_timer("test-slug", t)
        s = db.get_session("test-slug")
        assert abs(s["timer_started_at"] - t) < 0.001


class TestSetStatus:
    def test_update_to_writing(self):
        _make_session()
        db.set_status("test-slug", "writing")
        assert db.get_session("test-slug")["status"] == "writing"

    def test_update_to_closed(self):
        _make_session()
        db.set_status("test-slug", "closed")
        assert db.get_session("test-slug")["status"] == "closed"


class TestCloseSession:
    def test_sets_status_to_closed(self):
        _make_session()
        db.close_session("test-slug", time.time())
        assert db.get_session("test-slug")["status"] == "closed"

    def test_records_closed_at(self):
        _make_session()
        t = time.time()
        db.close_session("test-slug", t)
        s = db.get_session("test-slug")
        assert abs(s["closed_at"] - t) < 0.001

    def test_assigns_distribution_idx_to_all_answers(self):
        _make_session()
        for text in ("A", "B", "C"):
            db.add_answer("test-slug", text, time.time())
        db.close_session("test-slug", time.time())
        # Every answer should now have a distribution_idx assigned
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT distribution_idx FROM answers WHERE session_slug='test-slug'"
            ).fetchall()
        indices = sorted(r[0] for r in rows)
        assert indices == [0, 1, 2]

    def test_distribution_idx_covers_all_positions(self):
        _make_session()
        for text in ("X", "Y", "Z", "W"):
            db.add_answer("test-slug", text, time.time())
        db.close_session("test-slug", time.time())
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT distribution_idx FROM answers WHERE session_slug='test-slug'"
            ).fetchall()
        assert sorted(r[0] for r in rows) == [0, 1, 2, 3]

    def test_resets_distribution_counter_to_zero(self):
        _make_session()
        db.close_session("test-slug", time.time())
        assert db.get_session("test-slug")["distribution_counter"] == 0

    def test_no_distribution_idx_without_answers(self):
        _make_session()
        db.close_session("test-slug", time.time())  # should not raise
        assert db.count_answers("test-slug") == 0


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------

class TestAnswers:
    def setup_method(self):
        _make_session("ans-slug")

    def test_count_initially_zero(self):
        assert db.count_answers("ans-slug") == 0

    def test_add_increments_count(self):
        db.add_answer("ans-slug", "Hello", time.time())
        assert db.count_answers("ans-slug") == 1

    def test_multiple_answers(self):
        db.add_answer("ans-slug", "First", time.time())
        db.add_answer("ans-slug", "Second", time.time())
        assert db.count_answers("ans-slug") == 2

    def test_get_answers_returns_all_texts(self):
        db.add_answer("ans-slug", "Alpha", time.time())
        db.add_answer("ans-slug", "Beta", time.time())
        texts = [r["answer_text"] for r in db.get_answers("ans-slug")]
        assert "Alpha" in texts
        assert "Beta" in texts

    def test_get_answers_ordered_by_submitted_at(self):
        t = time.time()
        db.add_answer("ans-slug", "Earlier", t)
        db.add_answer("ans-slug", "Later", t + 1)
        rows = db.get_answers("ans-slug")
        assert rows[0]["answer_text"] == "Earlier"
        assert rows[1]["answer_text"] == "Later"

    def test_get_next_answer_none_when_empty(self):
        db.close_session("ans-slug", time.time())
        assert db.get_next_answer("ans-slug") is None

    def test_get_next_answer_returns_the_answer(self):
        db.add_answer("ans-slug", "Only answer", time.time())
        db.close_session("ans-slug", time.time())
        row = db.get_next_answer("ans-slug")
        assert row is not None
        assert row["answer_text"] == "Only answer"

    def test_get_next_answer_distributes_all_before_repeating(self):
        """Every answer appears exactly once in the first N calls."""
        texts = ["Alpha", "Beta", "Gamma", "Delta"]
        for t in texts:
            db.add_answer("ans-slug", t, time.time())
        db.close_session("ans-slug", time.time())

        received = [db.get_next_answer("ans-slug")["answer_text"] for _ in texts]
        assert sorted(received) == sorted(texts), "Each answer must be distributed exactly once"

    def test_get_next_answer_no_duplicates_in_first_pass(self):
        for i in range(5):
            db.add_answer("ans-slug", f"Answer {i}", time.time())
        db.close_session("ans-slug", time.time())

        received = [db.get_next_answer("ans-slug")["answer_text"] for _ in range(5)]
        assert len(set(received)) == 5, "No duplicates on the first pass"

    def test_get_next_answer_wraps_when_more_callers_than_answers(self):
        """Extra callers beyond the answer count get a repeated answer rather than an error."""
        db.add_answer("ans-slug", "Solo", time.time())
        db.close_session("ans-slug", time.time())

        row1 = db.get_next_answer("ans-slug")
        row2 = db.get_next_answer("ans-slug")  # wraps back to slot 0
        assert row1["answer_text"] == "Solo"
        assert row2["answer_text"] == "Solo"

    def test_count_is_per_session(self):
        _make_session("other-slug")
        db.add_answer("ans-slug", "X", time.time())
        assert db.count_answers("other-slug") == 0

    def test_answer_schema_has_no_participant_identifiers(self):
        db.add_answer("ans-slug", "text", time.time())
        rows = db.get_answers("ans-slug")
        col_names = [k.lower() for k in rows[0].keys()]
        for forbidden in ("participant", "user_id", "ip", "cookie", "session_id"):
            assert forbidden not in col_names, f"Found forbidden column: {forbidden}"
