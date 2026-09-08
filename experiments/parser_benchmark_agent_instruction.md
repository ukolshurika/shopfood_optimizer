# Инструкция для coding-агента: benchmark API для парсинга продуктового заказа

**Статус:** рабочая спецификация для реализации  
**Дата фиксации требований:** 2026-09-05  
**Проект:** Telegram-бот оптимизации продуктовой корзины с доставкой

## 1. Роль агента

Ты — coding-агент, который должен реализовать воспроизводимый benchmark парсинга пользовательского списка продуктов через несколько LLM API.

Нужно сравнить минимум три провайдера:

- OpenAI;
- Qwen / Alibaba Cloud Model Studio;
- DeepSeek.

Все API-ключи должны подставляться только через `.env`.

Результат работы агента — запускаемый Python-проект, который:

1. читает размеченный dataset;
2. отправляет одинаковые пользовательские запросы нескольким LLM;
3. получает структурированный результат;
4. валидирует его одной общей Pydantic/JSON Schema моделью;
5. сохраняет raw responses и usage каждого API;
6. сравнивает ответы с gold-разметкой;
7. считает метрики качества;
8. считает фактический расход токенов;
9. рассчитывает стоимость по конфигу тарифов;
10. измеряет latency и retry rate;
11. строит сводный CSV/JSON/Markdown report;
12. позволяет выбрать наиболее дешёвую модель, прошедшую quality gate.

Не выбирай победителя заранее.

## 2. Цель benchmark

Нужно ответить на вопрос:

> Какой API / модель наиболее эффективно превращает русскоязычный свободный список покупок в нашу структуру `ShoppingList`?

Под эффективностью понимается комбинация:

```text
качество
+
стоимость
+
latency
+
стабильность API
```

Главный принцип выбора:

```text
сначала пройти quality gate
↓
затем среди прошедших выбрать наиболее экономичный и стабильный вариант
```

Не оптимизировать только `tokens/request`.

У разных провайдеров разные токенизаторы, поэтому токены нельзя напрямую использовать как универсальную единицу стоимости между API.

Главные экономические метрики:

```text
USD / 1000 requests
USD / 1000 valid responses
USD / 1000 exact matches
USD / 1000 correct orders
```

## 3. Что парсер должен и не должен делать

LLM выполняет только extraction + normalization.

LLM НЕ должен:

- искать SKU в магазинах;
- выбирать конкретный товар;
- рассчитывать количество упаковок;
- подставлять одну упаковку, если количество отсутствует;
- оптимизировать корзину;
- определять магазин;
- вычислять стоимость.

Пример:

```text
творог
```

Корректно:

```json
{
  "product": "творог",
  "quantity_value": null,
  "quantity_unit": null,
  "package_count": null
}
```

Некорректно:

```json
{
  "product": "творог",
  "package_count": 1
}
```

Бизнес-дефолты применяются позже обычным кодом приложения.

## 4. Семантика количества

Парсер обязан различать физическое количество, количество упаковок и размер упаковки.

```text
"2 литра молока"
→ quantity_value=2
→ quantity_unit=l

"10 яиц"
→ quantity_value=10
→ quantity_unit=pcs

"2 молока"
→ package_count=2

"2 пачки творога по 180 г"
→ package_count=2
→ package_size_value=180
→ package_size_unit=g
```

`2 молока` НЕ должно автоматически превращаться в `2 литра`.

## 5. Целевая Pydantic-модель

Создай единую Pydantic-модель, которая применяется ко всем провайдерам.

```python
from pydantic import BaseModel, Field
from typing import Literal

MeasureUnit = Literal["g", "kg", "ml", "l", "pcs"]


class ProductAttribute(BaseModel):
    key: str
    value: str


class ShoppingItem(BaseModel):
    product: str
    brand: str | None = None

    quantity_value: float | None = None
    quantity_unit: MeasureUnit | None = None

    package_count: int | None = None

    package_size_value: float | None = None
    package_size_unit: MeasureUnit | None = None

    attributes: list[ProductAttribute] = Field(default_factory=list)


class ShoppingList(BaseModel):
    items: list[ShoppingItem]
```

