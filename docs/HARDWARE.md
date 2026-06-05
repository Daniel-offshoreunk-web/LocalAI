# Hardware sizing

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
**Inference:** Ollama CPU or GPU with `llama3.1:8b` (quantized)  
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
**Inference:** Ollama or vLLM with Llama 3.1 8B; optional 32B for office hours  
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
| `llama3.1:8b` (Q4) | 5–8 GB | Autocomplete, quick help — **default** |
| `deepseek-coder:1.3b` | ~2 GB | Ultra-light pilot on CPU |
| DeepSeek R1 Distill 32B | 20–24 GB | Deep debugging (Tier B+) |
| Llama 3.1 70B | 40+ GB | Tier C only |

Set via `DEFAULT_CHAT_MODEL` in environment.

## Ollama pull commands (pilot)

```bash
ollama pull llama3.1:8b
# optional lighter fallback:
ollama pull deepseek-coder:1.3b
```

## When to move from Tier A to B

- More than ~10 students need AI at the same time
- Latency exceeds ~3 s for first token
- RAM pressure causes OOM (`dmesg | grep -i oom`)

Switch to production compose profile and vLLM per [REPLICATE.md](REPLICATE.md) §7.
