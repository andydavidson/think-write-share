# Think–Write–Share

A small, anonymous web app for running [Think–Write–Share](https://www.thinkwriteshare.com/) facilitation sessions.

Think–Write–Share is a structured participation technique used in meetings and workshops. It gives everyone quiet time to think, then invites written responses before the group shares — reducing groupthink and preventing louder voices from dominating.

**Privacy by design.** No accounts, no logins, no tracking. Participant answers are stored with only their text and a timestamp — no names, IP addresses, cookies, or any other identifying information.

## How it works

1. A **facilitator** creates a session, sets a question and a think timer, then shares the participant URL with the group.
2. **Participants** open the URL and see the question. When the facilitator starts the timer, a countdown is shown — no answer box yet.
3. When the timer hits zero, the answer box appears and participants submit their anonymous response.
4. The facilitator closes submissions. Each participant is shown one randomly selected anonymous answer (which may be their own).
5. The facilitator can download all answers as a Markdown file.

## Requirements

- Python 3.11 or later

No Node.js or npm required.

## Getting started

```bash
git clone <repo-url>
cd tws
./run.sh
```

`run.sh` will:
- Create a Python virtual environment in `./venv/`
- Install dependencies from `requirements.txt`
- Start the server on **http://localhost:8000**

Open http://localhost:8000 in your browser to create your first session.

### Manual start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

### Configuration

| Environment variable | Default   | Description                          |
|----------------------|-----------|--------------------------------------|
| `TWS_DB_PATH`        | `tws.db`  | Path to the SQLite database file     |

## Security notes

- Admin tokens are generated with `secrets.token_urlsafe(32)` (cryptographically secure).
- The admin token appears only in the facilitator's URL — it is never stored in a cookie or sent to participants.
- All pages are served with `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy` headers.
- Rate limiting on answer submission is enforced per session (not per IP, to avoid retaining IP addresses).
