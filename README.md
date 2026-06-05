# LocalAI / EPS Cloud Lab

**Secure, browser-based computer science lab** for schools: students get a cloud IDE and local AI without installing software on Chromebooks. Teachers approve every workspace before it starts. Built for replication — other districts can deploy the same stack on their own hardware.

## What it does

| Audience | Experience |
|----------|------------|
| **Students** | Sign up in a browser → wait for teacher approval → open **Cloud IDE** (VS Code) + AI assistant |
| **Teachers / IT** | Localhost admin panel → approve or deny registrations → review security alerts |
| **Developers** | OpenAI-compatible `/v1/chat/completions` API with per-student tokens (Continue, Tabby) |

## Architecture (one host)

```
Students (browser) ──► Gateway :8000 ──► Ollama/vLLM :11434 (inference, localhost only)
                            │
                            ├──► SQLite (registrations, tokens)
                            └──► Docker ──► code-server per student (internal network)
Admin (SSH + localhost) ──► Admin :8888
```

## Quick start (development)

**Requirements:** Linux, Python 3.12+, Docker, [Ollama](https://ollama.com/)

```bash
git clone <repo-url> eps-cloud-lab && cd eps-cloud-lab
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
chmod +x scripts/*.sh
./scripts/generate-secrets.sh >> .env
echo "ALLOW_INSECURE_DEFAULTS=0" >> .env   # or =1 for first local test only

ollama pull llama3.1:8b
ollama serve   # terminal 1

python -m src.main gateway   # terminal 2 — http://127.0.0.1:8000
python -m src.main admin     # terminal 3 — http://127.0.0.1:8888
```

Open `http://127.0.0.1:8000`, create an account, then approve it in the admin panel (add header `X-Admin-Secret: <ADMIN_SECRET from .env>` or set `ADMIN_SECRET` empty with `ALLOW_INSECURE_DEFAULTS=1` for local dev only).

Verify: `./scripts/verify-install.sh`

## Production deployment

**For IT staff and integrators**, follow the full guide:

| Document | Purpose |
|----------|---------|
| **[docs/REPLICATE.md](docs/REPLICATE.md)** | Step-by-step install (native or Docker) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, ports, data flow |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model and hardening checklist |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Backups, updates, troubleshooting |
| [docs/HARDWARE.md](docs/HARDWARE.md) | Sizing for pilot vs classroom |
| [docs/AUGUST-CHECKLIST.md](docs/AUGUST-CHECKLIST.md) | Roadmap to August go-live |

**Docker (pilot):**

```bash
cp .env.example .env && ./scripts/generate-secrets.sh >> .env
docker compose -f docker-compose.pilot.yml up -d --build
```

**Pilot → production:** same repo; switch compose file and `.env` (`DEPLOY_PROFILE=production`). See REPLICATE.md §7.

## Environment variables

See [.env.example](.env.example). Required for production:

| Variable | Description |
|----------|-------------|
| `SESSION_SECRET` | Cookie signing key (32+ random bytes) |
| `ADMIN_SECRET` | Admin panel header secret |
| `PUBLIC_BASE_URL` | Public HTTPS URL (e.g. `https://lab.school.edu`) |
| `SESSION_COOKIE_SECURE` | Set `1` when using HTTPS |

## Continue.dev / Tabby

Copy [config/continue/config.yaml.example](config/continue/config.yaml.example) into the student's code-server workspace. Replace `GATEWAY_URL` and the API key from the dashboard **Advanced** section.

## License

[MIT](LICENSE) — intended for reuse by other schools and districts.

**Before you publish or hand this to a district:** replace the placeholder copyright line in `LICENSE` with the actual legal rights holder (you, or your district only after their legal/IP office assigns copyright). Do not put an organization’s name on the license without their written approval.

## Support

Operational issues: see [docs/OPERATIONS.md](docs/OPERATIONS.md). Security concerns: [docs/SECURITY.md](docs/SECURITY.md).
