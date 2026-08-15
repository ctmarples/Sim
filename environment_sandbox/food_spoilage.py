"""Per-storage food quality meters and spoilage conversion."""

from __future__ import annotations

from typing import Any

SPOILAGE_KEY = "spoilage"


def spoilable_food_keys() -> frozenset[str]:
    from resource_balance import VILLAGER_FOOD_KEYS

    return frozenset(str(k) for k in VILLAGER_FOOD_KEYS)


def is_spoilable_food(key: str) -> bool:
    return key in spoilable_food_keys()


def ensure_food_quality_map(storage: Any) -> dict[str, float]:
    q = getattr(storage, "food_quality", None)
    if not isinstance(q, dict):
        q = {}
        setattr(storage, "food_quality", q)
    return q


def food_quality(storage: Any, key: str) -> float:
    if int(getattr(storage, key, 0) or 0) <= 0:
        return 1.0
    q = ensure_food_quality_map(storage)
    return max(0.0, min(1.0, float(q.get(key, 1.0))))


def set_food_quality(storage: Any, key: str, value: float) -> None:
    q = ensure_food_quality_map(storage)
    if int(getattr(storage, key, 0) or 0) <= 0:
        q.pop(key, None)
        return
    q[key] = max(0.0, min(1.0, float(value)))


def on_food_merged(
    storage: Any,
    key: str,
    *,
    amount_before: int,
    amount_added: int,
    src_quality: float = 1.0,
) -> None:
    """When food is added onto an existing key, keep the lower quality meter."""
    if amount_added <= 0 or not is_spoilable_food(key):
        return
    q = ensure_food_quality_map(storage)
    src_q = max(0.0, min(1.0, float(src_quality)))
    if amount_before <= 0:
        q[key] = src_q
    else:
        q[key] = min(float(q.get(key, 1.0)), src_q)


def on_food_removed(storage: Any, key: str) -> None:
    if int(getattr(storage, key, 0) or 0) <= 0:
        ensure_food_quality_map(storage).pop(key, None)


def serialize_food_quality(storage: Any) -> dict[str, float]:
    q = getattr(storage, "food_quality", None)
    if not isinstance(q, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in q.items():
        if int(getattr(storage, key, 0) or 0) <= 0:
            continue
        try:
            out[str(key)] = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            continue
    return out


def apply_food_quality(storage: Any, data: dict[str, float] | None) -> None:
    q = ensure_food_quality_map(storage)
    q.clear()
    if not data:
        return
    for key, value in data.items():
        if int(getattr(storage, key, 0) or 0) <= 0:
            continue
        try:
            q[str(key)] = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            continue


def qualities_for_display(storage: Any) -> dict[str, float]:
    """Quality meters for spoilable foods present in ``storage`` (UI)."""
    out: dict[str, float] = {}
    for key in spoilable_food_keys():
        if int(getattr(storage, key, 0) or 0) > 0:
            out[key] = food_quality(storage, key)
    return out


def tick_storage_spoilage(storage: Any, day_frac: float, days_to_spoil: float) -> int:
    """Decay food quality; convert one unit to spoilage when a meter hits 0.

    Returns units of spoilage produced this tick.
    """
    if day_frac <= 0 or days_to_spoil <= 0:
        return 0
    decay = float(day_frac) / max(0.05, float(days_to_spoil))
    produced = 0
    qmap = ensure_food_quality_map(storage)
    for key in list(spoilable_food_keys()):
        have = int(getattr(storage, key, 0) or 0)
        if have <= 0:
            qmap.pop(key, None)
            continue
        quality = max(0.0, min(1.0, float(qmap.get(key, 1.0))))
        quality -= decay
        while quality <= 0.0 and have > 0:
            setattr(storage, key, have - 1)
            have -= 1
            # Prefer parking spoilage on the same storage if it accepts the key.
            if hasattr(storage, SPOILAGE_KEY):
                setattr(
                    storage,
                    SPOILAGE_KEY,
                    int(getattr(storage, SPOILAGE_KEY, 0) or 0) + 1,
                )
            produced += 1
            if have > 0:
                quality += 1.0
            else:
                quality = 0.0
        if have <= 0:
            qmap.pop(key, None)
        else:
            qmap[key] = max(0.0, min(1.0, quality))
    return produced
