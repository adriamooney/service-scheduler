"""Unit tests for quote_engine: tiers, modifiers, truck fraction."""

from __future__ import annotations

import pytest

from src.sms_webhook.quote_engine import (
    Quote,
    QuoteItem,
    QuoteModifiers,
    compute_quote,
    TIER_RANGES,
    TRUCK_CUBIC_YARDS,
)


def test_empty_items_returns_small_placeholder():
    q = compute_quote([])
    assert q.tier == "Small"
    assert q.amount_min_cents == 5000  # $50
    assert q.amount_max_cents == 10000  # $100
    assert q.est_truck_fraction == 0.0


def test_single_medium_item():
    items = [QuoteItem(name="couch", category="Medium", quantity=1, est_cubic_yards=3.0)]
    q = compute_quote(items)
    assert q.tier == "Medium"
    assert q.amount_min_cents == 10000  # $100
    assert q.amount_max_cents == 25000  # $250
    assert q.est_truck_fraction == 3.0 / TRUCK_CUBIC_YARDS


def test_volume_drives_tier():
    # 1 cu yd -> Small
    q = compute_quote([QuoteItem("chair", "Small", 1, 1.0)])
    assert q.tier == "Small"

    # 4 cu yd -> Medium
    q = compute_quote([QuoteItem("couch", "Medium", 1, 4.0)])
    assert q.tier == "Medium"

    # 7 cu yd -> Large
    q = compute_quote([QuoteItem("room", "Large", 1, 7.0)])
    assert q.tier == "Large"

    # 10 cu yd -> XL
    q = compute_quote([QuoteItem("garage", "XL", 1, 10.0)])
    assert q.tier == "XL"


def test_modifiers_stairs():
    items = [QuoteItem("couch", "Medium", 1, 3.0)]
    mods = QuoteModifiers(stairs_flights=2)
    q = compute_quote(items, mods)
    # Base Medium $100–$250 + 2 * $37.50 = $75
    assert q.amount_min_cents == 17500  # $175
    assert q.amount_max_cents == 32500  # $325


def test_modifiers_inside_carry():
    items = [QuoteItem("mattress", "Medium", 1, 3.0)]  # 3 cu yd -> Medium tier
    mods = QuoteModifiers(inside_carry=True)
    q = compute_quote(items, mods)
    assert q.amount_min_cents == 12500   # $100 + $25
    assert q.amount_max_cents == 27500   # $250 + $25


def test_modifiers_hazardous():
    items = [QuoteItem("paint cans", "Small", 1, 0.5)]
    mods = QuoteModifiers(hazardous_count=2)
    q = compute_quote(items, mods)
    # $50–$100 + 2 * $52.50 = $105
    assert q.amount_min_cents == 15500   # $155
    assert q.amount_max_cents == 20500   # $205


def test_modifiers_same_day():
    items = [QuoteItem("chair", "Small", 1, 1.0)]
    mods = QuoteModifiers(same_day=True)
    q = compute_quote(items, mods)
    assert q.amount_min_cents == 6000   # $50 * 1.2
    assert q.amount_max_cents == 12000  # $100 * 1.2


def test_modifiers_curbside():
    items = [QuoteItem("couch", "Medium", 1, 3.0)]
    mods = QuoteModifiers(curbside=True)
    q = compute_quote(items, mods)
    assert q.amount_min_cents == 9000   # $100 * 0.9
    assert q.amount_max_cents == 22500  # $250 * 0.9


def test_modifiers_combined():
    items = [QuoteItem("couch", "Medium", 1, 3.0)]
    mods = QuoteModifiers(stairs_flights=1, same_day=True)
    q = compute_quote(items, mods)
    # ($100 + $37.50) * 1.2 = $165, ($250 + $37.50) * 1.2 = $345
    assert q.amount_min_cents == 16500
    assert q.amount_max_cents == 34500


def test_dict_items_accepted():
    items = [
        {"name": "couch", "category": "Medium", "quantity": 1, "est_cubic_yards": 3.0},
    ]
    q = compute_quote(items)
    assert q.tier == "Medium"
    assert q.amount_min_cents == 10000


def test_quote_to_dict():
    q = Quote(amount_min_cents=15000, amount_max_cents=22500, tier="Medium", est_truck_fraction=0.25)
    d = q.to_dict()
    assert d["amount_min"] == 150.0
    assert d["amount_max"] == 225.0
    assert d["tier"] == "Medium"
    assert d["est_truck_fraction"] == 0.25
    assert d["currency"] == "USD"


def test_truck_fraction_capped_at_one():
    items = [QuoteItem("estate", "XL", 1, 20.0)]
    q = compute_quote(items)
    assert q.est_truck_fraction == 1.0
