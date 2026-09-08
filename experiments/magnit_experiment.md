# Magnit Parser Benchmark Experiment

## Objective

Benchmark LLM providers for parsing Russian free-form Telegram shopping requests into the canonical `ShoppingList` structure for a grocery optimization bot focused on Магнит.

The parser must perform only extraction and normalization. It must not select Магнит SKUs, infer availability, choose delivery options, estimate prices, optimize substitutions, calculate package counts, or assume missing quantities. Those steps belong to deterministic application code after parsing.

Primary decision rule:

1. Exclude configurations that fail the quality gate.
2. Among passing configurations, rank by `cost_per_1k_exact_matches`.
3. Use `critical_error_rate`, `p95_latency`, `retry_rate`, and operational complexity as tie-breakers.

No provider or model is preselected.

## Magnit-Specific User Input Risks

Магнит-focused Telegram traffic is likely to include store-specific language, brand ambiguity, promo language, and delivery substitutions. The benchmark must measure whether the parser extracts only explicit shopping intent.

Key risks:

- Store name pollution: user mentions `Магнит`, `Магнит у дома`, `Магнит Семейный`, or `Магнит Косметик`; parser must not add store as product, brand, or attribute unless the user asks for a product branded Магнит.
- Private label ambiguity: `Магнит` can be a shop or a brand/private-label cue. Gold policy must distinguish `в Магните купи молоко` from `молоко Магнит`.
- Promo noise: phrases like `по акции`, `с желтым ценником`, `если скидка`, `дешевле`, `2 по цене 1` should be attributes only when explicitly relevant and must not create quantities unless policy says so.
- Package semantics: Магнит catalog often has bottles, packs, trays, doypacks, nets, and multipacks. Parser must distinguish `2 л молока`, `2 молока`, `2 бутылки молока`, and `молоко 2 бутылки по 950 мл`.
- Weight vs package size: `сыр 300 г`, `сыр кусок 300 г`, `2 упаковки сыра по 300 г` have different fields.
- Countable grocery units: eggs, yogurts, baby food jars, canned goods, bananas, and bakery items may use `шт`, packs, or physical mass.
- Product line and brand confusion: `Простоквашино`, `Домик в деревне`, `Брест-Литовск`, `Моя цена`, `Красная цена`, `Магнит Свежесть` may be brands or product-line text. Only explicit brand text goes to `brand`.
- Fresh department terms: `фарш домашний`, `салат готовый`, `курица охлажденная`, `нарезка`, `кулинария` should normalize product names without inventing SKU details.
- User substitutions: `если нет, возьми другое`, `любой`, `самое дешевое`, `как обычно` should not cause product invention. Keep explicit constraints as attributes only where useful.
- Cosmetics/non-food leakage: users may mention `Магнит Косметик`, household goods, or pharmacy-like items. This experiment should either include an explicit out-of-scope policy or measure non-food parsing separately.

## Dataset Plan

Use the same JSONL case format as the parser benchmark instruction:

```json
{
  "id": "magnit_simple_001",
  "category": "magnit_simple",
  "input": "в Магните возьми молоко 2 литра и бананы 1 кг",
  "gold": {
    "items": []
  }
}
```

The final `gold.items` must use only fields from the canonical `ShoppingList` schema. Evaluator-only fields such as `accepted_product_names` may be kept outside the schema and must not be sent to models.

Recommended splits:

| Split | Size | Purpose |
|---|---:|---|
| `dev.jsonl` | 50 | Prompt and policy tuning before freezing |
| `test.jsonl` | 250 | Final Магнит benchmark |
| `stability.jsonl` | 30-50 | Hard Магнит cases repeated 3-5 times |

Recommended TEST category allocation:

| Category | Cases |
|---|---:|
| Магнит store-name noise | 25 |
| Simple grocery lists | 30 |
| Conversational Telegram requests | 30 |
| kg / g / l / ml / pcs quantities | 30 |
| Packages, bottles, trays, nets | 30 |
| Package size `по N г/мл` | 20 |
| Promo and substitution noise | 20 |
| Brands and private labels | 25 |
| Product attributes: fat, type, variety, category | 25 |
| Typos, slang, cases, abbreviations | 20 |
| Ambiguous package semantics | 20 |
| Repeated or close products | 15 |
| Out-of-scope or mixed Магнит Косметик input | 10 |

## Russian Example Cases and Gold Expectations

These examples define the intended policy. Full JSONL gold should expand every item with all schema fields.

### Store Name Noise

Input:

