# August go-live checklist

Target: **production-ready, replicable deployment** for district use by August.

Status key: ✅ Done · 🟡 Partial · ⬜ Not started

---

## Documentation (required for replication)

| Item | Status | Notes |
|------|--------|-------|
| README.md | ✅ | Entry point + quick start |
| docs/REPLICATE.md | ✅ | Professional install guide |
| docs/ARCHITECTURE.md | ✅ | System design |
| docs/SECURITY.md | ✅ | Hardening checklist |
| docs/OPERATIONS.md | ✅ | Day-2 runbook |
| docs/HARDWARE.md | ✅ | Sizing tiers |
| .env.example | ✅ | All variables documented |
| LICENSE (MIT) | 🟡 | Placeholder copyright — assign with legal before district release |
| docker-compose.pilot.yml | ✅ | One-command pilot |
| docker-compose.production.yml | 🟡 | Stub + Redis; vLLM commented |
| systemd units | ✅ | Native deploy path |
| Continue config template | ✅ | config/continue/ |
| Firewall example | ✅ | deploy/nftables/ |
| verify-install.sh | ✅ | Post-deploy smoke test |

---

## Application (code)

| Item | Status | August target |
|------|--------|---------------|
| Student portal (signup, IDE, AI chat) | ✅ | Polish UX copy |
| Admin approval queue | ✅ | — |
| Session + CSRF auth | ✅ | — |
| DB-backed API tokens | ✅ | Token rotation UI |
| Prompt guard + security events | ✅ | Guardian heuristics |
| code-server sandbox | ✅ | Persistent volumes per user |
| `/v1/chat/completions` proxy | ✅ | vLLM adapter tested |
| DEPLOY_PROFILE in code | ⬜ | Env-only today; wire in config.py |
| Redis rate limits (production) | ⬜ | Required for multi-instance |
| Custom code-server image + Continue | ⬜ | **High priority for accessibility** |
| Guardian classifier (small model) | ⬜ | Pilot stretch goal |
| SSO (Google/Microsoft) | ⬜ | Production optional |

---

## Infrastructure (deploy on district hardware)

| Week | Task | Owner |
|------|------|-------|
| **Now** | Provision Tier A or B hardware | District IT |
| **Now** | Run REPLICATE.md on staging host | IT / integrator |
| **+1 wk** | TLS + DNS (`lab.district.edu`) | IT |
| **+1 wk** | Firewall + school CIDR | IT |
| **+2 wk** | Teacher training (admin panel) | Staff sponsor |
| **+2 wk** | Pull Ollama models; load test 10 users | Dev |
| **+3 wk** | Custom code-server image with Continue | Dev |
| **+3 wk** | Pen-test on VLAN; fix findings | Security |
| **+4 wk** | Pilot with 5–10 students (optional dry run) | Research |
| **August** | Go-live for fall semester | All |

---

## Definition of "done" for August

A professional can replicate the system if they can:

1. Clone the repo and read **README.md**
2. Follow **docs/REPLICATE.md** without asking the original developer
3. Run `./scripts/verify-install.sh` and get all green checks
4. Approve a test student and open the cloud IDE in a browser
5. Point Continue.dev at the gateway using **config/continue/config.yaml.example**

---

## Remaining engineering priority (before August)

Ordered by impact:

1. **Custom code-server Docker image** with Continue pre-installed and gateway URL templated
2. **Persistent workspace volumes** (`-v eps-ws-{user}:/home/coder`)
3. **vLLM smoke test** on GPU hardware; document `INFERENCE_URL` in REPLICATE.md
4. **Guardian L2 heuristics** (rate + paste size flags in admin)
5. **Pen-test fixes** from district security review

---

## Risk register

| Risk | Mitigation |
|------|------------|
| GPU funding delayed | Run Tier A on CPU with `deepseek-coder:1.3b`; limit concurrent users |
| Docker socket compromise | Dedicated VM; restrict `eps` user; no public admin |
| Teacher bottleneck on approvals | Bulk approve UI; pre-register class roster (future) |
| Continue setup too hard for students | Pre-bake image (priority #1 above) |

---

## Sign-off template

| Role | Name | Date | Sign-off |
|------|------|------|----------|
| IT lead | | | Install per REPLICATE.md |
| Security | | | SECURITY.md checklist |
| CS teacher | | | Admin workflow tested |
| Privacy officer | | | Data retention reviewed |
