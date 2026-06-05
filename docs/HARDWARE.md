# Hardware sizing

**[← README](../README.md)** · [Install](REPLICATE.md) · [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · [Operations](OPERATIONS.md) · [August checklist](AUGUST-CHECKLIST.md)

Reference hardware for EPS Cloud Lab deployments. Software is identical across tiers; capacity and model choice differ.

## Tier A — Pilot (research study, 5–10 students)

| Component | Specification |
|-----------|---------------|
| CPU | 8 threads (Intel i7 or equivalent) |
| RAM | 32 GB |
| Storage | 500 GB NVMe |
| GPU | Optional: NVIDIA RTX 4060/4090 16–24 GB |
| Network | School VLAN; 1 Gbps |
| OS | Fedora 40+ (reference) |

**Concurrent students:** 5–10  
**Inference:** LocalAI CPU image in [docker-compose.yml](../docker-compose.yml); model via `DEFAULT_CHAT_MODEL`  
**Cost band:** Existing lab hardware ($0) to ~$2,000 with GPU

## Tier B — Single classroom (25–35 students)

| Component | Specification |
|-----------|---------------|
| CPU | 16+ threads |
| RAM | 64–128 GB |
| GPU | 1× RTX 4090 24 GB or L40S 48 GB |
| Storage | 1 TB NVMe |
| Network | Dedicated VLAN; TLS at edge |

**Concurrent students:** 25–35 (not all coding simultaneously)  
**Inference:** LocalAI GPU or vLLM with Llama-class 8B; optional 32B for office hours  
**Cost band:** $3,000–$8,000

## Tier C — District / multi-class

| Component | Specification |
|-----------|---------------|
| Gateway | 2× VMs (8 vCPU, 32 GB each) behind load balancer |
| Inference | 2× GPU servers (dual 4090 or L40S) running vLLM |
| Workspace host | 128+ GB RAM Docker host |
| Data | Postgres + Redis |
| Network | Firewall, school CIDR only |

**Concurrent students:** 100+  
**Cost band:** $15,000+ (or cloud GPU if district policy allows)

## Model recommendations

| Model | VRAM | Use case |
|-------|------|----------|
| `llama-3.2-3b-instruct:q4_k_m` | ~4 GB | Chat + autocomplete — **default** in `.env.example` |
| `llama-3.2-1b-instruct:q4_k_m` | ~2 GB | Guardian safety filter (`GUARDIAN_MODEL`) |
| DeepSeek R1 Distill 32B | 20–24 GB | Deep debugging (Tier B+) |
| Llama 3.1 70B | 40+ GB | Tier C only |

Set via `DEFAULT_CHAT_MODEL` and `GUARDIAN_MODEL` in [.env.example](../.env.example). Install models through the LocalAI Web UI or gallery after `./scripts/up.sh`.

## LocalAI (pilot compose)

Pilot stack includes `localai/localai:latest-aio-cpu`. First boot preloads bundled models — allow several minutes. Verify with:

```bash
docker compose ps
curl -sf http://127.0.0.1:8080/readyz   # when LocalAI port is published for debug only
./scripts/verify-install.sh
```

## When to move from Tier A to B

- More than ~10 students need AI at the same time
- Latency exceeds ~3 s for first token
- RAM pressure causes OOM (`dmesg | grep -i oom`)

Switch to [docker-compose.production.yml](../docker-compose.production.yml) per [REPLICATE.md](REPLICATE.md) §7.

## Related documentation

| Document | Description |
|----------|-------------|
| [REPLICATE.md](REPLICATE.md) | Install and environment variables |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Deployment profiles |
| [OPERATIONS.md](OPERATIONS.md) | Capacity troubleshooting |
