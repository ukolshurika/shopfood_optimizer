# VkusVill Parser Benchmark Experiment

## Objective

Evaluate which LLM API/model configuration most reliably parses Russian free-form ВкусВилл shopping requests into the canonical `ShoppingList` structure for a grocery optimization Telegram bot.

The experiment measures:

- extraction quality against frozen gold labels;
- cost from benchmark pricing config, not hardcoded assumptions;
- latency and retry behavior;
- API reliability under normal bot-like request volume.

Selection rule:

1. Keep only configurations that pass the quality gate.
2. Among passing configurations, prefer the lowest `cost_per_1k_exact_matches`.
3. If costs are close, prefer lower critical error rate, lower p95 latency, lower retry rate, and lower operational complexity.

The parser must only extract and normalize user intent. It must not choose ВкусВилл SKUs, infer package defaults, compute корзина contents, compare prices, choose delivery slots, or optimize the order.

## Canonical Output Schema

Use the same canonical `ShoppingList` schema from `parser_benchmark_agent_instruction.md`:

- `ShoppingList.items`
- `ShoppingItem.product`
- `brand`
- `quantity_value`
- `quantity_unit`: `g`, `kg`, `ml`, `l`, `pcs`
- `package_count`
- `package_size_value`
- `package_size_unit`
- `attributes`

No ВкусВилл-specific business schema should be introduced for benchmark scoring. Store ВкусВилл-specific concepts only as normalized product names, explicit brands, or explicit attributes.

## VkusVill-Specific User Input Risks

ВкусВилл users are likely to write requests with shop-specific shorthand, product-line names, dietary labels, and packaging assumptions. The benchmark must catch these failure modes:

- Shop name noise: `во вкусвилле`, `из ВВ`, `вкусвилл доставка` must not become products or brands unless explicitly attached to a product as brand text.
- Product-line ambiguity: `избенка`, `вкусвилл`, `вв` may be a shop/line reference, not necessarily a user-requested brand.
- Package default hallucination: `творог`, `молоко`, `котлеты` must not become `package_count=1`.
- Physical quantity vs packages: `2 молока` means two packages; `2 литра молока` means physical quantity.
- ВкусВилл pack names: `баночка`, `лоток`, `пачка`, `бутылка`, `упаковка`, `коробка`, `стаканчик` should map to `package_count` only when the count is explicit.
- Package size: `2 творога по 180 г`, `йогурт 4 штуки по 125 г` must preserve both package count and package size.
- Dietary and product attributes: `без сахара`, `безлактозное`, `растительное`, `фермерское`, `детское`, `органик`, `халяль`, `постное`, `замороженное` must be attributes if explicit.
- Percent attributes: `молоко 3.2%`, `творог 5%`, `сливки 10%` must become explicit attributes, not quantities.
- Varieties and cuts: `яблоки голден`, `сыр маасдам`, `фарш индейка`, `бедро куриное без кости` must preserve the useful attribute or normalized product name.
- Prepared food: `сырники`, `котлеты`, `салат цезарь`, `суп том ям` may be ready meals, not raw ingredients.
- Multiple close items: `молоко обычное и безлактозное`, `творог 5 и 9 процентов` must stay as separate items if the user requested separate products.
- Negation and substitutions: `не бери бананы`, `если нет голубики возьми чернику` are outside pure extraction unless the benchmark explicitly adds policy fields later. For this schema, only requested positive products should be included according to frozen dataset policy.
- Telegram noise: greetings, voice transcript artifacts, punctuation loss, repeated words, and mixed Russian/English must not pollute product names.

## Dataset Plan

Use three JSONL datasets:

- `dev.jsonl`: about 50 ВкусВилл-focused cases for prompt and policy iteration.
- `test.jsonl`: about 250 frozen cases for final scoring.
- `stability.jsonl`: 30-50 hard ВкусВилл cases, run 3-5 times.

Target test distribution:

| Category | Cases |
|---|---:|
| Simple ВкусВилл lists | 30 |
| Conversational Telegram requests | 30 |
| kg/g/l/ml/pcs quantities | 30 |
| Packages, bottles, trays, jars | 25 |
| Package size `по N г/мл` | 25 |
| Dietary and composition attributes | 30 |
| Fat percent, category, variety | 25 |
| ВкусВилл/shop-name noise | 20 |
| Typos, slang, mixed casing | 20 |
| Ambiguous/substitution-like text | 20 |
| Repeated or close products | 15 |