```text
в Магните купи молоко 2 литра, хлеб и бананы 1 кг
```

Gold expectations:

- `молоко`: `quantity_value=2`, `quantity_unit="l"`
- `хлеб`: all quantity/package fields `null`
- `банан`: `quantity_value=1`, `quantity_unit="kg"`
- No item, brand, or attribute for `Магнит`.

Input:

```text
добавь из Магнита творог 5% и яйца С0 10 штук
```

Gold expectations:

- `творог`: attribute `fat_percent=5`
- `яйцо`: `quantity_value=10`, `quantity_unit="pcs"`, attribute `category=C0`
- No store attribute.

### Private Label and Brand

Input:

```text
молоко Магнит 1 л и сметана Простоквашино 20%
```

Gold expectations:

- `молоко`: `brand="Магнит"`, `quantity_value=1`, `quantity_unit="l"`
- `сметана`: `brand="Простоквашино"`, attribute `fat_percent=20`

Input:

```text
в Магните молоко 1 л
```

Gold expectations:

- `молоко`: `quantity_value=1`, `quantity_unit="l"`
- `brand=null`

### Package Semantics

Input:

```text
2 молока, 1 кефир и 3 пачки творога по 180 г
```

Gold expectations:

- `молоко`: `package_count=2`
- `кефир`: `package_count=1`
- `творог`: `package_count=3`, `package_size_value=180`, `package_size_unit="g"`

Input:

```text
молоко 2 л и две бутылки воды по 1.5 л
```

Gold expectations:

- `молоко`: `quantity_value=2`, `quantity_unit="l"`, `package_count=null`
- `вода`: `package_count=2`, `package_size_value=1.5`, `package_size_unit="l"`

### Promo and Substitution Noise

Input:

```text
возьми сыр 300 г если по акции, иначе любой недорогой
```

Gold expectations:

- `сыр`: `quantity_value=300`, `quantity_unit="g"`
- Optional fixed policy before TEST: either ignore promo/substitution text or store explicit constraints as attributes such as `promo=true`, `substitution=любой недорогой`.
- Do not create extra items.

Input:

```text
яблоки голден 1 кг, если нет голден то любые красные
```

Gold expectations:

- `яблоко`: `quantity_value=1`, `quantity_unit="kg"`, attribute `variety=голден`
- Optional fixed policy: substitution text may be ignored or stored as `substitution=любые красные`.

### Fresh and Prepared Foods

Input:

```text
куриная грудка охлажденная 800 г, фарш домашний 500 г
```

Gold expectations:

- `куриная грудка`: `quantity_value=800`, `quantity_unit="g"`, attribute `state=охлажденная`
- `фарш`: `quantity_value=500`, `quantity_unit="g"`, attribute `type=домашний`

Input:

```text
салат оливье готовый 400 г и нарезку сыра 200 г
```

Gold expectations:

- `салат оливье`: `quantity_value=400`, `quantity_unit="g"`, attribute `prepared=true`
- `сыр`: `quantity_value=200`, `quantity_unit="g"`, attribute `form=нарезка`

### Typos and Telegram Style

Input:

```text
магнит: малако 2л, бананав кило, яица 10шт плз
```

Gold expectations:

- `молоко`: `quantity_value=2`, `quantity_unit="l"`
- `банан`: `quantity_value=1`, `quantity_unit="kg"`
- `яйцо`: `quantity_value=10`, `quantity_unit="pcs"`
- `плз` ignored.

### Repeated and Close Products

Input:

```text
молоко обычное 1 л и молоко безлактозное 1 л
```

Gold expectations:

- Two separate `молоко` items if the evaluator policy supports duplicate products with distinct attributes.
- First item: attribute `type=обычное`
- Second item: attribute `lactose_free=true`
- Matching must not collapse distinct requested products.

### Out-of-Scope Mixed Input

Input:

```text
в Магнит Косметик нужен шампунь, а в Магните хлеб и молоко
```

Gold expectations:

- If experiment scope is grocery-only: include `хлеб` and `молоко`; exclude `шампунь` with an explicit dataset policy.
- If bot supports mixed baskets later: keep `шампунь` in a separate future schema, not in this benchmark unless `ShoppingList` scope is widened.

Freeze this policy before Pass 3.

## Provider and Model Benchmark Matrix

Use the same provider families from the benchmark instruction. Model names come from `.env` and config, not from this report.

