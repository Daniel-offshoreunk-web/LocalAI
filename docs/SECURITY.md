# Security

## Threat model

| Threat | Mitigation |
|--------|------------|
| Anonymous compute abuse | Admin approval before `docker run`; rate limits on signup |
| Stolen API keys | Per-user tokens in DB; revocable by re-deploy; rate limits |
| Prompt injection / malware gen | Regex + AST (`prompt_guard.py`), then optional ≥1B guardian model; events logged |
| Container escape | cap-drop, no-new-privileges, resource limits, isolated network |
| Admin panel exposure | Binds `127.0.0.1`; requires `X-Admin-Secret` in production |
| Session hijacking | HttpOnly cookies, CSRF on forms, `SESSION_SECRET` required |
| Path traversal to other workspaces | Session-bound username; proxy path validation |
| Direct LocalAI access | Must not expose port 8080; gateway holds `INFERENCE_API_KEY` |

## Production checklist

Before exposing to students on the school network:

- [ ] `SESSION_SECRET` and `ADMIN_SECRET` set (use `scripts/generate-secrets.sh`)
- [ ] `ALLOW_INSECURE_DEFAULTS=0`
- [ ] `SESSION_COOKIE_SECURE=1` with HTTPS
- [ ] Admin panel reachable **only** via localhost or SSH tunnel
- [ ] LocalAI reachable only on internal/docker network (not WAN)
- [ ] `INFERENCE_API_KEY` set when LocalAI is on a shared network segment
- [ ] Firewall applied (`deploy/nftables/eps-gateway.nft.example`)
- [ ] Docker socket accessible only to the `eps` service user
- [ ] `DISABLE_API_REGISTER=1` (web signup only)
- [ ] TLS certificate valid; `PUBLIC_BASE_URL` matches

## Authentication layers

1. **Students:** Session cookie after password login (PBKDF2-SHA256, 310k rounds)
2. **API clients (Continue):** Bearer `sk-eps-…` token looked up in SQLite
3. **Admin:** Localhost IP check + optional `X-Admin-Secret` header

## code-server `--auth none`

code-server runs without its own password because:

- Containers are on `gateway_net`, not published to the host LAN
- Only the gateway proxy can reach port 8080 inside the container
- Students must hold a valid session to access `/lab`

**Do not** publish workspace container ports directly.

## Prompt guard

`src/prompt_guard.py` scans chat payloads for:

- Shell execution patterns (`os.system`, `subprocess`, etc.)
- Network patterns (`socket`, `curl`, `wget`)
- AST analysis on fenced Python blocks

Violations are **blocked** and logged to `security_events`.

## Rate limits (in-memory)

| Endpoint | Limit |
|----------|-------|
| Login | 10 / 15 min per IP |
| Signup | 5 / hour per IP |
| AI chat | 20 / min per user, 30 / min per IP |

**Production note:** in-memory limits reset on process restart and do not sync across replicas. Use Redis when running multiple gateway instances (production compose includes a Redis stub).

## Data retention

| Data | Stored? | Location |
|------|---------|----------|
| Username, password hash | Yes | SQLite |
| API token | Yes | SQLite |
| Registration status | Yes | SQLite |
| Security event metadata | Yes | SQLite |
| Full AI prompts/responses | **No** (by default) | — |

Districts should document this in their privacy impact assessment.

## Penetration testing

Expected findings to address before internet exposure:

1. **Docker socket on gateway host** — compromise of gateway = root on host. Mitigate with dedicated VM, AppArmor, minimal user permissions.
2. **In-memory rate limits** — bypass with distributed IPs. Mitigate with edge rate limiting.
3. **No geo-fence** — add nftables school CIDR rules.
4. **Guardian is rule-based only** — add heuristic + small classifier model (August roadmap).

Report findings through district responsible disclosure.

## Incident response

1. Stop affected workspace: Admin → **Stop** on deployed user
2. Deny pending registrations if attack in progress
3. Review `security_events` in admin dashboard
4. Rotate `ADMIN_SECRET` and affected student API tokens (re-approve user to regenerate)
5. Restore `orchestrator.db` from backup if database tampered

See [OPERATIONS.md](OPERATIONS.md) for backup procedures.
