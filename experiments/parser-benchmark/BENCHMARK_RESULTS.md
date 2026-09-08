# Benchmark Results

Последнее сравнение выполнено на `data/dev.jsonl` из 16 кейсов, режим `production`, по одному запросу на кейс.

| Провайдер | Schema | Item recall | Item precision | Quantity value | Quantity unit | Package semantics | Exact order | Critical errors | P95, ms | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen | 1.000 | 1.000 | 1.000 | 0.938 | 0.938 | 0.938 | 0.813 | 0.135 | 1,946 | n/a |
| DeepSeek | 0.813 | 0.813 | 0.813 | 0.813 | 0.813 | 0.813 | 0.813 | 0.081 | 9,654 | n/a |
| GigaChat Freemium | 1.000 | 1.000 | 0.979 | 0.813 | 0.813 | 0.875 | 0.375 | 0.730 | 2,024 | $0 |
| YandexGPT Lite | 0.375 | 0.375 | 0.375 | 0.156 | 0.188 | 0.188 | 0.000 | 0.676 | 4,755 | n/a |

## v2: prompt examples and shape normalization

The v2 run uses the same 16 cases and models. It adds few-shot examples for package count, repeated products, brands, and attribute representation. The adapter normalizes only `attributes: null` and object-shaped attributes; the original response remains in each run's `raw_attempts.jsonl`.

| Провайдер | Schema | Item recall | Item precision | Quantity value | Quantity unit | Package semantics | Exact order | Critical errors | P95, ms | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen | 1.000 | 1.000 | 1.000 | 0.938 | 0.938 | 0.938 | 0.813 | 0.135 | 1,643 | n/a |
| DeepSeek | 0.938 | 0.938 | 0.938 | 0.875 | 0.875 | 0.875 | 0.875 | 0.108 | 8,580 | n/a |
| GigaChat Freemium | 1.000 | 1.000 | 1.000 | 0.792 | 0.854 | 0.740 | 0.188 | 0.892 | 3,440 | $0 |
| YandexGPT Lite | 0.938 | 0.938 | 0.938 | 0.583 | 0.698 | 0.615 | 0.250 | 0.838 | 4,290 | n/a |

The v2 run confirms that shape normalization helps format compliance, but it does not solve quantity and package semantics. Qwen remains the strongest baseline; DeepSeek is the most promising candidate for a stronger model and strict JSON Schema path. The one-run comparison is directional because model outputs are stochastic.

## Interpretation

- Qwen is the current best baseline: perfect schema and item extraction, with remaining errors in quantity and package semantics.
- DeepSeek is semantically competitive on this small set, but the current `json_object` path produces schema failures and is much slower.
- GigaChat returns valid structure, but its semantic accuracy is currently insufficient.
- YandexGPT Lite frequently returns `attributes` as an object or `null` instead of the required array and is not a candidate for the current parser without a different output strategy.

## Strong-model round

This round used the same 16 cases and `parser_v1` prompt. DeepSeek Pro used the Responses API with strict JSON Schema. YandexGPT Pro and Qwen Strong used the Yandex OpenAI-compatible endpoint.

| Модель | Schema | Item recall | Item precision | Quantity value | Quantity unit | Package semantics | Exact order | Critical errors | P95, ms | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| DeepSeek Pro | 0.938 | 0.938 | 0.938 | 0.875 | 0.875 | 0.875 | 0.875 | 0.108 | 15,355 | completed |
| YandexGPT Pro | 0.375 | 0.375 | 0.218 | 0.313 | 0.292 | 0.198 | 0.000 | 0.946 | 14,923 | completed, weak JSON/semantics |
| Qwen 235B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.432 | 148 | not evaluated: HTTP 400 `Failed to get model` |

The current winner remains the regular Qwen baseline at `0.813` exact match with much lower latency. DeepSeek Pro is a viable quality candidate, but not an improvement on this sample and is substantially slower. The YandexGPT Pro run indicates a transport/output compatibility problem rather than a useful quality signal.

## Fixed Yandex/Qwen live round

After correcting Yandex model URIs and the Qwen reasoning parameter, both endpoints produced usable responses.

| Модель | Schema | Item recall | Item precision | Quantity value | Quantity unit | Package semantics | Exact order | Critical errors | P95, ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| YandexGPT Pro (`gpt://.../yandexgpt/latest`) | 1.000 | 1.000 | 1.000 | 0.906 | 0.906 | 0.938 | 0.813 | 0.162 | 3,667 |
| Qwen 235B (`qwen3-235b-a22b-fp8/latest`, `reasoning_effort=low`) | 1.000 | 1.000 | 1.000 | 0.917 | 0.938 | 0.917 | 0.750 | 0.216 | 7,362 |

YandexGPT Pro now matches the baseline Qwen on exact order match and is faster in this run. Qwen 235B is valid and operational, but did not outperform the smaller Qwen baseline on this dataset.

## Source Artifacts

Detailed raw responses and per-case evaluations remain in the ignored local directories:

- `results/qwen_dev_16/`
- `results/deepseek_dev_16/`
- `results/gigachat_dev_16/`
- `results/yandexgpt_lite_dev_16/`

The benchmark gate is intentionally strict (`whole_order_exact_match >= 0.95`), so none of these four runs passes it yet.
