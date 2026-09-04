"""What a turn cost, in dollars.

A price list goes stale, so an unknown model returns `None` and the UI renders
a dash: a plausible figure from the wrong model's prices is indistinguishable
from a right one until someone reconciles the invoice.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    """USD per 1M tokens.

    `cache_write` is storing a prefix, `cached_input` is re-reading it. Most
    OpenAI models bill a write as ordinary input and leave it None.
    """

    input: float
    cached_input: float
    output: float
    cache_write: float | None = None

    @property
    def write(self) -> float:
        return self.input if self.cache_write is None else self.cache_write


# Matched by longest prefix *on a hyphen boundary*: dated aliases
# ("gpt-4.1-2025-04-14") must resolve to their floating name, while a bare
# startswith would also match "gpt-5" to "gpt-5.6-terra".
PRICES: dict[str, Price] = {
    "gpt-4.1-nano": Price(0.10, 0.025, 0.40),
    "gpt-4.1-mini": Price(0.40, 0.10, 1.60),
    "gpt-4.1": Price(2.00, 0.50, 8.00),
    "gpt-4o-mini": Price(0.15, 0.075, 0.60),
    "gpt-4o": Price(2.50, 1.25, 10.00),
    "gpt-5-nano": Price(0.05, 0.005, 0.40),
    "gpt-5-mini": Price(0.25, 0.025, 2.00),
    "gpt-5": Price(1.25, 0.125, 10.00),
    "gpt-5.6-terra": Price(2.00, 0.20, 12.00, cache_write=2.50),
    "o4-mini": Price(1.10, 0.275, 4.40),
    "o3-mini": Price(1.10, 0.55, 4.40),
    "o3": Price(2.00, 0.50, 8.00),
}


def price_for(model: str, table: dict[str, Price] | None = None) -> Price | None:
    prices = PRICES if table is None else table
    best = ""
    for name in prices:
        if len(name) <= len(best):
            continue
        if model == name or model.startswith(f"{name}-"):
            best = name
    return prices[best] if best else None


def cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    table: dict[str, Price] | None = None,
) -> float | None:
    """Estimated spend for one turn, or None if the model is not priced.

    `prompt_tokens` is the *whole* input count; `cached_tokens` and
    `cache_write_tokens` are parts of it, each billed at its own rate.
    """
    price = price_for(model, table)
    if price is None:
        return None
    total = max(prompt_tokens, 0)
    # provider-reported; clamp so the parts cannot exceed the total
    cached = min(max(cached_tokens, 0), total)
    written = min(max(cache_write_tokens, 0), total - cached)
    fresh = total - cached - written
    return (
        fresh * price.input
        + cached * price.cached_input
        + written * price.write
        + max(completion_tokens, 0) * price.output
    ) / 1_000_000


def parse_prices(value: str) -> dict[str, Price]:
    """Parse `MODEL_PRICES="model=in/cached/out[/write],..."`.

    Shorter forms are accepted because not every provider has every rate.
    """
    table: dict[str, Price] = {}
    for entry in value.split(","):
        model, _, rates = entry.strip().partition("=")
        model = model.strip()
        if not model or not rates:
            continue
        parts = [float(part) for part in rates.split("/")]
        if len(parts) == 4:
            table[model] = Price(parts[0], parts[1], parts[2], cache_write=parts[3])
        elif len(parts) == 3:
            table[model] = Price(parts[0], parts[1], parts[2])
        elif len(parts) == 2:
            table[model] = Price(parts[0], parts[0], parts[1])
        else:
            raise ValueError(
                f"{model!r}: expected 'input/cached/output[/cache_write]' or "
                f"'input/output', got {rates!r}"
            )
    return table


__all__ = ["PRICES", "Price", "cost_usd", "parse_prices", "price_for"]