Сгенерируй JSON Schema из этой модели и используй именно её как каноническую schema benchmark.

Не поддерживай отдельные бизнес-схемы для разных провайдеров.

## 6. Канонический prompt

Создай файл `prompts/parser_v1.md`:

```text
Ты — парсер списка продуктов.

Преобразуй пользовательский список покупок в структурированный JSON.

Извлекай только информацию, которую пользователь указал явно. Ничего не додумывай.

Правила:

1. Каждый самостоятельно запрошенный продукт должен присутствовать в items ровно один раз.

2. Нормализуй название до короткого общеупотребительного названия продукта на русском языке.

Примеры:
- «бананы», «бананов» → «банан»
- «яблоки», «яблок» → «яблоко»

3. Различай физическое количество продукта и количество упаковок.

Примеры:
- «молоко 2 литра» → quantity_value=2, quantity_unit="l"
- «3 кг бананов» → quantity_value=3, quantity_unit="kg"
- «10 яиц» → quantity_value=10, quantity_unit="pcs"
- «2 молока» → package_count=2
- «две бутылки молока» → package_count=2
- «2 пачки творога» → package_count=2

4. Если указан размер упаковки:
«2 пачки творога по 180 г»
→ package_count=2, package_size_value=180, package_size_unit="g"

5. Не рассчитывай количество упаковок самостоятельно.
«2 литра молока» НЕ означает две упаковки.

6. Если количество не указано, не предполагай одну упаковку. Оставь значения количества null.

7. Если бренд указан явно, сохрани его в brand.

8. Остальные явно указанные характеристики сохрани в attributes.

Примеры:
- «творог 5%» → key="fat_percent", value="5"
- «молоко безлактозное» → key="lactose_free", value="true"
- «яблоки голден» → key="variety", value="голден"
- «яйца С0» → key="category", value="C0"

9. Не добавляй отсутствующие в запросе товары или свойства.

10. Фразы «купи», «возьми», «мне нужно», «добавь», «пожалуйста» не являются частью названия товара.

11. Если информация отсутствует, используй null или пустой список вместо предположения.

Верни только JSON.
```

## 7. Короткий prompt для ablation test

Создай `prompts/parser_short_v1.md`:

```text
Ты — парсер списка продуктов.

Верни только структурированный JSON согласно переданной schema.

Извлекай только явно указанную информацию. Ничего не додумывай.

Различай:
- физическое количество: «2 л молока» → quantity;
- число упаковок: «2 молока» / «2 бутылки молока» → package_count;
- размер упаковки: «2 пачки по 180 г» → package_size.

Если количество не указано — оставь null.
Не рассчитывай число упаковок из физического количества.
Явный бренд сохрани в brand.
Другие явные характеристики сохрани в attributes.
Нормализуй название продукта и единицы измерения.
Не добавляй товары или характеристики, которых нет в запросе.
```

Цель — проверить, окупается ли более длинный prompt качеством.

## 8. Два режима benchmark

### MODE A — production

Использовать лучшую структурированную выдачу, реально доступную у каждого API.

Ориентир:

```text
OpenAI
→ JSON Schema / Structured Output

Qwen
→ JSON Schema, если выбранная модель поддерживает
→ иначе JSON Object

DeepSeek
→ JSON Object
→ Pydantic validation
```

Это главный benchmark для выбора production API.

### MODE B — parity

Использовать максимально сопоставимый режим:

```text
одинаковый prompt
+
JSON Object / prompt-enforced JSON
+
одинаковая Pydantic validation
```

Цель MODE B — отделить качество модели от constrained decoding / structured-output API.

Главный итоговый выбор делается по MODE A.

## 9. Актуальные особенности API

Перед реализацией перепроверь официальные docs.

На дату этой спецификации:

### OpenAI

Responses API поддерживает Structured Outputs через JSON Schema. Usage ответа содержит `input_tokens`, `output_tokens`, `total_tokens` и дополнительные token details, где применимо.

Документация:

```text
https://developers.openai.com/api/reference/resources/responses/methods/create
https://developers.openai.com/api/reference/resources/responses
```

### Qwen / Alibaba Cloud Model Studio

