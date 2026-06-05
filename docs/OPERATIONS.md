# Operations

**[← README](../README.md)** · [Install](REPLICATE.md) · [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · [Hardware](HARDWARE.md) · [August checklist](AUGUST-CHECKLIST.md)

Day-2 runbook for staff maintaining EPS Cloud Lab in production.

## Service management

### Native (systemd)

```bash
sudo systemctl status eps-gateway eps-admin
sudo systemctl restart eps-gateway
sudo journalctl -u eps-gateway -n 100 -f
```

### Docker Compose

```bash
docker compose ps
docker compose logs -f gateway
docker compose restart gateway
```

Production profile: `docker compose -f docker-compose.production.yml …` — see [REPLICATE.md](REPLICATE.md) §7.

## Health checks

```bash
curl -sf http://127.0.0.1:8000/health
curl -sf http://127.0.0.1:8080/readyz
./scripts/verify-install.sh
```

Expected gateway response: `{"status":"healthy","gateway":"operational"}`

## Backups

**Critical file:** SQLite database (registrations, tokens, security events)

```bash
# Stop writes briefly (optional; SQLite supports hot copy on Linux)
sudo cp /var/lib/eps/orchestrator.db /var/lib/eps/backups/orchestrator-$(date +%F).db
```

Schedule daily with cron:

```cron
0 2 * * * cp /var/lib/eps/orchestrator.db /var/lib/eps/backups/orchestrator-$(date +\%F).db
```

Student workspace data lives inside Docker containers (`eps-ws-*`). For persistence across container recreation, future releases will mount volumes per user. **Pilot:** treat workspaces as ephemeral.

## Updates

```bash
cd /opt/eps-cloud-lab
sudo -u eps git pull
sudo -u eps venv/bin/pip install -r requirements.txt
sudo systemctl restart eps-gateway eps-admin
```

Or with compose:

```bash
git pull
docker compose up -d --build
```

**Always** backup `orchestrator.db` before upgrading.

## LocalAI model management

```bash
curl http://127.0.0.1:8080/v1/models
# Install models via LocalAI Web UI or gallery; then set in /etc/eps/cloud-lab.env:
# DEFAULT_CHAT_MODEL=llama-3.2-3b-instruct:q4_k_m
sudo systemctl restart eps-gateway
```

## User lifecycle

| Action | How |
|--------|-----|
| Approve student | Admin → Deploy workspace |
| Deny student | Admin → Deny |
| Stop lab | Admin → Stop (container stopped, registration stays deployed) |
| Remove container manually | `docker rm -f eps-ws-username` |
| Re-provision | Admin → Deploy again (or delete container first) |

## Common issues

### Gateway: `Refusing to start: set SESSION_SECRET`

Set `SESSION_SECRET` in env file or use `ALLOW_INSECURE_DEFAULTS=1` for dev only.

### Admin: `403 Admin access is localhost-only`

Connect via SSH and use `curl http://127.0.0.1:8888/` or browser with SSH port forward:

```bash
ssh -L 8888:127.0.0.1:8888 eps@lab-host
```

### IDE: "cloud lab is starting or offline"

1. Confirm user status is `deployed` in admin
2. `docker ps | grep eps-ws`
3. `docker start eps-ws-username` if stopped
4. Check gateway can reach container: `docker network inspect gateway_net`

### AI: 503 Inference backend unreachable

1. `docker ps | grep local-ai` (or your LocalAI service name)
2. `curl http://127.0.0.1:8080/readyz`
3. Verify `INFERENCE_URL` and `INFERENCE_API_KEY` in env match LocalAI

### AI: 400 Request blocked by safety policy

Legitimate code question triggered prompt guard. Review `security_events` in admin. Adjust lesson or refine guard rules in `src/prompt_guard.py` if false positive.

### Docker: permission denied

```bash
sudo usermod -aG docker eps
# log out and back in
```

## Monitoring (minimal pilot)

- **Gateway up:** cron hits `/health` every 5 min
- **Disk:** `df -h /var/lib/eps`
- **Memory:** `free -h` — each workspace uses up to 512 MB
- **Containers:** `docker ps --filter name=eps-ws`

## Capacity planning

Rough limits on a 32 GB RAM host:

- Gateway + LocalAI: ~8–16 GB (depends on model)
- Per student container: 512 MB
- **Example:** 16 GB for system/AI → ~30 containers theoretical; **recommend ≤15 concurrent** for headroom

See [HARDWARE.md](HARDWARE.md) for GPU tiers.

## Logs

| Component | Location |
|-----------|----------|
| Gateway (systemd) | `journalctl -u eps-gateway` |
| Admin (systemd) | `journalctl -u eps-admin` |
| LocalAI (compose) | `docker compose logs localai` |
| Docker | `docker logs eps-ws-username` |

Application logs do **not** include full AI prompts by default.

## End of semester

1. Stop all workspaces from admin
2. Export backup of `orchestrator.db`
3. Optional: `docker rm -f $(docker ps -aq --filter name=eps-ws)`
4. Archive documentation and survey results per research protocol

## Related documentation

| Document | Description |
|----------|-------------|
| [REPLICATE.md](REPLICATE.md) | Install and first-day workflow |
| [SECURITY.md](SECURITY.md) | Incident response context |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Service layout |
| [HARDWARE.md](HARDWARE.md) | Capacity planning |
| [AUGUST-CHECKLIST.md](AUGUST-CHECKLIST.md) | Go-live tracker |
