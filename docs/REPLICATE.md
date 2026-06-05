# Replication guide

**[← README](/README.md)** · [Architecture](/docs/ARCHITECTURE.md) · [Security](/docs/SECURITY.md) · [Operations](/docs/OPERATIONS.md) · [Hardware](/docs/HARDWARE.md) · [August checklist](/docs/AUGUST-CHECKLIST.md)

This document is written for **IT staff, integrators, and sysadmins** deploying EPS Cloud Lab at a school or district. Follow it in order on a fresh Linux host.

Repository: `git clone https://github.com/Daniel-offshoreunk-web/LocalAI.git`

**Time estimate:** 2–4 hours (pilot), 1–2 days (production with TLS and GPU).

---

## 1. Overview

EPS Cloud Lab provides:

1. A **student web portal** (signup, dashboard, cloud IDE link, AI chat)
2. A **gateway** that proxies AI requests to [LocalAI](https://localai.io/) with per-user API tokens
3. An **admin approval queue** — no Docker workspace starts until a teacher approves
4. **Sandboxed code-server containers** per approved student

**Default ports:**

| Port | Service | Exposure |
|------|---------|----------|
| 443 | TLS reverse proxy (you provide) | Public / school network |
| 8000 | Student gateway | Behind proxy or school VLAN |
| 8888 | Admin panel | **127.0.0.1 only** |
| 8080 | LocalAI | **internal / 127.0.0.1 only** |

---

## 2. Prerequisites

### Software

- **OS:** Fedora 40+, RHEL 9+, or Ubuntu 22.04+ (Fedora is the reference platform)
- **Python:** 3.12+
- **Docker:** Engine 24+ with permission for the service user to run `docker`
- **LocalAI:** Docker image `localai/localai` ([quickstart](https://localai.io/basics/getting_started/))
- **Optional:** NVIDIA driver + CUDA for GPU inference

### Hardware (minimum pilot)

See [HARDWARE.md](/docs/HARDWARE.md). Minimum: 8 CPU threads, 32 GB RAM, 500 GB disk. GPU strongly recommended for acceptable AI latency.

### Network

- Static IP or DNS name for the lab host
- TLS certificate (Let's Encrypt or district CA)
- School IP ranges documented for firewall rules

---

## 3. Install — native (recommended for pilot)

### 3.1 Create service user and directories

```bash
sudo useradd -r -m -d /opt/eps-cloud-lab -s /bin/bash eps || true
sudo mkdir -p /var/lib/eps /etc/eps
sudo chown eps:eps /var/lib/eps
```

### 3.2 Clone and install Python dependencies

```bash
sudo -u eps git clone https://github.com/Daniel-offshoreunk-web/LocalAI.git /opt/eps-cloud-lab
cd /opt/eps-cloud-lab
sudo -u eps python3 -m venv venv
sudo -u eps venv/bin/pip install -r requirements.txt
```

### 3.3 Configure environment

```bash
sudo cp .env.example /etc/eps/cloud-lab.env
sudo chmod 600 /etc/eps/cloud-lab.env
sudo ./scripts/generate-secrets.sh | sudo tee -a /etc/eps/cloud-lab.env
```

Edit `/etc/eps/cloud-lab.env`:

```bash
sudo nano /etc/eps/cloud-lab.env
```

Set at minimum:

```env
DEPLOY_PROFILE=pilot
ORCHESTRATOR_DB=/var/lib/eps/orchestrator.db
PUBLIC_BASE_URL=https://lab.yourdistrict.edu
SESSION_COOKIE_SECURE=1
ALLOW_INSECURE_DEFAULTS=0
DEFAULT_CHAT_MODEL=llama-3.2-3b-instruct:q4_k_m
INFERENCE_URL=http://127.0.0.1:8080
INFERENCE_API_KEY=<match LocalAI LOCALAI_API_KEY>
```

Add the `eps` user to the `docker` group:

```bash
sudo usermod -aG docker eps
```

### 3.4 Install and start LocalAI

```bash
docker run -d --name local-ai --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -e LOCALAI_API_KEY=<same-as-INFERENCE_API_KEY> \
  -v localai-models:/models \
  localai/localai:latest-aio-cpu
```

Verify: `curl http://127.0.0.1:8080/readyz`

### 3.5 Install systemd services

```bash
sudo cp deploy/systemd/eps-gateway.service /etc/systemd/system/
sudo cp deploy/systemd/eps-admin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eps-gateway eps-admin
```

Check logs: `journalctl -u eps-gateway -f`

### 3.6 TLS reverse proxy (Caddy example)

Install Caddy on the host and use:

```caddy
lab.yourdistrict.edu {
    reverse_proxy 127.0.0.1:8000
}
```

Students use `https://lab.yourdistrict.edu`. Set `PUBLIC_BASE_URL` to match.

### 3.7 Firewall

Edit school CIDRs in `deploy/nftables/eps-gateway.nft.example`, then:

```bash
sudo nft -f deploy/nftables/eps-gateway.nft.example
```

Ensure **8080** (LocalAI) and **8888** (admin) are not reachable from the internet.

### 3.8 Verify

```bash
cd /opt/eps-cloud-lab
GATEWAY_URL=https://lab.yourdistrict.edu ./scripts/verify-install.sh
```

---

## 4. Install — Docker Compose (recommended)

One command brings up LocalAI, gateway, admin, and builds the Continue-enabled workspace image:

```bash
git clone https://github.com/Daniel-offshoreunk-web/LocalAI.git && cd LocalAI
chmod +x scripts/*.sh
./scripts/up.sh
```

`up.sh` creates `.env` on first run, frees conflicting ports, and runs `docker compose up -d --build`. For production, edit `.env` first (`PUBLIC_BASE_URL`, `SESSION_COOKIE_SECURE=1`, `ALLOW_INSECURE_DEFAULTS=0`) — see [.env.example](/.env.example).

Equivalent manual start (after `.env` exists):

```bash
docker compose up -d --build
./scripts/verify-install.sh
```

`docker-compose.pilot.yml` is an alias that includes [docker-compose.yml](/docker-compose.yml).

**Admin access:** SSH to the host, then:

```bash
# Browser (recommended): http://127.0.0.1:8888/login — paste ADMIN_SECRET from .env
# Scripts may still use: curl -H "X-Admin-Secret: $(grep ADMIN_SECRET .env | cut -d= -f2)" http://127.0.0.1:8888/
```

Or port-forward: `ssh -L 8888:127.0.0.1:8888 admin@lab-host`

---

## 5. First-day workflow

### Teacher / admin

1. Open `http://127.0.0.1:8888/login` on the server and enter the admin key (16+ characters). One failed attempt permanently blocks that IP until another signed-in admin unblocks it.
2. Review **Pending approval** queue.
3. Click **Deploy workspace** for each approved student.
4. Monitor **Security alerts** for blocked prompts or failed logins.

### Student

1. Browse to `https://lab.yourdistrict.edu`
2. **Create account** → status shows *pending*
3. After teacher approval → **Open Cloud IDE**
4. **Open Cloud IDE** — Continue is pre-installed; the student's API key is injected at deploy time.

---

## 6. Continue.dev setup

**Docker / Compose (default):** The `eps-workspace:latest` image includes Continue and writes `~/.continue/config.yaml` when a teacher approves a student. No manual setup for most users.

**Custom image or native deploy:** Copy [config/continue/config.yaml.example](/config/continue/config.yaml.example) to `~/.continue/config.yaml` and set:

- `GATEWAY_URL` → your public lab URL (no trailing slash)
- `sk-eps-PASTE_STUDENT_TOKEN_HERE` → token from the dashboard **Advanced** section

---

## 7. Pilot → production switch

Same codebase. Change configuration only:

| Setting | Pilot | Production |
|---------|-------|------------|
| Compose file | [docker-compose.yml](/docker-compose.yml) | [docker-compose.production.yml](/docker-compose.production.yml) |
| `DEPLOY_PROFILE` | `pilot` | `production` |
| Inference | LocalAI CPU (`latest-aio-cpu` in compose) | LocalAI GPU or external OpenAI-compatible node |
| `INFERENCE_URL` | `http://localai:8080` (compose) | GPU LocalAI service or vLLM URL |
| Database | SQLite at `/var/lib/eps/` | SQLite OK for single host; Postgres planned for HA |
| Rate limits | In-memory | Redis (compose production includes Redis stub) |
| TLS | Caddy/nginx | District load balancer |

**Migration steps:**

1. Snapshot `/var/lib/eps/orchestrator.db`
2. Provision GPU inference host; deploy vLLM with OpenAI-compatible API
3. Update `.env` with new inference URL
4. Swap compose file; `docker compose up -d`
5. Re-run `verify-install.sh`

No student URL changes required.

---

## 8. Environment reference

Full list in [.env.example](/.env.example).

| Variable | Required | Notes |
|----------|----------|-------|
| `SESSION_SECRET` | Yes (prod) | `openssl rand -hex 32` |
| `ADMIN_SECRET` | Yes (prod) | Protects admin panel |
| `PUBLIC_BASE_URL` | Yes (HTTPS) | Used for cookies and Continue config |
| `SESSION_COOKIE_SECURE` | Yes (HTTPS) | Must be `1` behind TLS |
| `INFERENCE_URL` | Yes | LocalAI base URL; never expose port 8080 publicly |
| `INFERENCE_API_KEY` | Recommended | Server-side LocalAI key; see [SECURITY.md](/docs/SECURITY.md) |
| `ORCHESTRATOR_DB` | No | Default `./orchestrator.db` |
| `DISABLE_API_REGISTER` | No | Default `1` — force web signup |
| `ALLOW_INSECURE_DEFAULTS` | No | **Never `1` in production** |

---

## 9. Replication checklist for another district

- [ ] Clone repo (`git clone https://github.com/Daniel-offshoreunk-web/LocalAI.git`); copy `LICENSE.example` → `LICENSE` and **set the copyright holder** with district legal if needed
- [ ] Provision hardware per [HARDWARE.md](/docs/HARDWARE.md)
- [ ] Install Docker; run `./scripts/up.sh` or follow §4
- [ ] Generate secrets; configure `/etc/eps/cloud-lab.env`
- [ ] Deploy gateway + admin (systemd or compose)
- [ ] Configure TLS reverse proxy
- [ ] Apply firewall rules
- [ ] Run `verify-install.sh`
- [ ] Teacher training: admin approval workflow
- [ ] Student onboarding: signup URL only (no API keys required for basic use)
- [ ] Document local support contact in your runbook

---

## 10. Troubleshooting

| Symptom | Check |
|---------|-------|
| Gateway won't start | `SESSION_SECRET` set? `ALLOW_INSECURE_DEFAULTS=0`? |
| Admin 403 | Must connect from localhost; use SSH tunnel |
| Admin login blocked | Wrong key blocks IP permanently; unblock from dashboard or `admin_ip_blocks` table |
| IDE 503 | Student approved? `docker ps` shows `eps-ws-<user>`? |
| AI 503 | LocalAI healthy? (`docker compose ps`; first boot can take several minutes) |
| AI 401 | Student deployed? Token in DB? |

Full runbook: [OPERATIONS.md](/docs/OPERATIONS.md)

---

## 11. Privacy and data

- **Stored:** usernames, password hashes, API tokens, registration status, security event metadata
- **Not stored by default:** full AI prompt/response content
- **Surveys:** run outside this application (Google Forms, etc.)

Align with district policy (e.g. MNCDPA). See [SECURITY.md](/docs/SECURITY.md).

---

## 12. Getting help

1. [README.md](/README.md) — overview and quick start
2. [ARCHITECTURE.md](/docs/ARCHITECTURE.md) — components and request flows
3. [OPERATIONS.md](/docs/OPERATIONS.md) — day-2 operations
4. [SECURITY.md](/docs/SECURITY.md) — hardening and pen-test prep
5. [AUGUST-CHECKLIST.md](/docs/AUGUST-CHECKLIST.md) — release roadmap

Report security issues through your district's responsible disclosure channel.
