# LocalAI — EPS Cloud Lab

A **secure, self-hosted computer science lab** for schools. Students use a normal web browser to access a full cloud IDE (VS Code via code-server) and local AI assistance—without installing anything on a Chromebook. Teachers must **explicitly approve** every workspace before any server compute is allocated.

The project is **open source** so other districts can replicate the same stack on their own hardware, meet student-data privacy expectations, and avoid per-seat fees for proprietary AI tools.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Who it is for](#who-it-is-for)
- [What students experience](#what-students-experience)
- [What teachers and IT do](#what-teachers-and-it-do)
- [Architecture](#architecture)
- [Components](#components)
- [Security model](#security-model)
- [Privacy and data](#privacy-and-data)
- [Technology stack](#technology-stack)
- [Repository layout](#repository-layout)
- [Ports and networking](#ports-and-networking)
- [Deployment profiles](#deployment-profiles)
- [Quick start (development)](#quick-start-development)
- [Production deployment](#production-deployment)
- [Configuration](#configuration)
- [HTTP API and routes](#http-api-and-routes)
- [Continue.dev / Tabby integration](#continuedev--tabby-integration)
- [Hardware sizing](#hardware-sizing)
- [Replicating in another district](#replicating-in-another-district)
- [Current limitations and roadmap](#current-limitations-and-roadmap)
- [Documentation index](#documentation-index)
- [License](#license)

---

## Why this exists

Commercial AI tools (e.g. GitHub Copilot) cost money per student, send data to vendors, and are hard for teachers to supervise. Many students also lack home computers powerful enough to run local models.

This project provides:

- **Equity** — Professional-grade tools on school servers; students need only a browser.
- **Privacy** — Inference runs on district hardware; prompts are not logged to a third-party SaaS by default.
- **Control** — Teachers approve accounts; admins see security alerts; compute is rate-limited and sandboxed.
- **Replication** — Documented, MIT-licensed software any district can deploy without vendor lock-in.

It supports a **research pilot** (pre/post surveys on CS confidence and engagement) and a path to **full classroom deployment** by changing configuration, not rewriting the application.

---

## Who it is for

| Role | Need |
|------|------|
| **Students** | Sign up, wait for approval, open cloud IDE, use AI help—no API or terminal knowledge required |
| **Teachers / sponsors** | Approve or deny lab access, review security flags, stop workspaces |
| **District IT** | Install on Linux, TLS, firewall, backups—follow [docs/REPLICATE.md](docs/REPLICATE.md) |
| **Integrators / developers** | OpenAI-compatible gateway for Continue, Tabby, or custom clients via per-student `sk-eps-…` tokens |

---

## What students experience

1. Open the school lab URL (e.g. `https://lab.yourdistrict.edu`).
2. **Create account** with username and password (8+ characters).
3. See dashboard status **pending** until a teacher approves.
4. After approval:
   - **Open Cloud IDE** — full VS Code in the browser (`/lab/`).
   - **AI assistant** — chat on the dashboard (`/app/ai/chat`).
   - **Advanced** — personal API key for Continue.dev or Tabby inside the IDE.

Students never receive the server’s upstream inference key. They authenticate to **this gateway** only.

---

## What teachers and IT do

1. SSH to the lab host (admin panel is **localhost-only**).
2. Open the admin dashboard on port **8888** with the `X-Admin-Secret` header (when configured).
3. Review the **pending** queue → **Deploy workspace** or **Deny**.
4. Monitor **security alerts** (blocked prompts, failed logins).
5. **Stop** a deployed workspace if needed.

No container is created at signup. This blocks anonymous “free compute” abuse (mass signups spawning Docker workloads).

---

## Architecture

```
                         School network / VLAN
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  Chromebook ──► TLS reverse proxy (Caddy/nginx) :443              │
│                        │                                           │
│                        ▼                                           │
│                 Gateway (FastAPI) :8000                            │
│                   • Student portal (HTML + sessions)               │
│                   • CSRF-protected forms                           │
│                   • /v1/chat/completions (student tokens)          │
│                   • /lab/* → code-server proxy (HTTP + WebSocket)  │
│                        │                                           │
│          ┌─────────────┼─────────────┐                             │
│          ▼             ▼             ▼                             │
│      SQLite      LocalAI :8080    Docker Engine                    │
│   (orchestrator   (OpenAI API,    │                               │
│    .db)           internal only)  ▼                               │
│                          ┌──────────────────┐                      │
│                          │ eps-ws-<user>    │                      │
│                          │ code-server      │                      │
│                          │ on gateway_net   │                      │
│                          └──────────────────┘                      │
│                                                                    │
│  Teacher (SSH) ──► Admin panel :8888 (127.0.0.1 only)              │
└────────────────────────────────────────────────────────────────────┘
```

**Two-layer AI auth:** Students use session cookies (browser) or `sk-eps-…` tokens (IDE extensions). The gateway validates them, applies rate limits and prompt guard, then forwards to LocalAI using a **server-side** `INFERENCE_API_KEY` that students never see.

---

## Components

### Gateway (`src/gateway.py`, port 8000)

Public FastAPI application:

- Mounts student routes (`src/student.py`)
- Session middleware (signed cookies, 8-hour TTL)
- Security headers and 1 MB body size limit
- Health check: `GET /health`
- Optional machine registration: `POST /v1/register` (disabled by default)
- Inference proxy: `POST /v1/chat/completions`

Refuses to start in production without a real `SESSION_SECRET` (unless `ALLOW_INSECURE_DEFAULTS=1` for local dev only).

### Student portal (`src/student.py`)

| Route | Purpose |
|-------|---------|
| `GET /` | Login / signup page |
| `POST /signup`, `POST /login`, `POST /logout` | Account lifecycle (CSRF-protected) |
| `GET /dashboard` | Status, IDE link, AI chat, API key |
| `POST /app/ai/chat` | Browser AI chat (session + CSRF) |
| `GET/POST /lab/`, `/lab/{path}` | Proxy to student’s code-server |
| WebSocket `/lab/{path}` | IDE terminal / extension traffic |

### Admin panel (`src/admin.py`, port 8888)

- **Localhost-only** middleware on every request
- Lists pending / approved / recent registrations
- **Deploy workspace** → triggers Docker run
- **Deny**, **Stop workspace**
- **Security alerts** from `security_events` table
- Requires `ADMIN_SECRET` in production (via `X-Admin-Secret` header)

### Orchestrator (`src/orchestrator.py`)

Spawns student workspaces with **argv-only** `docker` calls (no shell):

| Constraint | Value |
|------------|--------|
| CPU | `--cpus 0.25` |
| Memory | `--memory 512m` |
| PIDs | `--pids-limit 128` |
| Network | `gateway_net` (internal bridge) |
| Capabilities | `--cap-drop ALL`, `no-new-privileges` |
| Image | `eps-workspace:latest` — code-server + Continue.dev (configurable) |
| Continue | Pre-installed; config injected at deploy with student's `sk-eps-…` token |
| code-server | `--auth none` — gateway session is the auth boundary |

Container name: `eps-ws-<username>` (username validated before use).

### Inference (`src/inference.py`)

Single guarded path to the LLM:

1. Resolve `sk-eps-…` in SQLite (or use session row for browser chat)
2. Verify account status (`deployed` or `approved`)
3. Rate limit per IP and per user
4. Run `prompt_guard` (regex + AST), then guardian LLM (≥1B model) when enabled
5. Strip student credentials from upstream headers
6. Forward to `INFERENCE_URL/v1/chat/completions` with `INFERENCE_API_KEY`

Supports streaming responses for OpenAI-compatible clients.

### Prompt guard (`src/prompt_guard.py`)

Blocks common abuse patterns before they reach the model:

- Regex: `os.system`, `subprocess`, `socket`, `eval`, `curl`, etc.
- AST scan on fenced ` ```python ` blocks in chat payloads
- Violations logged to `security_events` and returned as HTTP 400

### Database (`src/db.py`, SQLite)

**`registrations`**

| Column | Purpose |
|--------|---------|
| `username` | Unique, validated lowercase identifier |
| `status` | `pending` → `approved` → `deployed` (or `denied` / `failed`) |
| `password_hash` | PBKDF2-SHA256 (310k rounds) |
| `api_token` | Per-student `sk-eps-…` for IDE extensions |
| `container_name` | Docker name after deploy |
| `display_name` | Optional friendly name |

**`security_events`** — `prompt_blocked`, `login_failed`, etc. (metadata only, not full prompts)

### Supporting modules

| Module | Role |
|--------|------|
| `src/security.py` | Username/container validation, bearer token parsing, proxy path checks |
| `src/auth_store.py` | Password hashing, API token generation |
| `src/sessions.py` | Login/logout, CSRF tokens, session fixation mitigation |
| `src/rate_limit.py` | In-memory token-bucket limiter |
| `src/workspace_proxy.py` | HTTP/WebSocket proxy to code-server containers |
| `src/http_middleware.py` | CSP, `X-Frame-Options`, body size cap |

---

## Security model

| Threat | Mitigation |
|--------|------------|
| Anonymous compute farming | Admin approval before any `docker run` |
| Stolen API keys | Per-user DB tokens; rate limits; revocable by re-provision |
| Malicious prompts | Prompt guard + security event logging |
| Container escape / host abuse | cgroups, cap-drop, isolated Docker network |
| Admin panel on the internet | Binds `127.0.0.1`; SSH tunnel + secret header |
| Session hijacking / CSRF | Signed cookies, CSRF on all form posts and AI chat |
| Cross-user IDE access | Session username bound to one container proxy |
| Direct inference access | LocalAI port not public; gateway holds upstream key |
| Path traversal to other workspaces | `validate_proxy_path()` rejects `..` and null bytes |

**Production checklist:** [docs/SECURITY.md](docs/SECURITY.md)

**Do not** publish code-server container ports on the host LAN. Students reach the IDE only through `/lab` after login.

---

## Privacy and data

| Data | Stored? | Notes |
|------|---------|-------|
| Username, password hash | Yes | SQLite |
| Per-student API token | Yes | Shown on dashboard (Advanced) |
| Registration / deploy status | Yes | |
| Security event metadata | Yes | No full prompt text by default |
| Full AI prompts and responses | **No** | Aligns with MNCDPA-style local processing story |
| Research surveys | Outside app | Pre/post forms, anonymized |

Districts should complete a privacy review before go-live. See [docs/SECURITY.md](docs/SECURITY.md) § Data retention.

---

## Technology stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12+ |
| Web framework | FastAPI, Starlette, Jinja2 |
| HTTP client | httpx (async) |
| WebSockets | websockets (IDE proxy) |
| Database | SQLite (aiosqlite) |
| Sessions | itsdangerous (via Starlette SessionMiddleware) |
| Student IDE | code-server (Docker) |
| Inference | [LocalAI](https://localai.io/) — OpenAI-compatible `/v1` API |
| IDE AI extensions | Continue.dev or Tabby (optional) |
| Container runtime | Docker Engine |
| Reverse proxy (production) | Caddy / nginx (documented, not bundled) |

**Python dependencies:** [requirements.txt](requirements.txt)

---

## Repository layout

```
LocalAI/
├── src/
│   ├── main.py              # CLI: gateway | admin | both
│   ├── gateway.py           # Public app (:8000)
│   ├── admin.py             # Admin app (:8888)
│   ├── student.py           # Portal + /lab proxy routes
│   ├── inference.py         # LLM proxy + guards
│   ├── orchestrator.py      # Docker workspace lifecycle
│   ├── db.py                # SQLite schema and queries
│   ├── security.py          # Validation and auth helpers
│   ├── prompt_guard.py      # Prompt/code scanner
│   ├── rate_limit.py        # Token-bucket limiter
│   ├── workspace_proxy.py   # code-server HTTP/WS proxy
│   ├── auth_store.py        # Passwords and tokens
│   ├── sessions.py          # Cookie sessions + CSRF
│   ├── http_middleware.py   # Security headers
│   ├── config.py            # Environment configuration
│   └── templates/           # student_*.html, admin_dashboard.html
├── docs/
│   ├── REPLICATE.md         # Full install guide for IT
│   ├── ARCHITECTURE.md      # Design reference
│   ├── SECURITY.md          # Hardening and threat model
│   ├── OPERATIONS.md        # Backups, troubleshooting
│   ├── HARDWARE.md          # Sizing tiers
│   └── AUGUST-CHECKLIST.md  # Go-live tracker
├── deploy/
│   ├── systemd/             # eps-gateway.service, eps-admin.service
│   └── nftables/            # Example firewall rules
├── config/continue/         # Continue.dev config template
├── scripts/
│   ├── generate-secrets.sh
│   └── verify-install.sh
├── docker-compose.yml        # Full stack — one `docker compose up`
├── docker-compose.pilot.yml  # Alias → docker-compose.yml
├── docker-compose.production.yml
├── Dockerfile
├── Dockerfile.workspace      # code-server + Continue.dev
├── .env.example
└── LICENSE.hidden           # MIT — set copyright holder before distribution
```

---

## Ports and networking

| Port | Service | Exposure |
|------|---------|----------|
| **443** | TLS reverse proxy | Public or school VLAN (you provide) |
| **8000** | Student gateway | Behind proxy; not raw internet in production |
| **8888** | Admin panel | **127.0.0.1 only** |
| **8080** | LocalAI inference | Internal / Docker network only — never WAN |
| **8080** (inside container) | code-server per student | `gateway_net` only — not host-published |

Docker network **`gateway_net`** connects the gateway to student workspace containers. LocalAI runs on a separate internal network in the pilot compose file.

---

## Deployment profiles

Set `DEPLOY_PROFILE=pilot` or `production` in `.env`.

| | **Pilot** | **Production** |
|---|-----------|----------------|
| **Use case** | Research study, 5–10 students | Classroom / district scale |
| **Compose file** | `docker-compose.pilot.yml` | `docker-compose.production.yml` |
| **Inference** | LocalAI CPU image in compose | LocalAI GPU (+ Redis stub) |
| **Database** | SQLite at `/var/lib/eps/` | SQLite today; Postgres planned for HA |
| **Rate limits** | In-memory | Redis when multi-instance |
| **Switch effort** | Change `.env` + compose file | Same codebase, no student URL change |

Details: [docs/REPLICATE.md](docs/REPLICATE.md) §7

---

## Quick start (one command)

**Requirements:** Linux, Docker with Compose v2

```bash
git clone <repo-url> LocalAI && cd LocalAI
chmod +x scripts/*.sh
./scripts/up.sh
```

That single command:

1. Creates `.env` with dev secrets (first run only)
2. Builds **LocalAI**, the **gateway**, the **admin** panel, and the **workspace image** (code-server + Continue.dev)
3. Starts everything with `docker compose up -d --build`

Then:

1. Open `http://127.0.0.1:8000` → create a student account  
2. Open `http://127.0.0.1:8888` → approve the account (`X-Admin-Secret` header from `.env`)  
3. Return to the dashboard → **Open Cloud IDE** (Continue is already wired to the gateway with the student's API key)

Verify: `./scripts/verify-install.sh`

**Equivalent manual command** (after `.env` exists):

```bash
docker compose up -d --build
```

### Native development (without Compose)

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
docker build -f Dockerfile.workspace -t eps-workspace:latest .
docker run -d -p 8080:8080 --name local-ai localai/localai:latest-aio-cpu
python -m src.main gateway   # terminal 2
python -m src.main admin     # terminal 3
```

Set `WORKSPACE_IMAGE=eps-workspace:latest` and `WORKSPACE_GATEWAY_URL=http://host.docker.internal:8000` in `.env`.

---

## Production deployment

**IT and integrators should follow [docs/REPLICATE.md](docs/REPLICATE.md)** — native systemd install or Docker Compose, TLS, firewall, secrets, and verification.

Minimum production settings:

```env
SESSION_SECRET=<openssl rand -hex 32>
ADMIN_SECRET=<openssl rand -hex 32>
ALLOW_INSECURE_DEFAULTS=0
PUBLIC_BASE_URL=https://lab.yourdistrict.edu
SESSION_COOKIE_SECURE=1
INFERENCE_URL=http://127.0.0.1:8080
INFERENCE_API_KEY=<localai-server-key-if-configured>
DISABLE_API_REGISTER=1
```

---

## Configuration

Full reference: [.env.example](.env.example)

| Variable | Description |
|----------|-------------|
| `DEPLOY_PROFILE` | `pilot` or `production` |
| `SESSION_SECRET` | Cookie signing key (**required** in prod) |
| `ADMIN_SECRET` | Admin `X-Admin-Secret` header (**required** in prod) |
| `PUBLIC_BASE_URL` | Public HTTPS URL for cookies and Continue config |
| `SESSION_COOKIE_SECURE` | `1` when using HTTPS |
| `ORCHESTRATOR_DB` | Path to SQLite file |
| `INFERENCE_URL` | LocalAI or any OpenAI-compatible `/v1` base URL |
| `INFERENCE_API_KEY` | Server-side upstream key (students never see this) |
| `DEFAULT_CHAT_MODEL` | Model id sent to LocalAI (e.g. `llama-3.2-3b-instruct:q4_k_m`) |
| `OLLAMA_URL` | Legacy alias for `INFERENCE_URL` |
| `WORKSPACE_IMAGE` | Workspace Docker image (`eps-workspace:latest`) |
| `WORKSPACE_GATEWAY_URL` | Gateway URL reachable from workspace containers |
| `DOCKER_NETWORK` | Bridge for workspaces (default `gateway_net`) |
| `RATE_LIMIT_CHAT_PER_MIN` | AI requests per user per minute |
| `DISABLE_API_REGISTER` | `1` = web signup only (default) |
| `ALLOW_INSECURE_DEFAULTS` | `1` = dev only; never on a public server |

Generate secrets: `./scripts/generate-secrets.sh`

---

## HTTP API and routes

### Public gateway (:8000)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check |
| GET | `/` | None | Student login page |
| POST | `/signup`, `/login`, `/logout` | CSRF | Account session |
| GET | `/dashboard` | Session | Student dashboard |
| POST | `/app/ai/chat` | Session + CSRF | Browser AI chat |
| GET/POST | `/lab/`, `/lab/{path}` | Session | code-server proxy |
| WS | `/lab/{path}` | Session cookie | IDE WebSocket proxy |
| POST | `/v1/chat/completions` | Bearer `sk-eps-…` | OpenAI-compatible inference |
| POST | `/v1/register` | None | Disabled by default |

### Admin (:8888, localhost only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Localhost + secret | Provisioning dashboard |
| POST | `/approve/{id}` | Localhost + secret | Deploy workspace |
| POST | `/deny/{id}` | Localhost + secret | Deny registration |
| POST | `/stop/{id}` | Localhost + secret | Stop container |

---

## Continue.dev / Tabby integration

**Docker / Compose:** Continue is pre-installed in `eps-workspace:latest`. When a teacher approves a student, the orchestrator starts a workspace container with that student's `sk-eps-…` token and gateway URL already written to `~/.continue/config.yaml`.

**Manual / custom image:** Copy [config/continue/config.yaml.example](config/continue/config.yaml.example) to `~/.continue/config.yaml`, set `GATEWAY_URL` and the student's API key from the dashboard.

Extensions talk to **`https://lab.yourdistrict.edu/v1`**, not to LocalAI directly. The gateway enforces per-student auth and prompt guard.

---

## Hardware sizing

| Tier | Students | Rough spec |
|------|----------|------------|
| **A — Pilot** | 5–10 | 8 threads, 32 GB RAM; optional GPU |
| **B — Classroom** | 25–35 | 64+ GB RAM, RTX 4090 / L40S 24–48 GB |
| **C — District** | 100+ | HA gateway, GPU inference nodes, workspace host |

Full tables: [docs/HARDWARE.md](docs/HARDWARE.md)

---

## Replicating in another district

1. Clone this repository.
2. Set the **copyright holder** in `LICENSE.hidden` with your legal/IP office.
3. Follow **[docs/REPLICATE.md](docs/REPLICATE.md)** on a staging host.
4. Run `./scripts/verify-install.sh`.
5. Train teachers on the admin approval workflow.
6. Point students at a single HTTPS URL.

No vendor account required. Software stack is MIT-licensed (once copyright is assigned correctly).

---

## Current limitations and roadmap

| Item | Status |
|------|--------|
| Student browser portal + IDE proxy | Done |
| Admin approval queue + security alerts | Done |
| LocalAI inference proxy + prompt guard | Done |
| Continue config template | Done |
| Custom code-server image with Continue pre-installed | Done (`Dockerfile.workspace`) |
| Persistent per-student workspace volumes | Planned |
| Guardian heuristics + small classifier model | Planned |
| Redis-backed rate limits (multi-instance) | Planned |
| School SSO (Google / Microsoft) | Planned |
| Postgres for HA | Planned |

Tracker: [docs/AUGUST-CHECKLIST.md](docs/AUGUST-CHECKLIST.md)

---

## Documentation index

| Document | Contents |
|----------|----------|
| [docs/REPLICATE.md](docs/REPLICATE.md) | Step-by-step install for professionals |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components and request flows |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model and production checklist |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Backups, updates, troubleshooting |
| [docs/HARDWARE.md](docs/HARDWARE.md) | Hardware tiers and models |
| [docs/AUGUST-CHECKLIST.md](docs/AUGUST-CHECKLIST.md) | Go-live checklist |

---

## License

MIT — see [LICENSE.hidden](LICENSE.hidden).

**Before distribution:** replace the placeholder copyright line with the actual legal rights holder (you, or your district only after their IP/legal office approves). Do not attribute copyright to an organization without written authorization.

---

## Support

- **Operations:** [docs/OPERATIONS.md](docs/OPERATIONS.md)
- **Security:** [docs/SECURITY.md](docs/SECURITY.md)
- **Install:** [docs/REPLICATE.md](docs/REPLICATE.md)
