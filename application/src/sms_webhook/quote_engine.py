"""Quote engine: tier-based pricing, modifiers, and truck fraction for junk removal."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TRUCK_CUBIC_YARDS = 12.0

# Tier names and base price ranges (min, max) in dollars
TIER_RANGES: dict[str, tuple[float, float]] = {
    "Small": (50.0, 100.0),   # Single item, light
    "Medium": (100.0, 250.0),  # A few items or one large
    "Large": (250.0, 450.0),   # Partial truckload
    "XL": (450.0, 800.0),     # Full or near-full truckload
}

# Volume (cubic yards) thresholds to assign tier from total volume
VOLUME_TO_TIER = [
    (2.0, "Small"),
    (5.0, "Medium"),
    (9.0, "Large"),
    (float("inf"), "XL"),
]


@dataclass
class QuoteItem:
    """Single line item for quote (name, tier, quantity, estimated cubic yards)."""
    name: str
    category: str  # e.g. "Small", "Medium", "Large", "XL"
    quantity: int = 1
    est_cubic_yards: float = 0.0


@dataclass
class QuoteModifiers:
    """Pricing modifiers from job conditions."""
    stairs_flights: int = 0           # +$25–$50 per flight (we use $37.50 midpoint)
    inside_carry: bool = False       # +$25
    hazardous_count: int = 0         # +$30–$75 per item (we use $52.50 midpoint)
    same_day: bool = False           # +20%
    curbside: bool = False           # −10% (no carry from inside)


@dataclass
class Quote:
    """Structured quote result (prices in cents for precision)."""
    amount_min_cents: int
    amount_max_cents: int
    tier: str
    est_truck_fraction: float
    currency: str = "USD"

    def amount_min_dollars(self) -> float:
        return self.amount_min_cents / 100.0

    def amount_max_dollars(self) -> float:
        return self.amount_max_cents / 100.0

    def to_dict(self) -> dict[str, Any]:
        """For storing in DynamoDB / passing to LLM (dollars for readability)."""
        return {
            "amount_min": self.amount_min_dollars(),
            "amount_max": self.amount_max_dollars(),
            "tier": self.tier,
            "est_truck_fraction": round(self.est_truck_fraction, 2),
            "currency": self.currency,
        }


def _volume_to_tier(total_cubic_yards: float) -> str:
    """Map total estimated volume to a single tier."""
    for threshold, tier in VOLUME_TO_TIER:
        if total_cubic_yards <= threshold:
            return tier
    return "XL"


def compute_quote(items: list[QuoteItem] | list[dict[str, Any]], modifiers: QuoteModifiers | None = None) -> Quote:
    """
    Compute a quote from structured items and optional modifiers.

    Items can be QuoteItem instances or dicts with keys: name, category, quantity (default 1),
    est_cubic_yards (default 0). Category should be one of Small, Medium, Large, XL.
    """
    if modifiers is None:
        modifiers = QuoteModifiers()

    # Normalize to QuoteItem list
    normalized: list[QuoteItem] = []
    for it in items:
        if isinstance(it, QuoteItem):
            normalized.append(it)
        else:
            d = dict(it)
            normalized.append(QuoteItem(
                name=d.get("name", "Item"),
                category=d.get("category", "Medium"),
                quantity=int(d.get("quantity", 1)),
                est_cubic_yards=float(d.get("est_cubic_yards", 0)),
            ))

    if not normalized:
        # No items: return a minimal Small placeholder
        tier = "Small"
        total_volume = 0.0
        base_min, base_max = TIER_RANGES["Small"]
    else:
        total_volume = sum(it.est_cubic_yards * it.quantity for it in normalized)
        tier = _volume_to_tier(total_volume)
        base_min, base_max = TIER_RANGES.get(tier, TIER_RANGES["Medium"])

    est_truck_fraction = total_volume / TRUCK_CUBIC_YARDS if TRUCK_CUBIC_YARDS else 0.0
    est_truck_fraction = min(est_truck_fraction, 1.0)  # cap at 1 truck

    # Base price in dollars, then apply flat modifiers
    subtotal_min = base_min
    subtotal_max = base_max

    # Stairs: +$37.50 per flight (midpoint of $25–$50)
    stairs_add = 37.50 * modifiers.stairs_flights
    subtotal_min += stairs_add
    subtotal_max += stairs_add

    # Inside carry: +$25
    if modifiers.inside_carry:
        subtotal_min += 25.0
        subtotal_max += 25.0

    # Hazardous: +$52.50 per item (midpoint of $30–$75)
    hazardous_add = 52.50 * modifiers.hazardous_count
    subtotal_min += hazardous_add
    subtotal_max += hazardous_add

    # Percentage modifiers (apply after flat)
    if modifiers.same_day:
        subtotal_min *= 1.20
        subtotal_max *= 1.20
    if modifiers.curbside:
        subtotal_min *= 0.90
        subtotal_max *= 0.90

    amount_min_cents = int(round(subtotal_min * 100))
    amount_max_cents = int(round(subtotal_max * 100))

    return Quote(
        amount_min_cents=amount_min_cents,
        amount_max_cents=amount_max_cents,
        tier=tier,
        est_truck_fraction=est_truck_fraction,
        currency="USD",
    )