Gold labels must be frozen before final TEST. Ambiguous policy decisions must be documented before comparing providers.

## Russian Example Cases and Gold Expectations

### Case vv_simple_001

Input:

```text
Во ВкусВилле возьми молоко 2 литра, творог 5%, бананы 1 кг
```

Gold expectation:

```json
{
  "items": [
    {
      "product": "молоко",
      "brand": null,
      "quantity_value": 2,
      "quantity_unit": "l",
      "package_count": null,
      "package_size_value": null,
      "package_size_unit": null,
      "attributes": []
    },
    {
      "product": "творог",
      "brand": null,
      "quantity_value": null,
      "quantity_unit": null,
      "package_count": null,
      "package_size_value": null,
      "package_size_unit": null,
      "attributes": [{"key": "fat_percent", "value": "5"}]
    },
    {
      "product": "банан",
      "brand": null,
      "quantity_value": 1,
      "quantity_unit": "kg",
      "package_count": null,
      "package_size_value": null,
      "package_size_unit": null,
      "attributes": []
    }
  ]
}
```

### Case vv_package_001

Input:

```text
2 пачки творога по 180 г и 3 бутылки воды по 1.5 л
```

Gold expectation:

```text
творог: package_count=2, package_size_value=180, package_size_unit=g
вода: package_count=3, package_size_value=1.5, package_size_unit=l
```

### Case vv_semantics_001

Input:

```text
2 молока, яйца С0 10 штук, сыр маасдам
```

Gold expectation:

```text
молоко: package_count=2, quantity_value=null, quantity_unit=null
яйцо: quantity_value=10, quantity_unit=pcs, attributes=[category=C0]
сыр: attributes=[variety=маасдам]
```

### Case vv_attributes_001

Input:

```text
нужно безлактозное молоко, йогурт без сахара, растительное мясо
```

Gold expectation:

```text
молоко: attributes=[lactose_free=true]
йогурт: attributes=[sugar_free=true]
мясо: attributes=[plant_based=true]
```

### Case vv_noise_001

Input:

```text
привет, добавь из вкусвилла пожалуйста куриную грудку без кожи 700 г и помидоры черри
```

Gold expectation:

```text
куриная грудка: quantity_value=700, quantity_unit=g, attributes=[skinless=true]
помидор черри: no quantity fields
```

### Case vv_repeated_001

Input:

```text
молоко обычное 1 л и молоко безлактозное 1 л
```

Gold expectation:

```text
two separate молоко items:
1. quantity_value=1, quantity_unit=l, attributes=[type=обычное]
2. quantity_value=1, quantity_unit=l, attributes=[lactose_free=true]
```

### Case vv_ambiguous_001

Input:

```text
пару йогуртов и творог
```

Gold policy:

```text
йогурт: package_count=2
творог: all quantity fields null
```

The `пару` policy must be fixed before TEST and applied equally to all providers.

### Case vv_negative_001

Input:

```text
бананы не надо, возьми яблоки голден 1 кг
```

Gold policy:

```text
яблоко: quantity_value=1, quantity_unit=kg, attributes=[variety=голден]
банан: excluded
```

This case tests whether the parser avoids extracting explicitly negated products. If the production parser does not support negation, classify this category separately and do not mix it into the main quality gate until policy is approved.

## Provider and Model Benchmark Matrix

Use provider adapters from the base benchmark spec and configure exact model names through `.env`.

| Provider | Model source | Production mode | Parity mode | Prompt variants | Required notes |
|---|---|---|---|---|---|
| OpenAI | `OPENAI_MODEL` | JSON Schema / Structured Output | JSON Object / prompt-enforced JSON | `parser_v1`, `parser_short_v1` | Use pricing from config only |
| Qwen / Alibaba Cloud Model Studio | `QWEN_MODEL` | JSON Schema if supported, otherwise JSON Object | JSON Object / prompt-enforced JSON | `parser_v1`, `parser_short_v1` | Record actual `QWEN_BASE_URL` and response mode, without secrets |
| DeepSeek | `DEEPSEEK_MODEL` | JSON Object + Pydantic validation | JSON Object + Pydantic validation | `parser_v1` | Empty content in JSON mode is a benchmark failure |

