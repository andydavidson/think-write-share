/**
 * participant.js — polls session state and updates the participant UI.
 *
 * Privacy notes:
 * - No participant identifier is ever sent to the server.
 * - sessionStorage is used (not localStorage) to track whether this browser
 *   tab has already submitted, purely to prevent accidental duplicate
 *   submission. The key is tab-scoped and session-specific; nothing is sent
 *   to the server to enforce this.
 * - The server does not set or read any cookie linked to a participant.
 */

(function () {
  "use strict";

  const slug = document.getElementById("page-data").dataset.slug;
  const statusArea = document.getElementById("status-area");
  const POLL_INTERVAL = 1500; // ms

  // Client-side duplicate-submission guard (no server-side identifier used).
  const SUBMITTED_KEY = "tws-submitted-" + slug;
  let alreadySubmitted = sessionStorage.getItem(SUBMITTED_KEY) === "true";

  let uiMode = "unknown";       // what's currently rendered in statusArea
  let timerInterval = null;     // setInterval handle for local countdown
  let localRemaining = 0;       // locally counted remaining seconds
  let shownAnswer = null;       // cached random answer (fetched once on close)
  let randomAnswerFetched = false;

  // --- Polling ----------------------------------------------------------- //

  async function poll() {
    try {
      const resp = await fetch("/api/s/" + slug + "/state");
      if (!resp.ok) return;
      const state = await resp.json();

      // Sync local remaining from server on every thinking poll
      if (state.status === "thinking" && state.remaining_seconds !== null) {
        localRemaining = state.remaining_seconds;
      }

      // Fetch random answer once when session closes
      if (state.status === "closed" && !randomAnswerFetched) {
        randomAnswerFetched = true;
        await fetchRandomAnswer();
      }

      renderUI(state.status);
    } catch (_) {
      /* Network error — keep polling silently */
    }
  }

  async function fetchRandomAnswer() {
    try {
      const resp = await fetch("/api/s/" + slug + "/random-answer");
      if (resp.ok) {
        const data = await resp.json();
        shownAnswer = data.answer !== null ? data.answer : (data.message || "No answers were submitted.");
      } else {
        shownAnswer = null;
      }
    } catch (_) {
      shownAnswer = null;
    }
  }

  // --- Rendering --------------------------------------------------------- //

  function renderUI(status) {
    if (status === "waiting"   && uiMode !== "waiting")   renderWaiting();
    if (status === "thinking")                             renderThinking();
    if (status === "writing"   && uiMode !== "writing" && uiMode !== "submitted") renderWriting();
    if (status === "closed"    && uiMode !== "closed")    renderClosed();
  }

  function renderWaiting() {
    stopTimer();
    uiMode = "waiting";
    statusArea.innerHTML =
      '<p class="status-msg">Waiting for the facilitator to start the timer&hellip;</p>';
  }

  function renderThinking() {
    if (uiMode !== "thinking") {
      stopTimer();
      uiMode = "thinking";
      statusArea.innerHTML =
        '<div class="timer-area">' +
          '<p class="timer-label">Time to think&hellip;</p>' +
          '<div id="timer-display" class="timer-display">' + fmtTime(localRemaining) + '</div>' +
        '</div>';
      startTimer();
    } else {
      // Already in thinking mode — just sync the display to latest server value
      const el = document.getElementById("timer-display");
      if (el) {
        el.textContent = fmtTime(localRemaining);
        el.className = "timer-display" + (localRemaining <= 10 ? " urgent" : "");
      }
    }
  }

  function renderWriting() {
    stopTimer();
    if (alreadySubmitted) {
      uiMode = "submitted";
      statusArea.innerHTML =
        '<div class="submitted-msg">' +
          '<div class="icon">&#10003;</div>' +
          '<p class="status-msg">Your answer has been submitted.<br>Waiting for the facilitator to close the session.</p>' +
        '</div>';
    } else {
      uiMode = "writing";
      statusArea.innerHTML =
        '<div class="answer-form">' +
          '<label for="answer-text">Your answer</label>' +
          '<textarea id="answer-text" maxlength="5000" rows="6"' +
            ' placeholder="Type your anonymous answer here\u2026"></textarea>' +
          '<div class="char-count"><span id="char-count">0</span> / 5000</div>' +
          '<button id="submit-btn" class="btn-primary btn-large">Submit Answer</button>' +
          '<p class="answer-hint">Your answer is anonymous. No name or identifier is stored.</p>' +
        '</div>';
      document.getElementById("answer-text").addEventListener("input", function () {
        document.getElementById("char-count").textContent = this.value.length;
      });
      document.getElementById("submit-btn").addEventListener("click", submitAnswer);
    }
  }

  function renderClosed() {
    stopTimer();
    uiMode = "closed";
    if (shownAnswer) {
      statusArea.innerHTML =
        '<div class="revealed-answer">' +
          '<p class="label">An anonymous answer:</p>' +
          '<blockquote>' + escapeHtml(shownAnswer) + '</blockquote>' +
          '<p class="revealed-hint">This may be your own answer or someone else\'s.</p>' +
        '</div>';
    } else if (randomAnswerFetched) {
      statusArea.innerHTML =
        '<div class="status-area">' +
          '<p class="no-answers">The session is closed. No answers were submitted.</p>' +
        '</div>';
    } else {
      statusArea.innerHTML = '<p class="status-msg">Session closed. Loading&hellip;</p>';
    }
  }

  // --- Timer ------------------------------------------------------------- //

  function startTimer() {
    timerInterval = setInterval(function () {
      localRemaining = Math.max(0, localRemaining - 1);
      const el = document.getElementById("timer-display");
      if (el) {
        el.textContent = fmtTime(localRemaining);
        el.className = "timer-display" + (localRemaining <= 10 ? " urgent" : "");
      }
    }, 1000);
  }

  function stopTimer() {
    if (timerInterval !== null) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  function fmtTime(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m + ":" + String(sec).padStart(2, "0");
  }

  // --- Answer submission ------------------------------------------------- //

  async function submitAnswer() {
    const textarea = document.getElementById("answer-text");
    const btn = document.getElementById("submit-btn");
    if (!textarea || !btn) return;

    const text = textarea.value.trim();
    if (!text) {
      textarea.focus();
      return;
    }

    btn.disabled = true;
    btn.textContent = "Submitting\u2026";

    try {
      const resp = await fetch("/api/s/" + slug + "/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer: text }),
      });

      if (resp.ok) {
        // Mark as submitted in sessionStorage (tab-scoped, not persistent).
        sessionStorage.setItem(SUBMITTED_KEY, "true");
        alreadySubmitted = true;
        uiMode = "submitted";
        statusArea.innerHTML =
          '<div class="submitted-msg">' +
            '<div class="icon">&#10003;</div>' +
            '<p class="status-msg">Your answer has been submitted.<br>Waiting for the facilitator to close the session.</p>' +
          '</div>';
      } else {
        const data = await resp.json().catch(function () { return {}; });
        btn.disabled = false;
        btn.textContent = "Submit Answer";
        alert(data.detail || "Failed to submit. Please try again.");
      }
    } catch (_) {
      btn.disabled = false;
      btn.textContent = "Submit Answer";
      alert("Network error. Please check your connection and try again.");
    }
  }

  // --- XSS-safe string escaping ----------------------------------------- //

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // --- Start ------------------------------------------------------------ //

  poll();
  setInterval(poll, POLL_INTERVAL);
})();