| Provider | Model source | Production mode | Parity mode | Prompt variants | Notes |
|---|---|---|---|---|---|
| OpenAI | `OPENAI_MODEL` | JSON Schema / Structured Output where available | JSON Object / prompt-enforced JSON | `parser_v1`, `parser_short_v1` | Use official SDK. Save actual response mode and request parameters. |
| Qwen / Alibaba Cloud Model Studio | `QWEN_MODEL` | JSON Schema with `strict=true` if selected model supports it, otherwise JSON Object | JSON Object / prompt-enforced JSON | `parser_v1`, `parser_short_v1` | `QWEN_BASE_URL` is user-supplied. Record fallback from schema mode if used. |
| DeepSeek | `DEEPSEEK_MODEL` | JSON Object | JSON Object | `parser_v1` | Empty content in JSON mode is a measured failure. |

Do not use provider-specific semantic prompt hacks. Technical API differences are allowed and must be recorded.

## Quality Gates

Apply the working gate from the base benchmark unless DEV shows that a threshold must be adjusted. Any adjustment must be made after DEV and before frozen TEST.

| Metric | Gate |
|---|---:|
| `schema_valid_rate` | `>= 99.5%` |
| `item_recall` | `>= 99.0%` |
| `item_precision` | `>= 99.0%` |
| `quantity_value_accuracy` | `>= 98.5%` |
| `quantity_unit_accuracy` | `>= 98.5%` |
| `package_semantics_accuracy` | `>= 99.0%` |
| `critical_error_rate` | `<= 0.5%` |
| `whole_order_exact_match` | `>= 95.0%` |

Магнит-specific critical errors to tag in addition to the base list:

- `store_name_as_product`
- `store_name_as_brand`
- `promo_text_as_quantity`
- `package_size_as_quantity`
- `quantity_as_package_count`
- `lost_private_label_brand`
- `invented_private_label_brand`
- `collapsed_distinct_duplicate_product`
- `included_out_of_scope_non_food`

## Cost, Latency, and Reliability Metrics

Use configured pricing only. Do not hardcode or claim current API prices in the experiment report. If pricing is unknown, cost fields are `null`.

Cost metrics:

- `total_cost_usd`
- `mean_cost_per_order`
- `p50_cost_per_order`
- `p95_cost_per_order`
- `cost_per_1k_orders`
- `cost_per_100k_orders`
- `cost_per_1k_valid_orders`
- `cost_per_1k_exact_matches`

Token metrics:

- mean / p50 / p95 `input_tokens`
- mean / p50 / p95 `output_tokens`
- mean / p50 / p95 `total_tokens`
- cached and reasoning tokens when available

Latency metrics:

- attempt-level `latency_ms`
- case-level `end_to_end_latency_ms`
- aggregate mean, p50, p90, p95, p99

Reliability metrics:

- `request_count`
- `successful_http_requests`
- `http_error_rate`
- `timeout_rate`
- `empty_response_rate`
- `invalid_json_rate`
- `schema_validation_failure_rate`
- `network_retry_rate`
- `schema_retry_rate`
- `final_failure_rate`
- first-attempt quality vs production quality after retry

## Run Plan

### Pass 0 - Local Tests

Goal: prove that schema, dataset, evaluator, pricing, and report generation work without API calls.

Actions:

- Build or reuse canonical `ShoppingList` Pydantic schema.
- Validate Магнит DEV/TEST/STABILITY JSONL format.
- Check duplicate case IDs and malformed JSONL handling.
- Unit-test deterministic canonicalization: lowercase, trim, `ё` to `е`, unit aliases, numeric equality, sorted attributes.
- Unit-test Магнит-specific evaluator errors such as `store_name_as_product`, `store_name_as_brand`, and package semantic mistakes.
- Run dry-run and verify planned calls, models, prompts, modes, and pricing config status.

Exit criteria:

- Unit tests pass.
- Dry-run makes zero API calls.
- Dataset hashes are generated.

### Pass 1 - Smoke

Goal: verify that every configured provider can parse a small Магнит sample and that raw attempts are saved.

Scope:

```text
3 providers x 5 cases x 1 run
```

Use cases covering:

- store-name noise;
- physical quantity;
- package count;
- package size;
- explicit brand/private label.

Exit criteria:

- Raw attempts, parsed JSON, usage, latency, and errors are persisted.
- API keys and Authorization headers are absent from logs and reports.
- At least one successful response per configured provider, or a classified provider failure.

### Pass 2 - DEV

Goal: tune prompt choice and finalize ambiguous Магнит policies before freezing TEST.

Scope:

```text
~50 DEV cases x candidate models x prompt variants x production/parity modes
```

