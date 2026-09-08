# Parser Benchmark

Локальный benchmark для сравнения LLM API, которые парсят русскоязычные списки продуктов в каноническую `ShoppingList` schema.

Текущая матрица:

- `qwen` и `qwen_strong` через Yandex AI Studio OpenAI-compatible API;
- `yandexgpt_lite` и `yandexgpt_pro` через Yandex AI Studio OpenAI-compatible API;
- `deepseek` через OpenAI-compatible Chat Completions и `deepseek_pro` через Responses API;
- `gigachat_freemium` через GigaChat API;
- `openai_control` включен в плане, но запускается только при заполненных `OPENAI_*` env.

Реализовано:

- Pydantic-модель и JSON Schema;
- prompt variants `parser_v1` и `parser_short_v1`;
- JSONL dataset loader с проверкой duplicate IDs;
- canonicalization и evaluator;
- pricing calculator из `benchmark_config.yaml`;
- dry-run CLI без API-вызовов;
- live runner с raw attempts и latency;
- fixture report generation.

## Быстрый запуск

```bash
cd parser-benchmark
pytest
PYTHONPATH=src python3 -m benchmark.cli dry-run --dataset data/dev.jsonl
PYTHONPATH=src python3 -m benchmark.cli evaluate-fixture --dataset data/dev.jsonl
```

## Yandex AI Studio

`.env` должен содержать:

```dotenv
YANDEX_API_KEY=
YANDEX_FOLDER_ID=
YANDEX_BASE_URL=https://ai.api.cloud.yandex.net/v1
YANDEX_QWEN_MODEL=gpt://<folder_ID>/qwen3.6-35b-a3b
YANDEX_QWEN_STRONG_MODEL=gpt://<folder_ID>/qwen3-235b-a22b-fp8/latest
YANDEXGPT_LITE_MODEL=gpt://<folder_ID>/yandexgpt-5-lite
YANDEXGPT_PRO_MODEL=gpt://<folder_ID>/yandexgpt/latest
```

Yandex AI Studio использует OpenAI-compatible `/chat/completions`, заголовок `Authorization: Api-Key ...` и `OpenAI-Project: <folder_ID>`. YandexGPT Lite 5 задается URI `gpt://<folder_ID>/yandexgpt-5-lite`, а Pro подключается через `YANDEXGPT_PRO_MODEL`. Для `qwen_strong` используется URI `gpt://<folder_ID>/qwen3-235b-a22b-fp8/latest`.

## Live API

API-ключи и модели задаются только через `.env`/environment. Цены не хардкодятся в Python: заполните pricing-поля в `benchmark_config.yaml` по актуальным официальным страницам перед платным запуском.

```bash
PYTHONPATH=src python3 -m benchmark.cli run --dataset data/dev.jsonl --limit 5 --out results/smoke
```

## GigaChat Freemium

GigaChat Freemium добавлен как `gigachat_freemium`. Это режим для физлиц и личного некоммерческого тестирования; для production Telegram-бота нужен платный пакет или корпоративный режим.

`.env` должен содержать:

```dotenv
GIGACHAT_CREDENTIALS=<authorization key из личного кабинета>
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_BASE_URL=https://api.giga.chat/v1
GIGACHAT_OAUTH_URL=https://ngw.devices.sberbank.ru:9443/api/v2/oauth
GIGACHAT_MODEL=GigaChat-2
GIGACHAT_VERIFY_SSL=true
```

Freemium cost в `benchmark_config.yaml` указан как `0.0`, потому что расходы идут из бесплатной квоты. При сравнении с платными провайдерами это нужно читать как `quota_cost`, а не как постоянную production-цену.

Smoke:

```bash
PYTHONPATH=src python3 -m benchmark.cli run --dataset data/dev.jsonl --limit 5 --out results/gigachat_freemium_smoke
```