Do not tune semantic prompts per provider in the main benchmark. Provider-specific prompt variants may be added only as separately named exploratory configurations.

## Quality Gates

Use the base quality gate unless DEV results justify changing thresholds before frozen TEST:

| Metric | Gate |
|---|---:|
| `schema_valid_rate` | >= 99.5% |
| `item_recall` | >= 99.0% |
| `item_precision` | >= 99.0% |
| `quantity_value_accuracy` | >= 98.5% |
| `quantity_unit_accuracy` | >= 98.5% |
| `package_semantics_accuracy` | >= 99.0% |
| `critical_error_rate` | <= 0.5% |
| `whole_order_exact_match` | >= 95.0% |

Add a ВкусВилл-focused review table for critical categories:

| Category | Required review |
|---|---|
| Shop-name noise | No `ВкусВилл`/`ВВ` invented products |
| Package semantics | No conversion between packages and physical quantity |
| Dietary attributes | No loss of explicit `без сахара`, `безлактозное`, `растительное` |
| Percent attributes | No confusion between fat percent and quantity |
| Close repeated items | Separate explicit variants remain separate |

## Cost, Latency, and Reliability Metrics

Cost metrics:

- `total_cost_usd`
- `mean_cost_per_order`
- `p50_cost_per_order`
- `p95_cost_per_order`
- `cost_per_1k_orders`
- `cost_per_100k_orders`
- `cost_per_1k_valid_orders`
- `cost_per_1k_exact_matches`

Cost calculation must use provider pricing values from `benchmark_config.yaml`. If pricing is not filled or cannot be represented accurately, output `null` cost fields and still report usage tokens.

Latency metrics:

- attempt-level `latency_ms`;
- case-level `end_to_end_latency_ms`;
- aggregate `mean`, `p50`, `p90`, `p95`, `p99`.

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

Report both:

- `first_attempt_quality`
- `production_quality_after_retry`

Retries count as separate API calls and must be included in cost and latency.

## Run Plan

### Pass 0 - Local Tests

Purpose: validate benchmark mechanics before any paid or remote API call.

Actions:

- Validate `ShoppingList` Pydantic schema and generated JSON Schema.
- Load ВкусВилл `dev.jsonl`, `test.jsonl`, and `stability.jsonl`.
- Check duplicate case IDs.
- Run canonicalization tests for lowercase, whitespace, `ё` to `е`, numeric equality, unit aliases, and sorted attributes.
- Run evaluator tests for missing item, extra item, wrong quantity, package semantic error, brand loss, attribute loss, aliases, and reordered items.
- Run pricing tests using fake usage and fake config prices.
- Run report generation from fixture results.
- Run CLI `--dry-run`.

Exit criteria:

- All local tests pass.
- Dry run prints planned providers, models, prompts, modes, cases, runs, API call count, and pricing config status.
- No API keys are printed.

### Pass 1 - Smoke

Purpose: verify provider adapters and output validation.

Scope:

```text
3 providers x 5 ВкусВилл cases x 1 run
```

Recommended smoke cases:

- simple list;
- package count;
- package size;
- dietary attribute;
- shop-name noise.

Exit criteria:

- Each configured provider returns at least one schema-valid response.
- Raw attempts, usage, latency, errors, and evaluated cases are written under `results/{run_id}/`.
- Any provider setup issue is classified as `AUTH_ERROR`, `HTTP_4XX`, `PROVIDER_ERROR`, or another defined error type.

### Pass 2 - DEV

Purpose: tune prompt choice and finalize ambiguity policies.

Scope:

```text
~50 ВкусВилл dev cases x candidate models x prompt variants x production/parity modes
```

Actions:

- Compare `parser_v1` vs `parser_short_v1` where provider supports both.
- Review failures by category.
- Freeze policies for `пару`, negation, substitutions, shop-name mentions, and repeated close products.
- Adjust dataset gold or prompt only before TEST.
- Record final prompt version and hash.

Exit criteria:

- Chosen prompt variant is fixed.
- Final provider/model configurations are fixed.
- Quality gate thresholds are either accepted from the base spec or changed before TEST with documented rationale.

### Pass 3 - Frozen TEST

Purpose: select production parser candidates using fixed data and fixed config.

Scope:

```text
~250 ВкусВилл test cases x final configurations x 1 run
```

Rules:

- Do not edit gold labels, prompt, schema, or pricing config during the run.
- Randomize provider order per case with a fixed seed.
- Save config snapshot, dataset hash, prompt hashes, model names, Python/package versions, git commit, timestamp, and random seed.

Exit criteria:

- `summary.csv`, `summary.json`, and `report.md` are generated.
- Each configuration is marked `Passes quality gate: YES/NO`.
- Rejected configurations include concrete failing metrics.

### Pass 4 - Stability

Purpose: measure repeated-run consistency on hard ВкусВилл cases.

Scope:

```text
30-50 hard cases x 3-5 runs x best 2-3 configurations
```

Metrics:

- `exact_match_rate_across_runs`
- `schema_valid_rate_across_runs`
- `output_variation_rate`
- `critical_error_any_run`

Exit criteria:

- Recommended primary and fallback do not have unacceptable instability on hard cases.
- Cases with repeated critical errors are added to the future regression dataset.

## Reporting Outputs

Each run must write:

```text
results/{run_id}/config_snapshot.yaml
results/{run_id}/env_metadata.json
results/{run_id}/dataset_hash.txt
results/{run_id}/prompt_hashes.json
results/{run_id}/raw_attempts.jsonl
results/{run_id}/evaluated_cases.jsonl
results/{run_id}/summary.csv
results/{run_id}/summary.json
results/{run_id}/report.md
results/{run_id}/errors.jsonl
```

The Markdown report must include:

- objective and dataset snapshot;
- provider/model/prompt/mode matrix;
- quality gate table;
- ВкусВилл category breakdown;
- first-attempt vs after-retry quality;
- reliability table;
- latency table;
- cost table with `null` where pricing is missing;
- top critical errors with case IDs;
- recommended primary;
- recommended fallback;
- rejected-by-quality-gate list;
- exact config, prompt hash, dataset hash, and run seed.

Summary table format:

| Provider | Model | Prompt | Mode | Schema valid | Item recall | Quantity | Package semantics | Exact order | Critical errors | Retry rate | p95 latency | Cost / 1k | Cost / 1k exact |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Risks

- ВкусВилл product names may look like brands, product lines, or shop noise. The dataset must distinguish explicit brand from ignored shop mention.
- User text may imply unavailable fields such as substitutions or exclusions. Keep these out of the main schema unless a deterministic policy is approved.
- Dietary attributes can be lost if the prompt normalizes too aggressively.
- Fat percent can be mistaken for quantity. This must be treated as a critical attribute error for dairy cases.
- Models may invent package count because grocery apps commonly default to one item. This is a critical parser error.
- Provider structured-output modes are not perfectly comparable. Use MODE A for production choice and MODE B for model-quality comparison.
- Current API capabilities and pricing may change. Verify official docs before implementation or live runs, then record the effective date in config.
- Retry can hide first-attempt instability. Report both first-attempt and after-retry metrics.
- Full TEST before DEV policy freeze can invalidate comparisons. Do not run frozen TEST until ambiguity policies and prompt hashes are fixed.

## Next Actions

1. Create ВкусВилл-focused `dev.jsonl` with 50 cases covering the categories above.
2. Manually review and freeze gold labels for DEV.
3. Add deterministic evaluator tests for shop-name noise, package semantics, percent attributes, and close repeated items.
4. Run Pass 0 local tests and `--dry-run`.
5. Configure `.env` model names and API keys locally without committing secrets.
6. Fill `benchmark_config.yaml` pricing fields from official pricing pages and set `effective_date`, or leave costs as `null`.
7. Run Pass 1 smoke with 5 cases.
8. Run Pass 2 DEV and choose the final prompt/config.
9. Freeze TEST dataset, prompt hash, schema, pricing config, and quality gates.
10. Run Pass 3 TEST, then Pass 4 stability for the best 2-3 configurations.