Model Studio предоставляет OpenAI-compatible API. Поддерживаются JSON Object и, для поддерживаемых моделей, JSON Schema с `strict=true`. Base URL зависит от региона / workspace.

Документация:

```text
https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope
https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output
```

### DeepSeek

Официальный DeepSeek API предоставляет OpenAI-compatible Chat Completions. JSON Output включается через `response_format={"type":"json_object"}`. В prompt должно присутствовать слово `JSON`. Пустой content в JSON mode должен учитываться как failure benchmark.

Документация:

```text
https://api-docs.deepseek.com/guides/json_mode/
```

## 10. `.env.example`

Создай:

```dotenv
# OpenAI
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_BASE_URL=https://api.openai.com/v1

# Qwen / Alibaba Cloud Model Studio
QWEN_API_KEY=
QWEN_MODEL=
QWEN_BASE_URL=
QWEN_RESPONSE_MODE=json_schema

# DeepSeek
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_RESPONSE_MODE=json_object

# Benchmark
BENCHMARK_CONCURRENCY=3
BENCHMARK_TIMEOUT_SECONDS=60
BENCHMARK_NETWORK_RETRIES=2
BENCHMARK_SCHEMA_RETRIES=1
```

Если Qwen требует workspace-specific URL, пользователь указывает полный `QWEN_BASE_URL`.

Никогда не выводи API keys в stdout, logs или reports.

## 11. `.gitignore`

```gitignore
.env
results/
__pycache__/
*.pyc
.venv/
```

## 12. Конфиг моделей и тарифов

Создай `benchmark_config.yaml`.

```yaml
benchmark:
  max_output_tokens: 500
  default_runs: 1
  stability_runs: 5
  timeout_seconds: 60

providers:
  openai:
    enabled: true
    model_env: OPENAI_MODEL
    prompt_variants:
      - parser_v1
      - parser_short_v1
    response_modes:
      production: json_schema
      parity: json_object
    pricing:
      currency: USD
      effective_date: "YYYY-MM-DD"
      input_per_1m: null
      cached_input_per_1m: null
      output_per_1m: null

  qwen:
    enabled: true
    model_env: QWEN_MODEL
    prompt_variants:
      - parser_v1
      - parser_short_v1
    response_modes:
      production: json_schema
      parity: json_object
    pricing:
      currency: USD
      effective_date: "YYYY-MM-DD"
      input_per_1m: null
      cached_input_per_1m: null
      output_per_1m: null

  deepseek:
    enabled: true
    model_env: DEEPSEEK_MODEL
    prompt_variants:
      - parser_v1
    response_modes:
      production: json_object
      parity: json_object
    pricing:
      currency: USD
      effective_date: "YYYY-MM-DD"
      input_per_1m: null
      cached_input_per_1m: null
      output_per_1m: null
```

Цены не хардкодить в Python.

Перед полным запуском:

1. открыть официальные pricing pages;
2. внести цены в YAML;
3. указать `effective_date`;
4. сохранить snapshot конфигурации рядом с результатами run.

Если точный cost вычислить нельзя, поле стоимости должно быть `null`.

## 13. Структура проекта

```text
parser-benchmark/
├── .env.example
├── .gitignore
├── README.md
├── benchmark_config.yaml
├── pyproject.toml
├── prompts/
│   ├── parser_v1.md
│   └── parser_short_v1.md
├── schemas/
│   └── shopping_list.schema.json
├── data/
│   ├── dev.jsonl
│   ├── test.jsonl
│   └── stability.jsonl
├── src/
│   └── benchmark/
│       ├── __init__.py
│       ├── models.py
│       ├── config.py
│       ├── dataset.py
│       ├── canonicalize.py
│       ├── evaluator.py
│       ├── pricing.py
│       ├── runner.py
│       ├── report.py
│       ├── cli.py
│       └── providers/
│           ├── base.py
│           ├── openai_provider.py
│           ├── qwen_provider.py
│           └── deepseek_provider.py
├── tests/
│   ├── test_evaluator.py
│   ├── test_canonicalize.py
│   ├── test_pricing.py
│   └── test_dataset.py
└── results/
```

