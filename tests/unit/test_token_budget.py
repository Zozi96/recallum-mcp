"""Deterministic token estimator and packing helpers."""

from __future__ import annotations

import math

import pytest

from recallum.memory import MemoryValidationError
from recallum.memory.token_budget import (
    TOKEN_HIT_OVERHEAD,
    estimate_tokens,
    pack_by_token_budget,
    reorder_by_strategy,
    validate_strategy,
)


def test_estimate_tokens_empty_content_is_overhead_only():
    assert estimate_tokens("") == TOKEN_HIT_OVERHEAD


def test_estimate_tokens_short_content():
    # Three chars → ceil(3/4)=1 plus overhead.
    assert estimate_tokens("abc") == 1 + TOKEN_HIT_OVERHEAD


def test_estimate_tokens_crosses_ceil_threshold():
    four = "abcd"
    five = "abcde"
    assert estimate_tokens(four) == math.ceil(4 / 4) + TOKEN_HIT_OVERHEAD
    assert estimate_tokens(five) == math.ceil(5 / 4) + TOKEN_HIT_OVERHEAD
    assert estimate_tokens(five) == estimate_tokens(four) + 1


def test_validate_strategy_rejects_unknown_before_any_use():
    with pytest.raises(MemoryValidationError, match="unknown strategy 'nope'"):
        validate_strategy("nope")


def test_reorder_by_strategy_debugging_puts_facts_before_preferences():
    items = [("preference", "p"), ("fact", "f"), ("preference", "p2"), ("fact", "f2")]
    ordered = reorder_by_strategy(
        items, "debugging", category_of=lambda item: item[0]
    )
    assert [item[0] for item in ordered] == ["fact", "fact", "preference", "preference"]
    assert [item[1] for item in ordered] == ["f", "f2", "p", "p2"]


def test_pack_by_token_budget_stops_before_overflow():
    items = ["aa", "bbbb", "cc"]
    # Each "aa" costs ceil(2/4)+8 = 9; budget 18 keeps two, not three.
    kept = pack_by_token_budget(
        items, max_items=10, max_tokens=18, content_of=lambda text: text
    )
    assert kept == ["aa", "bbbb"]
