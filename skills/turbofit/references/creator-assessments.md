# Creator Assessments Journal
# Running log of individual model assessments by Sirvir
# Format: [date] creator/model — assessment — quality verdict

## 2026-06-25 — Initial fleet assessment

### Ex0bit/Qwen3.6-27B-PRISM-PRO-DQ (Prism Eagle)
- **Creator**: Ex0bit (quality_score: 9)
- **Assessment**: Excellent hybrid Mamba2+GDN model. 121 tok/s, only 14GB VRAM. Vision works via shared mmproj. Fastest 27B dense in the fleet.
- **Verdict**: UPGRADE — replaces any non-MTP 27B as main when speed matters.
- **Tier**: S

### I-Compact/Darwin-Apex-36B (Darwin Apex)
- **Creator**: I-Compact (quality_score: 8)
- **Assessment**: Excellent MoE. 107 tok/s with NextN, 3B active params, 16GB. Vision works. Atomic fork required for NextN+TurboQuant.
- **Verdict**: KEEP — solid tier-S main candidate.
- **Tier**: S

### I-Nano/Qwen3.6-35B-A3B (Carnice)
- **Creator**: I-Nano (quality_score: 7)
- **Assessment**: Good MoE for aux role. 110 tok/s, 11GB (Q2 compact). Vision works. mmproj-BF16 from unsloth repo needed (n_embd=2048, not 5120).
- **Verdict**: KEEP — best aux candidate, smallest VRAM in tier.
- **Tier**: SF

### unsloth/Qwen3.6-27B-Instruct-GGUF (base for Darwin/Qwopus/Carwin merges)
- **Creator**: unsloth (quality_score: 9)
- **Assessment**: Clean Q4_K_M quantization. mmproj-F32 correct (n_embd=5120). Used as base for all 27B fleet merges.
- **Verdict**: REFERENCE — the gold standard for 27B GGUFs.
- **Tier**: N/A (base model)

### bartowski/Qwen3.5-35B-A3B-GGUF
- **Creator**: bartowski (quality_score: 8)
- **Assessment**: Stock Qwen MoE. 40 tok/s, 22GB. Larger VRAM than I-Nano compact. No MTP. Useful as fallback but not competitive with Carnice.
- **Verdict**: LATERAL — keep in catalog as tier-C fallback only.
- **Tier**: C