## 14. Provider interface

Все API привести к одному интерфейсу.

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class Usage:
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None


@dataclass
class ProviderResult:
    provider: str
    model: str
    raw_text: str | None
    parsed_json: dict[str, Any] | None
    usage: Usage
    latency_ms: float
    http_status: int | None
    response_id: str | None
    error_type: str | None
    error_message: str | None
    attempt: int


class Provider:
    async def parse(
        self,
        *,
        system_prompt: str,
        user_text: str,
        schema: dict,
        response_mode: str,
    ) -> ProviderResult:
        ...
```

Вся provider-specific логика должна находиться внутри адаптера.

`runner.py` не должен знать детали API.

## 15. Нормализация usage

Провайдеры могут называть поля по-разному. Привести их к:

```text
input_tokens
cached_input_tokens
output_tokens
reasoning_tokens
total_tokens
```

Если значение отсутствует — `null`.

Не вычислять неизвестные поля предположительно.

Сохранять оригинальный usage object в raw response.

## 16. Dataset format

Каждая строка JSONL — один кейс.

```json
{
  "id": "simple_001",
  "category": "simple",
  "input": "бананы 3 кг, яблоки 1 кг, творог, молоко 2 литра",
  "gold": {
    "items": [
      {
        "product": "банан",
        "brand": null,
        "quantity_value": 3,
        "quantity_unit": "kg",
        "package_count": null,
        "package_size_value": null,
        "package_size_unit": null,
        "attributes": []
      }
    ]
  }
}
```

## 17. Accepted aliases

Dataset может содержать evaluator-only metadata:

```json
{
  "product": "куриная грудка",
  "accepted_product_names": [
    "куриная грудка",
    "грудка куриная",
    "грудка курицы"
  ]
}
```

`accepted_product_names` не входит в ShoppingList schema и не передаётся модели.

## 18. Категории TEST dataset

Цель — около 250 кейсов.

| Категория | Количество |
|---|---:|
| Простые списки | 35 |
| Разговорная форма | 35 |
| кг / г / л / мл / шт | 30 |
| Пачки / бутылки / упаковки | 25 |
| Размер упаковки «по N г/мл» | 20 |
| Свойства: жирность / сорт / тип | 25 |
| Бренды | 15 |
| Опечатки / падежи / разговорные слова | 20 |
| Неоднозначные формулировки | 20 |
| Шум / лишний текст | 15 |
| Повторяющиеся или близкие товары | 10 |

## 19. DEV / TEST / STABILITY

`dev.jsonl`: около 50 кейсов. Можно менять prompt по результатам.

`test.jsonl`: около 250 кейсов. После утверждения gold замораживается.

`stability.jsonl`: 30–50 сложных кейсов, каждый прогоняется 3–5 раз.

## 20. Неоднозначные кейсы

Для каждой неоднозначной конструкции заранее определить policy.

Например:

```text
"пару молока"
```

Если политика проекта:

```text
package_count=2
```

это фиксируется в gold до финального benchmark.

Не менять policy между моделями.

## 21. Canonicalization

Перед evaluation допустима только deterministic normalization:

```text
trim whitespace
lowercase
ё → е
1.0 == 1
attributes sorted by key/value
unit aliases normalized
```

Не использовать вторую LLM для исправления или оценки результата.

## 22. Сопоставление items

Порядок items не должен влиять на score.

Рекомендуемый алгоритм:

1. match по canonical `product`;
2. match по `accepted_product_names`;
3. для повторяющихся продуктов максимизировать совпадение остальных полей;
4. при необходимости использовать deterministic bipartite/Hungarian matching.

LLM judge не использовать.

## 23. Метрики качества

Считать минимум:

```text
schema_valid_rate
item_precision
item_recall
product_name_accuracy
quantity_value_accuracy
quantity_unit_accuracy
package_count_accuracy
package_size_accuracy
package_semantics_accuracy
brand_precision
brand_recall
attribute_precision
attribute_recall
attribute_f1
whole_order_exact_match
critical_error_rate
```

## 24. Whole Order Exact Match

`whole_order_exact_match=true` только если после canonicalization:

- нет потерянных товаров;
- нет лишних товаров;
- product корректен;
- количество и единицы корректны;
- package semantics корректна;
- brand корректен;
- attributes корректны.

## 25. Critical errors

Критические ошибки:

```text
missing_item
extra_item
wrong_quantity
wrong_quantity_unit
physical_quantity_converted_to_package_count
package_count_converted_to_physical_quantity
invented_brand
lost_explicit_brand
lost_critical_attribute
invented_product
```

## 26. Рабочий Quality Gate

```text
schema_valid_rate              >= 99.5%
item_recall                    >= 99.0%
item_precision                 >= 99.0%
quantity_value_accuracy        >= 98.5%
quantity_unit_accuracy         >= 98.5%
package_semantics_accuracy     >= 99.0%
critical_error_rate            <= 0.5%
whole_order_exact_match        >= 95.0%
```

Пороги можно скорректировать после DEV, но ДО финального TEST.

## 27. API reliability metrics

Считать:

```text
request_count
successful_http_requests
http_error_rate
timeout_rate
empty_response_rate
invalid_json_rate
schema_validation_failure_rate
network_retry_rate
schema_retry_rate
final_failure_rate
```

Показывать отдельно:

```text
first_attempt_quality
production_quality_after_retry
```

## 28. Retry policy

Network retry допустим для timeout, connection errors, 429 и выбранных 5xx. Использовать bounded exponential backoff.

Schema retry допустим максимум один раз для empty response, invalid JSON или schema failure.

Первый failure сохраняется. Retry считается отдельным API-вызовом; его токены и latency входят в production cost.

## 29. Latency

На каждый attempt:

```text
started_at
finished_at
latency_ms
```

На case:

```text
end_to_end_latency_ms
```

Агрегаты:

```text
mean
p50
p90
p95
p99
```

## 30. Порядок вызовов

Не прогонять провайдеры большими последовательными блоками.

Для каждого case рандомизировать порядок провайдеров с фиксированным seed и сохранять seed в metadata.

## 31. Concurrency

По умолчанию concurrency = 3.

Не использовать benchmark как load test. Уважать 429, Retry-After и rate limits.

## 32. Generation parameters

Если поддерживается — использовать `temperature=0`.

Не включать web, tools, retrieval.

Reasoning/high-thinking отключать или минимизировать там, где это официально поддерживается.

Фактические параметры сохранять в metadata.

## 33. Max output

Ориентир — около 500 output tokens либо адекватный лимит для тестовых заказов.

Обрезанный ответ считается failure.

## 34. Raw result format

Каждый API attempt сохранять отдельной JSONL-записью с:

```text
run_id
case_id
dataset
provider
model
prompt_version
response_mode
attempt
request_params
started_at
finished_at
latency_ms
http_status
response_id
raw_text
parsed_json
json_valid
schema_valid
usage
pricing
error
```

API key не сохранять.

## 35. Evaluated result

Для каждого case/configuration сохранять:

```text
exact_match
critical_error
item_precision
item_recall
quantity_accuracy
package_semantics_accuracy
attribute_f1
total_attempts
total_cost_usd
end_to_end_latency_ms
```

## 36. Расчёт стоимости

Базовая формула:

```text
input_cost =
  non_cached_input_tokens / 1_000_000 * input_price_per_1m

