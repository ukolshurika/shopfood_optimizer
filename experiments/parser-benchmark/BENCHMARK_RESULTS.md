# Benchmark Results

Последнее сравнение выполнено на `data/dev.jsonl` из 16 кейсов, режим `production`, по одному запросу на кейс.

| Провайдер | Schema | Item recall | Item precision | Quantity value | Quantity unit | Package semantics | Exact order | Critical errors | P95, ms | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen | 1.000 | 1.000 | 1.000 | 0.938 | 0.938 | 0.938 | 0.813 | 0.135 | 1,946 | n/a |
| DeepSeek | 0.813 | 0.813 | 0.813 | 0.813 | 0.813 | 0.813 | 0.813 | 0.081 | 9,654 | n/a |
| GigaChat Freemium | 1.000 | 1.000 | 0.979 | 0.813 | 0.813 | 0.875 | 0.375 | 0.730 | 2,024 | $0 |
| YandexGPT Lite | 0.375 | 0.375 | 0.375 | 0.156 | 0.188 | 0.188 | 0.000 | 0.676 | 4,755 | n/a |

## Interpretation

- Qwen is the current best baseline: perfect schema and item extraction, with remaining errors in quantity and package semantics.
- DeepSeek is semantically competitive on this small set, but the current `json_object` path produces schema failures and is much slower.
- GigaChat returns valid structure, but its semantic accuracy is currently insufficient.
- YandexGPT Lite frequently returns `attributes` as an object or `null` instead of the required array and is not a candidate for the current parser without a different output strategy.

## Source Artifacts

Detailed raw responses and per-case evaluations remain in the ignored local directories:

- `results/qwen_dev_16/`
- `results/deepseek_dev_16/`
- `results/gigachat_dev_16/`
- `results/yandexgpt_lite_dev_16/`

The benchmark gate is intentionally strict (`whole_order_exact_match >= 0.95`), so none of these four runs passes it yet.
