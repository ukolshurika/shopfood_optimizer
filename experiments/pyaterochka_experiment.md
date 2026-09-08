# Pyaterochka Parser Benchmark Experiment

## Objective

Benchmark LLM APIs for converting Russian free-form grocery requests intended for a Пятерочка optimization Telegram bot into the canonical `ShoppingList` structure.

The parser performs only extraction and normalization. It must not select SKUs, infer availability in Пятерочка, choose private-label alternatives, calculate packages from physical quantity, estimate prices, optimize the basket, or decide whether Пятерочка is the best shop.

Primary decision rule:

1. Exclude configurations that fail the quality gate.
2. Among passing configurations, prefer the lowest `cost_per_1k_exact_matches`.
3. If cost is close, prefer lower critical error rate, lower p95 latency, lower retry rate, and lower operational complexity.

No provider or model is preselected as winner.

## Pyaterochka-Specific User Input Risks

Пятерочка users are likely to mix store vocabulary, promo wording, brands, private labels, package language, and casual Russian. The benchmark must capture these risks explicitly:

| Risk | Example input | Expected parser behavior |
|---|---|---|
| Store name as context, not product | `в пятерочке возьми молоко 2 л и хлеб` | Do not create item `пятерочка`; extract `молоко`, `хлеб`. |
| Promo or discount wording | `по акции сыр, бананы 1 кг` | Do not create promo attributes unless explicitly useful to the downstream app; extract requested products. |
| Private-label brand ambiguity | `творог красная цена 5%` | Treat `Красная цена` as explicit brand only if project policy confirms it as a brand string; preserve `fat_percent=5`. |
| Loyalty-card noise | `с картой пятерочки яйца С0 и молоко` | Ignore loyalty-card phrase; extract `яйца`, `молоко`. |
| Shelf/category wording | `что-нибудь к чаю: печенье, молоко` | Extract explicit products only; do not infer tea, sugar, or candy. |
| Package vs physical quantity | `2 молока Простоквашино` | `package_count=2`, not `quantity_value=2`, `quantity_unit=l`. |
| Package size | `3 пачки творога по 180 г` | `package_count=3`, `package_size_value=180`, `package_size_unit=g`. |
| Units common in grocery chat | `кола 0.9 л`, `сметана 300 г`, `курица 1.5 кг` | Normalize units to `l`, `g`, `kg`; keep values as numbers. |
| Variant words | `молоко безлактозное`, `яблоки голден`, `яйца С0` | Preserve explicit attributes. |
| Brand vs product confusion | `агуша питьевой йогурт 2 штуки` | `brand=Агуша`, product normalized to `йогурт`, quantity as `2 pcs` if policy treats `штуки` as physical count. |
| Typos and colloquial forms | `помидорки черри 500гр`, `картохи 2 кг` | Normalize product and units deterministically in evaluation. |
| Repeated close items | `молоко 2 л и молоко безлактозное 1 л` | Keep separate items because attributes differ. |

## Canonical Schema Scope

Use the same schema from the parser benchmark spec:

```text
ShoppingList.items[]
  product: str
  brand: str | null
  quantity_value: float | null
  quantity_unit: g | kg | ml | l | pcs | null
  package_count: int | null
  package_size_value: float | null
  package_size_unit: g | kg | ml | l | pcs | null
  attributes: [{ key: str, value: str }]
```

Пятерочка-specific concepts such as store, loyalty card, promo, delivery slot, price, SKU, category page, or replacement preference are outside this parser schema unless later added by application code.

## Dataset Plan

Create three JSONL datasets:

| Dataset | Size | Purpose |
|---|---:|---|
| `dev.jsonl` | ~50 cases | Prompt and policy iteration. |
| `test.jsonl` | ~250 frozen cases | Final quality and cost comparison. |
| `stability.jsonl` | 30-50 hard cases | Repeatability across 3-5 runs. |

Recommended Пятерочка-focused test distribution:

| Category | TEST cases |
|---|---:|
| Simple grocery lists | 30 |
| Conversational Telegram wording | 30 |
| Пятерочка context/noise | 25 |
| kg/g/l/ml/pcs quantities | 30 |
| Packages, bottles, packs | 25 |
| Package size `по N г/мл` | 20 |
| Product properties: fat, variety, type, category | 25 |
| Brands and private-label candidates | 20 |
| Typos, cases, colloquial words | 20 |
| Ambiguous quantity policy cases | 15 |
| Repeated or similar products | 10 |