cached_cost =
  cached_input_tokens / 1_000_000 * cached_input_price_per_1m

output_cost =
  output_tokens / 1_000_000 * output_price_per_1m

request_cost =
  input_cost + cached_cost + output_cost
```

Все retry складываются.

Если exact pricing model провайдера сложнее, реализовать отдельную pricing strategy и явно зафиксировать её в config/report.

## 37. Экономические агрегаты

Для каждой комбинации provider + model + prompt + mode:

```text
total_cost_usd
mean_cost_per_order
p50_cost_per_order
p95_cost_per_order
cost_per_1k_orders
cost_per_100k_orders
cost_per_1k_valid_orders
cost_per_1k_exact_matches
```

Главная метрика цены качества:

```text
cost_per_1k_exact_matches
```

## 38. Token metrics

Считать:

```text
mean/p50/p95 input_tokens
mean/p50/p95 output_tokens
mean/p50/p95 total_tokens
```

Если доступны — отдельно cached и reasoning tokens.

## 39. Stability benchmark

Для hard cases выполнить 3–5 повторов.

Считать:

```text
exact_match_rate_across_runs
schema_valid_rate_across_runs
output_variation_rate
critical_error_any_run
```

## 40. Prompt benchmark

На DEV сравнить `parser_v1` и `parser_short_v1`.

Если качество сопоставимо, предпочесть короткий prompt.

После выбора зафиксировать version/hash prompt.

## 41. Порядок эксперимента

### Pass 0 — local tests

Без API проверить schema, dataset loader, evaluator, pricing и reports.

### Pass 1 — smoke

```text
3 providers × 5 cases × 1 run
```

### Pass 2 — DEV

Около 50 cases × кандидатные модели × prompt variants.

### Pass 3 — frozen TEST

Около 250 cases × финальные конфигурации.

### Pass 4 — stability

30–50 hard cases × 3–5 runs × лучшие 2–3 конфигурации.

## 42. Dry run

CLI обязан иметь `--dry-run`.

Он показывает:

```text
dataset
cases
providers
models
prompts
runs
planned API calls
pricing config status
```

и не вызывает API.

## 43. CLI limits

Добавить:

```text
--limit N
--providers
--models
--prompts
--runs
--concurrency
--mode
```

Пример:

```bash
python -m benchmark.cli run   --dataset data/dev.jsonl   --providers openai,qwen,deepseek   --limit 10   --runs 1   --mode production
```

## 44. Resume

Поддержать:

```text
--resume RUN_ID
```

Не повторять уже успешно выполненный case/configuration/run без `--force`.

## 45. Results directory

Каждый запуск:

```text
results/{run_id}/
```

Содержимое:

```text
config_snapshot.yaml
env_metadata.json
dataset_hash.txt
prompt_hashes.json
raw_attempts.jsonl
evaluated_cases.jsonl
summary.csv
summary.json
report.md
errors.jsonl
```

`env_metadata.json` не содержит секретов.

## 46. Reproducibility

Сохранять:

```text
dataset SHA-256
prompt SHA-256
config snapshot
model names
Python version
package versions
git commit
timestamp
random seed
```

## 47. Итоговая таблица

`summary.csv` и `report.md` должны содержать:

| Provider | Model | Prompt | Mode | Schema valid | Item recall | Quantity | Package semantics | Exact order | Critical errors | Retry rate | p95 latency | Cost / 1k | Cost / 1k exact |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

Также:

```text
Passes quality gate: YES / NO
```

## 48. Winner selection

### Step 1

Исключить конфигурации, не прошедшие Quality Gate.

### Step 2

Среди прошедших сортировать прежде всего по:

```text
cost_per_1k_exact_matches ASC
```

### Step 3

При близкой стоимости учитывать:

```text
critical_error_rate ASC
p95_latency ASC
retry_rate ASC
operational complexity ASC
```

В отчёте вывести:

```text
Recommended primary
Recommended fallback
Rejected by quality gate
```

Победитель не должен быть захардкожен.

## 49. First-attempt vs production score

Обязательно показывать и raw first-attempt reliability, и итог после retry.

Модель, которой часто нужен retry, не эквивалентна модели с тем же итоговым качеством без retry.

## 50. Ошибки

Классифицировать:

```text
AUTH_ERROR
RATE_LIMIT
TIMEOUT
NETWORK_ERROR
HTTP_4XX
HTTP_5XX
EMPTY_RESPONSE
INVALID_JSON
SCHEMA_ERROR
TRUNCATED
PROVIDER_ERROR
UNKNOWN_ERROR
```

Failed cases не терять.

## 51. Tests benchmark-проекта

Unit tests минимум для:

- Pydantic schema;
- canonicalization;
- evaluator exact match;
- missing/extra item;
- wrong quantity/unit;
- package semantic error;
- aliases;
- reordered items;
- pricing;
- retry cost;
- malformed JSONL;
- duplicate case IDs.

## 52. Не использовать LLM judge

Основной benchmark должен быть deterministic.

Не использовать одну LLM для оценки другой.

LLM judge можно добавить позже только как отдельный exploratory metric.

## 53. Секреты

Обязательно:

```text
.env не коммитить
API keys не логировать
Authorization headers не сохранять
ключи не помещать в report
```

## 54. README

README должен объяснять:

1. установку;
2. Python version;
3. `cp .env.example .env`;
4. заполнение ключей и model names;
5. Qwen base URL;
6. pricing config;
7. dry run;
8. smoke;
9. DEV;
10. TEST;
11. stability;
12. расположение результатов;
13. интерпретацию quality gate.

## 55. Зависимости

Минимально:

```text
python-dotenv
pydantic
httpx
openai
PyYAML
```

Дополнительные библиотеки добавлять только при необходимости.

Версии закрепить после smoke-run.

## 56. Provider implementation guidance

### OpenAI

Использовать официальный OpenAI SDK. Для production structured output предпочтителен Responses API + JSON Schema.

### Qwen

Предпочтительно использовать OpenAI-compatible API.

```text
key = QWEN_API_KEY
base_url = QWEN_BASE_URL
model = QWEN_MODEL
```

Использовать JSON Schema, если выбранная модель поддерживает её. Иначе явно переключаться на `json_object` и записывать фактический mode в report.

### DeepSeek

Использовать OpenAI-compatible client.

```text
key = DEEPSEEK_API_KEY
base_url = DEEPSEEK_BASE_URL
model = DEEPSEEK_MODEL
```

Для JSON Output использовать:

```python
response_format={"type": "json_object"}
```

Обрабатывать empty content и schema mismatch как измеряемые failures.

## 57. Никаких provider-specific semantic prompt hacks

Финальный semantic prompt одинаков между провайдерами.

Допустимы только технические различия API.

Provider-tuned prompt можно тестировать только как отдельную именованную конфигурацию.

## 58. Acceptance criteria

Работа coding-агента завершена, когда:

- [ ] проект запускается локально;
- [ ] `.env.example` создан;
- [ ] секреты не сохраняются;
- [ ] есть OpenAI adapter;
- [ ] есть Qwen adapter;
- [ ] есть DeepSeek adapter;
- [ ] единая Pydantic schema;
- [ ] production/parity modes;
- [ ] `--dry-run`;
- [ ] `--limit`;
- [ ] `--resume`;
- [ ] raw results;
- [ ] usage и latency;
- [ ] cost из config;
- [ ] retry входит в cost;
- [ ] deterministic evaluator;
- [ ] critical errors;
- [ ] whole-order exact match;
- [ ] quality gate;
- [ ] CSV + JSON + Markdown report;
- [ ] unit tests;
- [ ] README;
- [ ] smoke test минимум по одному кейсу для каждого настроенного провайдера.

## 59. Первый запуск после реализации

```text
1. pytest
2. dry-run
3. 1 case × 3 providers
4. 5 cases × 3 providers
5. 50 DEV
6. ручной разбор ошибок
7. фиксация prompt/config
8. frozen TEST
9. stability
```

Не запускать сразу полный benchmark.

## 60. Ожидаемый итог

Нужен воспроизводимый результат вида:

```text
Configuration A
Quality gate: PASS
Whole-order exact: 98.4%
Critical errors: 0.2%
p95 latency: 820 ms
Cost / 1000 orders: $X
Cost / 1000 exact orders: $Y

Configuration B
Quality gate: FAIL
Whole-order exact: 93.2%
Critical errors: 1.4%
Cost / 1000 orders: $Z

Configuration C
Quality gate: PASS
Whole-order exact: 97.8%
Critical errors: 0.3%
p95 latency: 640 ms
Cost / 1000 exact orders: $W
```

После этого основной parser выбирается на основании измерений.

## 61. После benchmark

После выбора primary parser:

```text
Telegram user text
    ↓
Primary LLM parser
    ↓
Pydantic validation
    ↓
deterministic normalization
    ↓
ShoppingList
```

Benchmark-проект оставить в репозитории и перезапускать при смене модели, prompt, schema, провайдера, тарифов или при накоплении новых реальных пользовательских формулировок.
