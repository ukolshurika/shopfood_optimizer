from benchmark.pricing import Usage, calculate_cost_usd


def test_missing_pricing_returns_none():
    assert calculate_cost_usd(Usage(input_tokens=100, output_tokens=50), {"input_per_1m": None}) is None


def test_cost_uses_configured_prices():
    cost = calculate_cost_usd(
        Usage(input_tokens=1_000_000, output_tokens=500_000),
        {"input_per_1m": 2.0, "cached_input_per_1m": None, "output_per_1m": 10.0},
    )
    assert cost == 7.0


def test_cached_input_requires_cached_price():
    cost = calculate_cost_usd(
        Usage(input_tokens=1000, cached_input_tokens=100, output_tokens=100),
        {"input_per_1m": 2.0, "cached_input_per_1m": None, "output_per_1m": 10.0},
    )
    assert cost is None