Actions:

- Compare `parser_v1` and `parser_short_v1` for OpenAI and Qwen where configured.
- Use `parser_v1` for DeepSeek unless a short-prompt variant is explicitly added as a separate named configuration.
- Review all failures manually by category.
- Decide fixed policy for promo text, substitutions, duplicate product handling, and mixed Магнит Косметик inputs.
- Freeze prompt version/hash and dataset policy before Pass 3.

Exit criteria:

- Final configs for TEST are selected without using TEST performance.
- All ambiguous gold policies are documented.

### Pass 3 - Frozen TEST

Goal: produce the main provider/model comparison.

Scope:

```text
~250 frozen TEST cases x final configurations x 1 run
```

Rules:

- Do not change prompts, schema, canonicalization, or gold during this pass.
- Randomize provider order per case with a fixed seed.
- Include retries in cost and latency.
- Preserve failed cases and classified errors.

Exit criteria:

- `summary.csv`, `summary.json`, and `report.md` include all required metrics.
- Each configuration is marked `Passes quality gate: YES/NO`.
- Recommended primary/fallback are derived only from measured results.

### Pass 4 - Stability

Goal: measure repeatability on hard Магнит cases.

Scope:

```text
30-50 hard cases x 3-5 runs x best 2-3 configurations
```

Hard cases should include:

- store vs brand ambiguity;
- duplicate milk/yogurt products with different attributes;
- typo-heavy Telegram messages;
- promo/substitution noise;
- package size vs quantity ambiguity;
- mixed grocery/non-food text.

Metrics:

- `exact_match_rate_across_runs`
- `schema_valid_rate_across_runs`
- `output_variation_rate`
- `critical_error_any_run`

Exit criteria:

- Primary parser does not pass solely because of a lucky TEST run.
- Fallback parser is selected from a stable passing configuration when possible.

## Reporting Outputs

Every run writes to:

```text
results/{run_id}/
```

Required files:

- `config_snapshot.yaml`
- `env_metadata.json`
- `dataset_hash.txt`
- `prompt_hashes.json`
- `raw_attempts.jsonl`
- `evaluated_cases.jsonl`
- `summary.csv`
- `summary.json`
- `report.md`
- `errors.jsonl`

`report.md` must include:

- objective and dataset snapshot;
- provider/model/prompt/mode matrix;
- quality gate table;
- summary table with schema validity, item recall, quantity accuracy, package semantics, exact order rate, critical errors, retry rate, p95 latency, cost per 1k, and cost per 1k exact;
- first-attempt reliability vs production-after-retry reliability;
- top failure categories with Магнит-specific examples;
- recommended primary;
- recommended fallback;
- rejected configurations with gate reason;
- pricing config status and effective dates from config;
- reproducibility metadata: dataset SHA-256, prompt SHA-256, config snapshot, model names, Python/package versions, git commit, timestamp, and random seed.

## Risks

- Real user Магнит phrasing may differ from synthetic cases. Mitigation: add anonymized production examples to DEV first, then freeze new TEST cases for future runs.
- Store/private-label ambiguity can cause false brands. Mitigation: explicit gold policy and critical error tags.
- Promo and substitution text can be over-extracted. Mitigation: decide whether those are ignored or stored as attributes before TEST.
- Duplicate products with different attributes can be collapsed by evaluator or model. Mitigation: deterministic bipartite matching and dedicated duplicate cases.
- Cost comparison can be misleading if provider usage fields differ. Mitigation: normalize usage fields, keep original usage object, and set unknown cost to `null`.
- API behavior can change over time. Mitigation: save config snapshots, model names, prompt hashes, and documentation/pricing effective dates.
- Retried success can hide operational weakness. Mitigation: report first-attempt and after-retry metrics separately.
- Non-food Магнит Косметик requests can pollute grocery optimization. Mitigation: freeze an out-of-scope policy before TEST.

## Next Actions

1. Convert the example cases above into `data/dev.jsonl` with full `ShoppingList` gold objects.
2. Define evaluator-only aliases for common Магнит grocery names, especially dairy, eggs, meat, produce, and prepared foods.
3. Write explicit policy notes for promo text, substitutions, duplicate products, and Магнит Косметик scope.
4. Add Магнит-specific critical error tags to evaluator tests.
5. Run Pass 0 locally with `--dry-run`.
6. Run Pass 1 smoke with 5 cases only.
7. Review smoke failures before expanding to DEV.
8. Freeze DEV decisions, prompt hash, schema hash, and TEST gold before Pass 3.