Gold data must be frozen before the final TEST run. Ambiguous policies must be decided once and applied identically to every provider.

## Russian Example Cases and Gold Expectations

These examples are executable dataset seeds. Full JSONL gold should include every schema field, using `null` and empty `attributes` when absent.

| ID | Category | Input | Gold expectation |
|---|---|---|---|
| `pt_context_001` | Пятерочка noise | `в пятерочке возьми молоко 2 л, хлеб и бананы 1 кг` | Items: `молоко` with `2 l`; `хлеб` no quantity; `банан` with `1 kg`. No item for Пятерочка. |
| `pt_loyalty_001` | Loyalty noise | `по карте пятерочки яйца С0 10 штук и сметану 20%` | `яйцо` with `10 pcs`, attribute `category=C0`; `сметана` with `fat_percent=20`. |
| `pt_package_001` | Package count | `2 молока Простоквашино и творог` | `молоко`, `brand=Простоквашино`, `package_count=2`; `творог` no quantity. |
| `pt_size_001` | Package size | `3 пачки творога по 180 г, сметана 300 г` | `творог` with `package_count=3`, `package_size_value=180`, `package_size_unit=g`; `сметана` with `quantity_value=300`, `quantity_unit=g`. |
| `pt_brand_001` | Brand | `йогурт Агуша питьевой 2 штуки` | `йогурт`, `brand=Агуша`, `quantity_value=2`, `quantity_unit=pcs`, attribute `type=питьевой`. |
| `pt_private_001` | Private label | `красная цена гречка 900 г` | If policy treats `Красная цена` as brand: `гречка`, `brand=Красная цена`, `quantity_value=900`, `quantity_unit=g`. Otherwise put no brand and document policy before TEST. |
| `pt_promo_001` | Promo noise | `что там по акции: сыр 200 г, колбаса докторская` | `сыр` with `200 g`; `колбаса` with attribute `type=докторская`. No promo-only field. |
| `pt_typos_001` | Typos | `картохи 2кг, помидорки черри 500гр` | `картофель` with `2 kg`; `помидор` with `500 g`, attribute `variety=черри`. |
| `pt_repeat_001` | Similar items | `молоко 2 л и молоко безлактозное 1 л` | Two `молоко` items: one plain `2 l`; one `1 l` with `lactose_free=true`. |
| `pt_ambiguous_001` | Ambiguous | `пару молока и пару бананов` | Fix policy before TEST. Candidate policy: `молоко package_count=2`; `банан quantity_value=2`, `quantity_unit=pcs` only if accepted by project policy. |
| `pt_noise_001` | Extra text | `добавь пожалуйста как обычно хлеб, но без замен, и яблоки голден 1 кг` | `хлеб` no quantity; `яблоко` with `1 kg`, attribute `variety=голден`. Ignore replacement preference. |
| `pt_units_001` | Units | `кола 0.9 л, вода 1500 мл, куриная грудка 1.5 кг` | `кола` with `0.9 l`; `вода` with `1500 ml`; `куриная грудка` with `1.5 kg`. |

## Provider and Model Benchmark Matrix

Use at least the providers required by the base spec. Model names come from environment variables and benchmark config; do not hardcode pricing or claim current pricing in this experiment file.

| Provider | Model source | Production mode | Parity mode | Prompt variants |
|---|---|---|---|---|
| OpenAI | `OPENAI_MODEL` | JSON Schema / Structured Output where available | JSON Object / prompt-enforced JSON | `parser_v1`, `parser_short_v1` |
| Qwen / Alibaba Cloud Model Studio | `QWEN_MODEL` | JSON Schema with `strict=true` if supported, else JSON Object | JSON Object / prompt-enforced JSON | `parser_v1`, `parser_short_v1` |
| DeepSeek | `DEEPSEEK_MODEL` | JSON Object + Pydantic validation | JSON Object + Pydantic validation | `parser_v1` |

Mode A production is the decision benchmark. Mode B parity is diagnostic and separates model behavior from structured-output support.

## Quality Gates

Initial gate, copied from the base benchmark and applied to the frozen Пятерочка TEST set:

