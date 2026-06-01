# Specification: Anonymous Think–Write–Share Web App

Build a small secure web application for running anonymous “Think–Write–Share” facilitation sessions.

## Concept

Think–Write–Share is a facilitation pattern used in meetings and workshops.

The flow is:

1. **Think**: participants silently consider a question while a timer runs.
2. **Write**: once the timer reaches zero, participants write and submit their answer.
3. **Share**: once the facilitator closes submissions, each participant is shown one anonymous submitted answer. This may be their own answer or another participant’s answer.

The goal is to reduce groupthink, prevent loud voices dominating, and allow anonymous participation.

## Core Requirements

A facilitator visits the website and creates a new Think–Write–Share session.

The facilitator must be able to:

* Create a session.
* Accept or edit a suggested random slug, for example `/dog-cat-maple-syrup`.
* Enter the facilitation question.
* Choose a think timer duration.
* Confirm the session.
* See a facilitator control page showing:

  * the question
  * the public participant URL
  * the session status
  * the timer
  * number of submitted answers
* Start the timer.
* Close submissions.
* Download all submitted answers as a Markdown file.
* Never see participant identifiers, because none should be collected.

Participants visit the public slug URL.

Participants must be able to:

* See the question.
* See the timer once started.
* During the thinking phase, not see an answer box.
* When the timer reaches zero, see an answer text box.
* Submit one answer.
* After the facilitator closes the question, see one anonymous submitted answer selected at random.
* This returned answer may be their own answer or someone else’s.

## Privacy Requirements

The app must be anonymous by design.

Do not store:

* IP address
* user agent
* browser fingerprint
* cookies identifying the participant
* names
* email addresses
* login details
* participant IDs that can be linked back to a person

Participants may be prevented from accidental duplicate submission only client-side if possible, but do not create persistent identifiers to enforce this.

Submitted answers should contain only:

* answer text
* submission timestamp, if useful
* no participant identifier

## Storage

Use either SQLite or plain JSON files. Prefer SQLite unless JSON is simpler.

The storage model should include:

### Session

* slug
* question
* facilitator secret/admin token
* status:

  * draft
  * waiting
  * thinking
  * writing
  * closed
* timer duration in seconds
* timer started timestamp
* created timestamp
* closed timestamp

### Answer

* session slug or session ID
* answer text
* submitted timestamp

No participant identifier.

## URLs

Suggested URL structure:

* `/` — create session page
* `/create` — create session endpoint
* `/s/{slug}` — participant page
* `/admin/{slug}/{adminToken}` — facilitator control page
* `/admin/{slug}/{adminToken}/start` — start timer
* `/admin/{slug}/{adminToken}/close` — close submissions
* `/admin/{slug}/{adminToken}/download.md` — download markdown answers
* `/api/s/{slug}/state` — participant state polling endpoint
* `/api/s/{slug}/answer` — submit answer
* `/api/s/{slug}/random-answer` — get one anonymous answer after close

## Session Creation Flow

On the homepage:

* Generate a suggested random slug using 3–4 friendly words, e.g. `dog-cat-maple-syrup`.
* Allow the facilitator to edit the slug.
* Validate that the slug:

  * is unique
  * only contains lowercase letters, numbers, and hyphens
  * is not too long
  * does not clash with reserved routes
* Ask for:

  * question
  * timer duration
* On submit:

  * create the session
  * generate a strong random admin token
  * redirect facilitator to `/admin/{slug}/{adminToken}`

## Participant Behaviour

When a participant opens `/s/{slug}`:

* If session is waiting:

  * show the question
  * show “Waiting for facilitator to start”
* If session is thinking:

  * show the question
  * show countdown timer
  * hide answer box
* If timer has reached zero:

  * show the question
  * show answer box
* If session is closed:

  * show the question
  * show one random anonymous submitted answer

The participant page should poll the state endpoint every 1–2 seconds.

## Facilitator Behaviour

The facilitator page should show:

* question
* public participant URL
* current status
* countdown timer, if active
* answer count
* buttons:

  * Start timer
  * Close submissions
  * Download Markdown

Once the facilitator closes submissions:

* no more answers can be submitted
* answer list is sealed
* participants can retrieve one random answer

## Markdown Export

Markdown export should contain:

```markdown
# Think–Write–Share: {question}

Session: /s/{slug}
Created: {timestamp}
Closed: {timestamp}

## Answers

1. {answer text}

2. {answer text}

3. {answer text}
```

Do not include participant identifiers.

## Security Requirements

* Use HTTPS-ready deployment assumptions.
* Generate facilitator admin tokens using cryptographically secure randomness.
* Do not expose the admin token anywhere except the admin URL.
* Validate and sanitise all input.
* Escape all rendered answer text to prevent XSS.
* Use CSRF protection where appropriate.
* Add basic rate limiting to answer submission.
* Limit answer length, for example 2,000–5,000 characters.
* Limit question length.
* Reject dangerous slugs.
* Use secure HTTP headers:

  * Content-Security-Policy
  * X-Frame-Options or frame-ancestors
  * Referrer-Policy
  * X-Content-Type-Options
* Do not log request bodies containing answers.
* Configure application logging so IP addresses are not deliberately retained by the app.
* Make privacy-by-design choices explicit in comments.

## Non-Goals

Do not build:

* user accounts
* participant login
* facilitator login
* analytics tracking
* participant identification
* voting
* threaded discussion
* comments on answers

## Preferred Implementation

Use a simple modern stack suitable for easy deployment.

Good options:

* Node.js with Express/Fastify and SQLite
* Python FastAPI with SQLite
* SvelteKit with SQLite
* Next.js with SQLite

Keep the app simple, server-rendered where possible, with light JavaScript for polling and countdown updates.

## UI Style

The interface should be clean, calm, and facilitator-friendly.

Prioritise:

* large readable question
* obvious participant URL
* clear timer
* minimal distractions
* mobile-friendly participant page
* accessible contrast and font sizes

## Acceptance Criteria

The app is complete when:

1. A facilitator can create a session with a custom or suggested slug.
2. The facilitator can share the participant URL.
3. Participants can open the URL and see the question.
4. The facilitator can start the timer.
5. Participants see the countdown and cannot answer during thinking time.
6. When the timer reaches zero, participants can submit anonymous answers.
7. The facilitator can close submissions.
8. After close, participants see one random anonymous answer.
9. The facilitator can download all answers as Markdown.
10. No participant-identifying data is stored.
11. Answer rendering is safe from XSS.
12. Admin control requires the secret admin token.

