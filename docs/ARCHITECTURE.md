# Architecture

**[← README](../README.md)** · [Install](REPLICATE.md) · [Security](SECURITY.md) · [Operations](OPERATIONS.md) · [Hardware](HARDWARE.md) · [August checklist](AUGUST-CHECKLIST.md)

## System context

EPS Cloud Lab runs on **district-owned hardware**. Students use a browser; all compute stays on the school network. The design prevents anonymous compute abuse by requiring **teacher approval** before any workspace container is created.

## Component diagram

```
                    ┌─────────────────────────────────────────┐
                    │           School network / VLAN          │
                    │                                          │
  Chromebook ──────►│  TLS proxy (Caddy/nginx) :443           │
                    │           │                              │
                    │           ▼                              │
                    │  Gateway (FastAPI) :8000                 │
                    │    • Student portal (HTML)               │
                    │    • Session auth + CSRF                 │
                    │    • /v1/chat/completions proxy          │
                    │    • /lab → code-server proxy            │
                    │           │                              │
                    │     ┌─────┴─────┬──────────────┐        │
                    │     ▼           ▼              ▼        │
                    │  SQLite    LocalAI        Docker       │
                    │  (state)   :8080          engine       │
                    │  (local)   (internal)         │        │
                    │                               ▼        │
                    │                    ┌─────────────────┐ │
                    │                    │ eps-ws-alice    │ │
                    │                    │ code-server     │ │
                    │                    │ (gateway_net)   │ │
                    │                    └─────────────────┘ │
                    │                                          │
  Teacher (SSH) ───►│  Admin panel :8888 (127.0.0.1 only)     │
                    └─────────────────────────────────────────┘
```

## Services

### Gateway (`src/gateway.py`, port 8000)

Public-facing FastAPI application:

- Serves student HTML templates
- Validates session cookies and CSRF tokens
- Proxies OpenAI-compatible requests to LocalAI after token + rate-limit + prompt guard checks
- Proxies HTTP/WebSocket for `/lab/*` to the student's code-server container

### Admin (`src/admin.py`, port 8888)

Localhost-only FastAPI application:

- Lists pending registrations
- Triggers `docker run` on approval
- Shows security events (blocked prompts, failed logins)
- Stop workspace action

### Orchestrator (`src/orchestrator.py`)

Invokes Docker via **argv-only** subprocess (no shell). Creates containers with:

- `--cpus 0.25`, `--memory 512m`, `--pids-limit 128`
- `--cap-drop ALL`, `--security-opt no-new-privileges`
- Network `gateway_net` (no direct LAN access)
- code-server with `--auth none` (gateway session is the auth boundary)

### Inference (`src/inference.py`)

Single path to the LLM backend:

1. Resolve API token in SQLite
2. Rate limit (IP + user)
3. Prompt guard (regex + AST on fenced code)
4. Proxy to `INFERENCE_URL` (LocalAI `/v1/chat/completions`) with server-side API key

### Database (`src/db.py`)

SQLite file (`orchestrator.db`) with tables:

- `registrations` — users, status, password hash, API token, container name
- `security_events` — audit metadata for admin dashboard

## Request flows

### Student signup

```
POST /signup → validate username/password → INSERT pending → session cookie → /dashboard
```

No Docker action occurs.

### Teacher approval

```
Admin POST /approve/{id} → docker run eps-ws-{user} → status=deployed
```

### Open cloud IDE

```
GET /lab/ → session check → status=deployed → proxy to http://eps-ws-{user}:8080/
```

### AI chat (browser)

```
POST /app/ai/chat → session + CSRF → prompt guard → LocalAI
```

### AI chat (Continue/Tabby)

```
POST /v1/chat/completions → Bearer sk-eps-… → DB lookup → guard → LocalAI
```

## Deployment profiles

| Profile | Compose file | Inference | Database |
|---------|--------------|-----------|----------|
| `pilot` | [docker-compose.yml](../docker-compose.yml) | LocalAI CPU (compose service) | SQLite |
| `production` | [docker-compose.production.yml](../docker-compose.production.yml) | LocalAI GPU (+ Redis stub) | SQLite (Postgres planned) |

## File layout

```
LocalAI/
├── src/
│   ├── gateway.py          # Public app
│   ├── admin.py            # Admin app
│   ├── student.py          # Portal routes
│   ├── inference.py        # LLM proxy + guards
│   ├── orchestrator.py     # Docker workspace lifecycle
│   ├── db.py               # SQLite
│   ├── security.py         # Input validation
│   ├── prompt_guard.py     # Prompt/code scanner
│   ├── rate_limit.py       # Token bucket
│   └── templates/          # Jinja2 HTML
├── deploy/systemd/         # Native service units
├── deploy/nftables/        # Firewall example
├── config/continue/        # Continue.dev template
├── docs/                   # This documentation
├── docker-compose.yml      # Full stack (pilot default)
├── docker-compose.pilot.yml
├── docker-compose.production.yml
├── Dockerfile
├── Dockerfile.workspace    # code-server + Continue.dev
└── LICENSE.example
```

## Extension points

- **Custom workspace image:** set `WORKSPACE_IMAGE` (default `eps-workspace:latest` with Continue)
- **Other backends:** point `INFERENCE_URL` to any OpenAI-compatible `/v1` peer (vLLM, remote LocalAI node)
- **SSO:** add OIDC middleware in front of gateway (production roadmap)
- **Guardian AI:** `guardian_llm.py` + `prompt_guard.py` + `security_events` — see [SECURITY.md](SECURITY.md)

## Related documentation

| Document | Description |
|----------|-------------|
| [REPLICATE.md](REPLICATE.md) | Install and first-day workflow |
| [SECURITY.md](SECURITY.md) | Threat model and production checklist |
| [OPERATIONS.md](OPERATIONS.md) | Backups, updates, troubleshooting |
| [HARDWARE.md](HARDWARE.md) | Sizing tiers |
| [AUGUST-CHECKLIST.md](AUGUST-CHECKLIST.md) | Go-live tracker |
