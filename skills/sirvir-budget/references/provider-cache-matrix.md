# Provider Cache Support Matrix (2026-06-30)

Cross-provider analysis of prompt caching support. Tested by sending identical prompts back-to-back and checking for `prompt_tokens_details.cached_tokens` in the API response, then cross-referencing with Hermes state.db cache hit rates.

## Cache Support by Provider × Model

| Provider | Model | API `cached_tokens` | state.db Cache | Verdict |
|----------|-------|---------------------|----------------|---------|
| ollama-cloud | deepseek-v4-pro | NO (null) | 0% | **No cache** |
| ollama-cloud | deepseek-v4-flash | NO (null) | 0% | **No cache** |
| ollama-cloud | glm-5.2 | NO (null) | 24-151% | **Cache works** (Hermes-level) |
| ollama-cloud | kimi-k2.7-code | NO (null) | ? | Unknown |
| ollama-cloud | minimax-m3 | NO (null) | ? | Unknown |
| ollama-cloud | nemotron-3-nano:30b | NO (null) | ? | Unknown |
| NVIDIA NIM | deepseek-v4-flash | NO (null) | N/A | **No cache** |
| NVIDIA NIM | minimax-m3 | YES (cached=144) | N/A | **Cache works** |
| Nous Portal | all models | Token expired | N/A | Can't test |

## Key Finding

**ollama-cloud never returns `prompt_tokens_details`** — the API field where cache info lives. But Hermes still tracks cache hits in state.db, and the data shows:

- **glm-5.2 on ollama-cloud**: 24-151% cache hit rate — the system prompt prefix is being cached and reused
- **deepseek-v4-pro on ollama-cloud**: 0% cache — zero hits across all sessions

This means ollama-cloud supports prompt caching at the infrastructure level (glm-5.2 proves it), but **deepseek models don't participate in the cache**. The same pattern holds on NIM: MiniMax M3 caches, DeepSeek doesn't.

## Root Cause

This is a **model-level limitation** — DeepSeek's architecture or ollama-cloud's hosting of it doesn't support prompt caching. Every request is a full-context GPU recomputation. This is not a Hermes config issue (`cache_ttl: 5m` is set).

## Impact on GPU-Time Billing

On flat-rate providers (ollama-cloud, Ollama Max/Pro), the billing unit is GPU-time. A model with 0% cache burns GPU-time on every request recomputing the full context. At 55K tokens/request and 130 requests, that's ~7.2M tokens of GPU recomputation with zero reuse.

If deepseek-v4-pro cached at glm-5.2's 24% rate, effective GPU burn would drop by ~20%. At gpt-5.4's 997% rate, it'd be a fraction.

## Testing Methodology

1. Send identical prompt twice to the same model
2. Check API response for `usage.prompt_tokens_details.cached_tokens`
3. If absent, check if `prompt_tokens` drops on second request (server-side cache without reporting)
4. Cross-reference with state.db `cache_read_tokens` for real-world hit rates
5. Compare system prompts across sessions — same prefix = cacheable, different prefix = cache miss

## Provider-Specific Notes

### ollama-cloud
- Base URL: `https://ollama.com/v1` (redirects from `api.ollama.com`)
- No model returns `prompt_tokens_details`
- Cache tracking is Hermes-level (system prompt prefix reuse)
- glm-5.2 caches; deepseek models don't

### NVIDIA NIM
- Base URL: `https://integrate.api.nvidia.com/v1`
- MiniMax M3 returns `cached_tokens` in `prompt_tokens_details`
- DeepSeek models return `prompt_tokens_details: null`
- Free tier, ~1000 RPM

### Nous Portal
- Base URL: `https://inference-api.nousresearch.com/v1`
- OAuth token-based auth (from `auth.json`)
- Model slugs use `provider/model` format (e.g. `stepfun/step-3.7-flash:free`)
- Not tested for cache due to token expiry
