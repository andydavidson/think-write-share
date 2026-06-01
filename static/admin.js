/**
 * admin.js — live timer countdown and answer count polling on the admin page.
 *
 * The admin token is NOT used here; we only read the public state endpoint
 * which returns status, remaining_seconds, and answer_count.
 * All privileged actions (start, close, download) are plain HTML form POSTs
 * that work without JavaScript.
 */

(function () {
  "use strict";

  const pageData = document.getElementById("page-data");
  const slug     = pageData.dataset.slug;

  const timerEl  = document.getElementById("timer-display");
  const countEl  = document.getElementById("answer-count");
  const statusEl = document.getElementById("status-label");
  const btnCopy  = document.getElementById("btn-copy-url");

  const POLL_INTERVAL = 2000; // ms — slightly slower than participant page

  let localRemaining = null;
  let timerInterval  = null;
  let initialStatus  = pageData.dataset.status;

  // Initialise countdown from server-side rendered timer_started_at
  if (initialStatus === "thinking") {
    const startedAt = parseFloat(pageData.dataset.timerStartedAt || "0");
    const totalSecs = parseFloat(pageData.dataset.timerSeconds || "0");
    if (startedAt > 0) {
      const elapsed = (Date.now() / 1000) - startedAt;
      localRemaining = Math.max(0, totalSecs - elapsed);
      startCountdown();
    }
  }

  // --- Polling ----------------------------------------------------------- //

  async function poll() {
    try {
      const resp = await fetch("/api/s/" + slug + "/state");
      if (!resp.ok) return;
      const state = await resp.json();

      // Update answer count
      if (countEl) countEl.textContent = state.answer_count;

      // Update status badge text and class
      if (statusEl && state.status !== statusEl.dataset.status) {
        statusEl.textContent = state.status;
        statusEl.className = "status-badge status-" + state.status;
        statusEl.dataset.status = state.status;
      }

      // Sync countdown with server
      if (state.status === "thinking" && state.remaining_seconds !== null) {
        localRemaining = state.remaining_seconds;
        if (timerInterval === null) startCountdown();
      } else if (state.status !== "thinking") {
        stopCountdown();
        if (timerEl) timerEl.textContent = "\u2014";
      }
    } catch (_) {
      /* silently continue */
    }
  }

  // --- Countdown --------------------------------------------------------- //

  function startCountdown() {
    if (timerInterval !== null) return;
    timerInterval = setInterval(function () {
      if (localRemaining === null) return;
      localRemaining = Math.max(0, localRemaining - 1);
      if (timerEl) {
        timerEl.textContent = fmtTime(localRemaining);
        timerEl.className = (localRemaining <= 10 ? "timer-display urgent" : "timer-display");
      }
    }, 1000);
  }

  function stopCountdown() {
    if (timerInterval !== null) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
    localRemaining = null;
  }

  function fmtTime(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m + ":" + String(sec).padStart(2, "0");
  }

  // --- Copy URL button -------------------------------------------------- //

  if (btnCopy) {
    btnCopy.addEventListener("click", async function () {
      const url = btnCopy.dataset.url;
      try {
        await navigator.clipboard.writeText(url);
        const prev = btnCopy.textContent;
        btnCopy.textContent = "Copied!";
        setTimeout(function () { btnCopy.textContent = prev; }, 2000);
      } catch (_) {
        // Fallback: select the link text
        const link = document.querySelector(".participant-url");
        if (link) {
          const range = document.createRange();
          range.selectNode(link);
          window.getSelection().removeAllRanges();
          window.getSelection().addRange(range);
        }
      }
    });
  }

  // --- Start ------------------------------------------------------------ //

  poll();
  setInterval(poll, POLL_INTERVAL);
})();
