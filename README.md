# Think–Write–Share

A small, anonymous web app for running [Think–Write–Share](https://www.thinkwriteshare.net/) facilitation sessions.

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

---

## Development

### Quick start

```bash
git clone <repo-url>
cd tws
./run.sh
```

`run.sh` will:
- Create a Python virtual environment in `./venv/`
- Install dependencies from `requirements.txt`
- Start the server on **http://localhost:8000** with `--reload`

Open http://localhost:8000 in your browser to create your first session.

### Manual start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

### Running tests

```bash
source venv/bin/activate
pip install pytest httpx
pytest tests/ -v
```

### Configuration

| Environment variable | Default   | Description                      |
|----------------------|-----------|----------------------------------|
| `TWS_DB_PATH`        | `tws.db`  | Path to the SQLite database file |

---

## Production deployment

The recommended production stack is **uvicorn** (behind a **systemd** service) proxied by **nginx** with TLS from **Let's Encrypt**. The files `tws.service` and `tws.nginx.conf` in this repo are ready-to-use templates.

### 1. Server requirements

A small VPS is plenty. Tested on Ubuntu 22.04 / Debian 12.

```bash
sudo apt update
sudo apt install python3 python3-venv nginx certbot python3-certbot-nginx
```

### 2. Create a dedicated user and directories

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin tws
sudo mkdir -p /opt/tws /var/lib/tws
sudo chown tws:tws /var/lib/tws
```

### 3. Deploy the application

```bash
sudo cp -r . /opt/tws
cd /opt/tws
sudo python3 -m venv venv
sudo venv/bin/pip install -q -r requirements.txt
sudo chown -R tws:tws /opt/tws
```

For subsequent updates, pull the new code and restart the service:

```bash
cd /opt/tws && sudo git pull
sudo venv/bin/pip install -q -r requirements.txt
sudo systemctl restart tws
```

### 4. Install the systemd service

```bash
sudo cp tws.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tws
sudo systemctl status tws
```

The service runs uvicorn on `127.0.0.1:8000` and restarts automatically on failure. The SQLite database is stored at `/var/lib/tws/tws.db`, separate from the application code so it survives re-deployments.

### 5. Obtain a TLS certificate

Point your DNS A record at the server, then:

```bash
sudo certbot --nginx -d example.com
```

Certbot will edit your nginx config and set up automatic renewal. Run `sudo certbot renew --dry-run` to confirm renewal works.

### 6. Install the nginx config

Edit `tws.nginx.conf` and replace every occurrence of `example.com` with your domain:

```bash
sudo sed 's/example.com/yourdomain.com/g' tws.nginx.conf \
    > /etc/nginx/sites-available/tws
sudo ln -s /etc/nginx/sites-available/tws /etc/nginx/sites-enabled/tws
sudo nginx -t && sudo systemctl reload nginx
```

The nginx config:
- Redirects HTTP → HTTPS
- Serves `/static/` files directly (bypassing uvicorn) with a 7-day cache TTL
- Proxies everything else to uvicorn on `127.0.0.1:8000`
- Strips query strings from access logs so admin tokens are not written to disk

### 7. Verify

```bash
curl -I https://yourdomain.com
# Should return HTTP/2 200 with Content-Security-Policy header
```

### Backups

The entire application state is a single SQLite file:

```bash
# One-off backup
sudo cp /var/lib/tws/tws.db /var/lib/tws/tws.db.bak

# Simple daily cron (crontab -e as root)
0 3 * * * sqlite3 /var/lib/tws/tws.db ".backup '/var/backups/tws-$(date +\%F).db'"
```

---

## Security notes

- Admin tokens are generated with `secrets.token_urlsafe(32)` (cryptographically secure).
- The admin token appears only in the facilitator's URL — it is never stored in a cookie or sent to participants.
- All pages are served with `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy` headers.
- Rate limiting on answer submission is enforced per session (not per IP, to avoid retaining IP addresses).
- Because the admin token is in the URL, **HTTPS is essential** — the nginx config enforces this.
- The nginx `log_format` strips query strings so that tokens are not written to the access log.
