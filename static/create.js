/**
 * create.js — session creation page behaviour.
 * Handles slug regeneration, async availability check, and char counter.
 * No inline scripts; data is read from #page-data data attributes.
 */

(function () {
  "use strict";

  const slugInput   = document.getElementById("slug");
  const slugHint    = document.getElementById("slug-hint");
  const btnNewSlug  = document.getElementById("btn-new-slug");
  const qTextarea   = document.getElementById("question");
  const qCount      = document.getElementById("q-count");

  // --- Character counter for question ----------------------------------- //
  if (qTextarea && qCount) {
    qTextarea.addEventListener("input", function () {
      qCount.textContent = this.value.length;
    });
  }

  // --- Slug availability check (debounced) ------------------------------ //
  let checkTimer = null;

  function checkSlug(slug) {
    clearTimeout(checkTimer);
    if (!slug || slug.length < 3) {
      slugHint.textContent = "";
      slugHint.className = "field-hint slug-hint";
      return;
    }
    checkTimer = setTimeout(async function () {
      try {
        const resp = await fetch("/api/check-slug/" + encodeURIComponent(slug));
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.available) {
          slugHint.textContent = "Available";
          slugHint.className = "field-hint slug-hint ok";
        } else {
          slugHint.textContent = data.error || "Not available";
          slugHint.className = "field-hint slug-hint err";
        }
      } catch (_) {
        slugHint.textContent = "";
        slugHint.className = "field-hint slug-hint";
      }
    }, 400);
  }

  if (slugInput) {
    slugInput.addEventListener("input", function () {
      checkSlug(this.value.trim().toLowerCase());
    });
    // Check initial value (suggested slug) on load
    checkSlug(slugInput.value.trim().toLowerCase());
  }

  // --- Regenerate slug button ------------------------------------------- //
  if (btnNewSlug) {
    btnNewSlug.addEventListener("click", async function () {
      btnNewSlug.disabled = true;
      try {
        const resp = await fetch("/api/random-slug");
        if (!resp.ok) return;
        const data = await resp.json();
        slugInput.value = data.slug;
        checkSlug(data.slug);
      } catch (_) {
        /* silently ignore network errors */
      } finally {
        btnNewSlug.disabled = false;
        slugInput.focus();
      }
    });
  }
})();