| Metric | Threshold |
|---|---:|
| `schema_valid_rate` | `>= 99.5%` |
| `item_recall` | `>= 99.0%` |
| `item_precision` | `>= 99.0%` |
| `quantity_value_accuracy` | `>= 98.5%` |
| `quantity_unit_accuracy` | `>= 98.5%` |
| `package_semantics_accuracy` | `>= 99.0%` |
| `critical_error_rate` | `<= 0.5%` |
| `whole_order_exact_match` | `>= 95.0%` |

Any threshold changes are allowed only after DEV analysis and before freezing TEST.

Critical errors include missing items, extra items, wrong quantities, wrong units, physical quantity converted to package count, package count converted to physical quantity, invented brand, lost explicit brand, lost critical attribute, and invented product.

## Cost, Latency, and Reliability Metrics

Cost must be calculated from `benchmark_config.yaml` pricing values. If an exact provider pricing model is not configured, cost fields remain `null`.

Economic metrics:

| Metric | Definition |
|---|---|
| `total_cost_usd` | Sum of all attempts, including retries. |
| `mean_cost_per_order` | Average cost per evaluated input. |
| `cost_per_1k_orders` | Projected cost per 1000 submitted orders. |
| `cost_per_100k_orders` | Projected cost per 100000 submitted orders. |
| `cost_per_1k_valid_orders` | Cost normalized by schema-valid outputs. |
| `cost_per_1k_exact_matches` | Primary price-quality metric. |

Latency metrics:

| Metric | Scope |
|---|---|
| `latency_ms` | Per API attempt. |
| `end_to_end_latency_ms` | Per case/configuration including retries. |
| `mean`, `p50`, `p90`, `p95`, `p99` | Aggregated per provider/model/prompt/mode. |

Reliability metrics:

| Metric | Notes |
|---|---|
| `request_count` | Includes retries. |
| `successful_http_requests` | HTTP-level success count. |
| `http_error_rate` | 4xx/5xx rate. |
| `timeout_rate` | Timeout failures. |
| `empty_response_rate` | Empty content in JSON mode is a failure. |
| `invalid_json_rate` | Non-parseable JSON. |
| `schema_validation_failure_rate` | JSON parse succeeds but schema fails. |
| `network_retry_rate` | Retry rate from timeout, connection, 429, selected 5xx. |
| `schema_retry_rate` | Retry rate from empty response, invalid JSON, schema failure. |
| `final_failure_rate` | Failure after allowed retries. |

Report both `first_attempt_quality` and `production_quality_after_retry`.

## Run Plan

### Pass 0 - Local Tests

No API calls.

Actions:

1. Validate canonical Pydantic schema and generated JSON Schema.
2. Validate dataset loader on Пятерочка JSONL examples.
3. Test canonicalization: lowercase, trim, `ё -> е`, unit aliases, sorted attributes, `1.0 == 1`.
4. Test evaluator for exact match, missing item, extra item, wrong quantity/unit, package semantic error, aliases, reordered items.
5. Test pricing with configured and `null` prices.
6. Generate dry-run report.

Exit criteria:

1. Unit tests pass.
2. Dataset has no duplicate IDs.
3. Dry run shows planned providers, models, prompts, modes, pricing status, and API call count.

### Pass 1 - Smoke

Scope:

```text
3 providers x 5 Пятерочка cases x 1 run
```

Actions:

1. Use production mode.
2. Include cases for simple list, package count, package size, store-name noise, and brand/private-label handling.
3. Save raw attempts, parsed JSON, usage, latency, and errors.
4. Confirm no API keys or authorization headers are saved.

Exit criteria:

1. Each configured provider returns at least one schema-valid response.
2. Empty response, invalid JSON, and schema mismatch are classified correctly.
3. Retry accounting includes cost and latency.

### Pass 2 - DEV

Scope:

```text
~50 DEV cases x candidate models x prompt variants x production/parity modes
```

Actions:

1. Compare `parser_v1` against `parser_short_v1` where configured.
2. Review errors manually by category.
3. Decide ambiguous policies such as `пару молока`, private-label brand treatment, and `штуки` for countable grocery items.
4. Adjust prompt, accepted aliases, and deterministic evaluator only before TEST freeze.
5. Record prompt hash and config snapshot for selected candidates.

Exit criteria:

1. Final TEST policies are documented.
2. Prompt version is fixed.
3. Final candidate configurations are selected without choosing a winner.

