# August go-live checklist

**[← README](../README.md)** · [Install](REPLICATE.md) · [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · [Operations](OPERATIONS.md) · [Hardware](HARDWARE.md)

Target: **production-ready, replicable deployment** for district use by August.

Status key: ✅ Done · 🟡 Partial · ⬜ Not started

---

## Documentation (required for replication)

| Item | Status | Notes |
|------|--------|-------|
| [README.md](../README.md) | ✅ | Entry point + quick start |
| [REPLICATE.md](REPLICATE.md) | ✅ | Professional install guide |
| [ARCHITECTURE.md](ARCHITECTURE.md) | ✅ | System design |
| [SECURITY.md](SECURITY.md) | ✅ | Hardening checklist |
| [OPERATIONS.md](OPERATIONS.md) | ✅ | Day-2 runbook |
| [HARDWARE.md](HARDWARE.md) | ✅ | Sizing tiers |
| [.env.example](../.env.example) | ✅ | All variables documented |
| [LICENSE.example](../LICENSE.example) | 🟡 | Copy → `LICENSE`; assign copyright with legal before district release |
| [docker-compose.yml](../docker-compose.yml) | ✅ | One-command pilot stack |
| [docker-compose.production.yml](../docker-compose.production.yml) | 🟡 | GPU LocalAI + Redis stub |
| systemd units | ✅ | Native deploy path — [REPLICATE.md](REPLICATE.md) §3 |
| [Continue config](../config/continue/config.yaml.example) | ✅ | Manual fallback; image pre-wires Continue |
| Firewall example | ✅ | [deploy/nftables/](../deploy/nftables/) |
| [verify-install.sh](../scripts/verify-install.sh) | ✅ | Post-deploy smoke test |

---

## Application (code)

| Item | Status | August target |
|------|--------|---------------|
| Student portal (signup, IDE, AI chat) | ✅ | Polish UX copy |
| Admin approval queue | ✅ | — |
| Session + CSRF auth | ✅ | — |
| DB-backed API tokens | ✅ | Token rotation UI |
| Prompt guard + guardian LLM + security events | 🟡 | Tune guardian model; L2 heuristics |
| code-server sandbox | ✅ | Persistent volumes per user |
| `/v1/chat/completions` proxy → LocalAI | ✅ | vLLM adapter tested on GPU tier |
| `DEPLOY_PROFILE` in code | ✅ | `pilot` / `production` in [config](../src/config.py) |
| Redis rate limits (production) | ⬜ | Required for multi-instance |
| Custom code-server image + Continue | ✅ | [Dockerfile.workspace](../Dockerfile.workspace) |
| SSO (Google/Microsoft) | ⬜ | Production optional |

---

## Infrastructure (deploy on district hardware)

| Week | Task | Owner |
|------|------|-------|
| **Now** | Provision Tier A or B hardware — [HARDWARE.md](HARDWARE.md) | District IT |
| **Now** | Run [REPLICATE.md](REPLICATE.md) on staging host | IT / integrator |
| **+1 wk** | TLS + DNS (`lab.district.edu`) | IT |
| **+1 wk** | Firewall + school CIDR — [SECURITY.md](SECURITY.md) | IT |
| **+2 wk** | Teacher training (admin panel) | Staff sponsor |
| **+2 wk** | LocalAI model load test; 10 concurrent users | Dev |
| **+3 wk** | Pen-test on VLAN; fix findings — [SECURITY.md](SECURITY.md) | Security |
| **+4 wk** | Pilot with 5–10 students (optional dry run) | Research |
| **August** | Go-live for fall semester | All |

---

## Definition of "done" for August

A professional can replicate the system if they can:

1. `git clone https://github.com/Daniel-offshoreunk-web/LocalAI.git` and read [README.md](../README.md)
2. Follow [REPLICATE.md](REPLICATE.md) without asking the original developer
3. Run [verify-install.sh](../scripts/verify-install.sh) and get all green checks
4. Approve a test student and open the cloud IDE in a browser
5. Confirm Continue points at the gateway (pre-installed in `eps-workspace:latest`)

---

## Remaining engineering priority (before August)

Ordered by impact:

1. **Persistent workspace volumes** — mount per-user data across container recreation
2. **vLLM / GPU LocalAI smoke test** on Tier B hardware; document `INFERENCE_URL` in [REPLICATE.md](REPLICATE.md) §7
3. **Guardian L2 heuristics** (rate + paste size flags in admin)
4. **Pen-test fixes** from district security review — [SECURITY.md](SECURITY.md)
5. **Redis-backed rate limits** for production HA

---

## Risk register

| Risk | Mitigation |
|------|------------|
| GPU funding delayed | Run Tier A on CPU; limit concurrent users; smaller `DEFAULT_CHAT_MODEL` |
| Docker socket compromise | Dedicated VM; restrict `eps` user; no public admin — [SECURITY.md](SECURITY.md) |
| Teacher bottleneck on approvals | Bulk approve UI; pre-register class roster (future) |
| LocalAI slow first boot | Document wait time in [OPERATIONS.md](OPERATIONS.md); healthcheck in compose |

---

## Sign-off template

| Role | Name | Date | Sign-off |
|------|------|------|----------|
| IT lead | | | Install per [REPLICATE.md](REPLICATE.md) |
| Security | | | [SECURITY.md](SECURITY.md) checklist |
| CS teacher | | | Admin workflow tested |
| Privacy officer | | | Data retention reviewed — [SECURITY.md](SECURITY.md) § Privacy |