### Pass 3 - Frozen TEST

Scope:

```text
~250 frozen TEST cases x final configurations
```

Actions:

1. Run production mode as the main benchmark.
2. Run parity mode as a diagnostic comparison.
3. Randomize provider order per case with fixed seed.
4. Save dataset hash, prompt hashes, config snapshot, model names, Python/package versions, git commit, timestamp, and seed.
5. Apply quality gates without changing gold or prompt.

Exit criteria:

1. `summary.csv`, `summary.json`, and `report.md` are generated.
2. Every configuration is marked `Passes quality gate: YES/NO`.
3. Rejected configurations list gate failures by metric.

### Pass 4 - Stability

Scope:

```text
30-50 hard cases x 3-5 runs x best 2-3 configurations
```

Actions:

1. Re-run difficult Пятерочка cases involving package semantics, store noise, brands, and ambiguous quantities.
2. Measure `exact_match_rate_across_runs`, `schema_valid_rate_across_runs`, `output_variation_rate`, and `critical_error_any_run`.
3. Compare first-attempt stability with production-after-retry stability.

Exit criteria:

1. Recommended primary and fallback are selected from configurations that passed TEST quality gates.
2. Stability risks are documented before production integration.

## Reporting Outputs

Each run writes to:

```text
results/{run_id}/
```

Required files:

| File | Contents |
|---|---|
| `config_snapshot.yaml` | Exact config and pricing fields used for the run. |
| `env_metadata.json` | Non-secret environment metadata. |
| `dataset_hash.txt` | SHA-256 of dataset. |
| `prompt_hashes.json` | Prompt version hashes. |
| `raw_attempts.jsonl` | One row per API attempt. |
| `evaluated_cases.jsonl` | One row per case/configuration. |
| `summary.csv` | Flat comparison table. |
| `summary.json` | Machine-readable aggregate metrics. |
| `report.md` | Human-readable analysis. |
| `errors.jsonl` | Classified failures and critical errors. |

Main report table:

| Provider | Model | Prompt | Mode | Schema valid | Item recall | Quantity | Package semantics | Exact order | Critical errors | Retry rate | p95 latency | Cost / 1k | Cost / 1k exact |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

The report must include:

1. Recommended primary.
2. Recommended fallback.
3. Rejected by quality gate.
4. First-attempt vs production-after-retry comparison.
5. Category-level failure analysis for Пятерочка-specific cases.
6. Cost fields as `null` when pricing config is incomplete.

## Risks

| Risk | Mitigation |
|---|---|
| Gold data encodes unstable ambiguity policy | Freeze and document policies before TEST; do not change them per provider. |
| Пятерочка-specific phrases leak into product names | Include store-name, loyalty-card, promo, and replacement-noise cases in DEV/TEST. |
| Model invents package count when quantity is absent | Gate on package semantics and include many no-quantity examples. |
| Model treats physical quantity as package count | Critical error classification and hard stability cases. |
| Brand/private-label policy inconsistency | Decide accepted brand policy before TEST; use accepted aliases only in evaluator metadata. |
| Pricing data missing or stale | Keep prices in config with `effective_date`; output `null` when cost cannot be computed. |
| Retry hides poor first-attempt reliability | Report first-attempt quality separately from production-after-retry quality. |
| Provider structured-output differences dominate results | Use production mode for decision and parity mode for diagnosis. |
| Dataset overfits to prompt examples | Keep frozen TEST separate from DEV; avoid editing prompt after TEST freeze. |
| Secrets leak into artifacts | Never save API keys, authorization headers, or `.env` values in raw attempts or reports. |

## Next Actions

1. Convert the example cases above into `data/dev.jsonl` with full schema fields.
2. Define and document ambiguity policies for `пару`, private-label brands, `штуки`, replacement preferences, and promo wording.
3. Expand DEV to ~50 cases across all Пятерочка-specific categories.
4. Implement or verify deterministic evaluator behavior before any API calls.
5. Fill model names and pricing config externally through `.env` and `benchmark_config.yaml`; do not hardcode prices in code.
6. Run Pass 0 local tests and dry run.
7. Run Pass 1 smoke with 5 cases and inspect raw failures.
8. Iterate only on DEV, then freeze TEST and run Pass 3.
9. Run Pass 4 stability for the top passing configurations.
