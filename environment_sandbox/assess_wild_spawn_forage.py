"""Full-year spawn vs forage vs recipe assessment for flora_rebalance.

Usage:
  SDL_VIDEODRIVER=dummy ../.venv/bin/python assess_wild_spawn_forage.py [save] [--years 1]
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
import settings as cfg

info = pygame.display.Info()
cfg.configure_for_display(max(info.current_w, 1280), max(info.current_h, 800))

from game import Game  # noqa: E402
from recipes import KITCHEN_RECIPES  # noqa: E402
from resource_balance import FOOD_BY_KEY, food_tier  # noqa: E402
from resources import resource_label  # noqa: E402
from save_load import load_from_path, saves_dir  # noqa: E402
from seasons import YEAR_DAYS, format_date  # noqa: E402
from wild_species import WILD_BY_KEY, is_harvestable  # noqa: E402


FOCUS_WILD = (
    "peas",
    "beans",
    "nettles",
    "potato",
    "mushrooms",
    "onion",
    "garlic",
    "kale",
    "leek",
    "pumpkin",
    "carrot",
    "turnip",
    "cabbage",
    "blackberries",
    "honey",
    "thyme",
    "sage",
    "mint",
    "wheat",
    "rye",
    "barley",
)


def _recipe_inputs_for_resource(key: str) -> list[tuple[str, int, int]]:
    """Return (recipe_name, input_need, output_tier) that consume ``key``."""
    rows = []
    for recipe in KITCHEN_RECIPES:
        need = int(recipe.inputs.get(key, 0) or 0)
        if need <= 0:
            continue
        out = next(iter(recipe.outputs), recipe.name)
        tier = food_tier(out) or int(recipe.steps or 0)
        rows.append((recipe.name, need, int(tier)))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("save", nargs="?", default="flora_rebalance.json")
    parser.add_argument("--years", type=float, default=1.0)
    # 60 ticks/day starves villager work (travel/cooldowns never finish).
    # 3600 ≈ 10× realtime speed with representative forage; omit to use save default.
    parser.add_argument("--ticks", type=int, default=3600)
    args = parser.parse_args()

    save_path = Path(args.save)
    if not save_path.is_file():
        save_path = saves_dir() / args.save
    if not save_path.is_file():
        save_path = Path(__file__).resolve().parents[1] / "saves" / args.save
    if not save_path.is_file():
        print(f"Save not found: {args.save}")
        return 1

    days = max(1, int(round(args.years * YEAR_DAYS)))
    out_dir = Path(__file__).resolve().parent / "_debug"
    out_dir.mkdir(exist_ok=True)
    report_path = out_dir / "wild_spawn_forage_report.json"

    print(f"Loading {save_path} …", flush=True)
    t0 = time.time()
    game = Game(headless=True)
    load_from_path(game, save_path)
    game.sim_speed = 0
    game.fast_forward = True
    game.resource_history.reset()
    game._bind_wild_spawn_tracker()
    # Re-establish flora so spawn ledger starts from a clean half-season.
    game.world.respawn_flora(float(game.calendar_day), passes=32)
    if args.ticks and args.ticks != game.ticks_per_day:
        try:
            game._set_ticks_per_day(args.ticks)
        except Exception:
            game.ticks_per_day = args.ticks
            from seasons import set_ticks_per_day

            set_ticks_per_day(args.ticks)

    print(
        f"Start {format_date(game.calendar_day)} vills={len(game.villagers)} "
        f"days={days} ticks/day={game.ticks_per_day}",
        flush=True,
    )

    sample_every = max(1, YEAR_DAYS // 8)
    for elapsed in range(1, days + 1):
        game.simulate_fast_day()
        if elapsed % sample_every == 0 or elapsed == days:
            spawned = game.resource_history.spawned_totals()
            reachable = game.resource_history.spawned_reachable_totals()
            produced = game.resource_history.produced_totals()
            print(
                f"  day {elapsed}/{days} {format_date(game.calendar_day)} "
                f"spawn_keys={len(spawned)} reach_keys={len(reachable)} "
                f"forage_keys={len(produced)} "
                f"peas {spawned.get('peas', 0)}/{reachable.get('peas', 0)}/{produced.get('peas', 0)} "
                f"beans {spawned.get('beans', 0)}/{reachable.get('beans', 0)}/{produced.get('beans', 0)} "
                f"nettles {spawned.get('nettles', 0)}/{reachable.get('nettles', 0)}/{produced.get('nettles', 0)} "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )

    spawned = game.resource_history.spawned_totals()
    reachable = game.resource_history.spawned_reachable_totals()
    foraged = game.resource_history.produced_totals()
    consumed = game.resource_history.consumed_totals()
    stock = {
        k: int(v)
        for k, v in game._village_stock_amounts().items()
        if int(v) > 0
    }

    # Wild forageable species → resource key
    wild_rows = []
    for species in WILD_BY_KEY.values():
        if not is_harvestable(species):
            continue
        key = species.resource_key
        s = int(spawned.get(key, 0))
        r = int(reachable.get(key, 0))
        f = int(foraged.get(key, 0))
        c = int(consumed.get(key, 0))
        st = int(stock.get(key, 0))
        rate = (f / s) if s > 0 else None
        reach_rate = (f / r) if r > 0 else None
        recipes = _recipe_inputs_for_resource(key)
        wild_rows.append(
            {
                "species": species.key,
                "resource": key,
                "label": species.label,
                "terrains": list(species.terrains),
                "yield_amount": int(species.yield_amount),
                "spawn_peak": float(species.spawn_peak),
                "spawned": s,
                "spawned_reachable": r,
                "foraged": f,
                "consumed": c,
                "stock": st,
                "forage_of_spawn": rate,
                "forage_of_reachable": reach_rate,
                "recipes_using": [
                    {"name": n, "need": need, "tier": tier}
                    for n, need, tier in recipes
                ],
            }
        )

    # Focus summary
    focus = []
    for key in FOCUS_WILD:
        s = int(spawned.get(key, 0))
        r = int(reachable.get(key, 0))
        f = int(foraged.get(key, 0))
        c = int(consumed.get(key, 0))
        focus.append(
            {
                "key": key,
                "label": resource_label(key),
                "spawned": s,
                "spawned_reachable": r,
                "foraged": f,
                "consumed": c,
                "stock": int(stock.get(key, 0)),
                "forage_of_spawn": (f / s) if s > 0 else None,
                "forage_of_reachable": (f / r) if r > 0 else None,
                "tier": food_tier(key),
                "is_food": key in FOOD_BY_KEY,
                "recipes": [
                    {"name": n, "need": need, "tier": tier}
                    for n, need, tier in _recipe_inputs_for_resource(key)
                ],
            }
        )

    # Cooked dish production by tier
    cooked = defaultdict(lambda: {"produced": 0, "consumed": 0, "stock": 0, "items": {}})
    for key, amount in foraged.items():
        tier = food_tier(key)
        if tier is None:
            continue
        bucket = cooked[f"T{tier}"]
        bucket["produced"] += int(amount)
        bucket["consumed"] += int(consumed.get(key, 0))
        bucket["stock"] += int(stock.get(key, 0))
        bucket["items"][key] = {
            "produced": int(amount),
            "consumed": int(consumed.get(key, 0)),
            "stock": int(stock.get(key, 0)),
        }

    # Diagnosis helpers
    weak = [
        row
        for row in wild_rows
        if row["resource"] in FOCUS_WILD
        and (
            row["spawned"] < 30
            or (row["spawned"] > 0 and (row["forage_of_spawn"] or 0) < 0.15)
        )
    ]
    weak.sort(key=lambda r: (r["spawned"], r["foraged"]))

    high_spawn_low_forage = [
        row
        for row in wild_rows
        if row["spawned"] >= 50 and (row["forage_of_spawn"] or 0) < 0.25
    ]
    high_spawn_low_forage.sort(key=lambda r: (r["forage_of_spawn"] or 0, -r["spawned"]))

    reachable_low_pickup = [
        row
        for row in wild_rows
        if row["spawned_reachable"] >= 20
        and (row["forage_of_reachable"] or 0) < 0.35
    ]
    reachable_low_pickup.sort(
        key=lambda r: (r["forage_of_reachable"] or 0, -r["spawned_reachable"])
    )

    payload = {
        "save": str(save_path),
        "days": days,
        "ticks_per_day": int(game.ticks_per_day),
        "elapsed_sec": round(time.time() - t0, 1),
        "focus": focus,
        "cooked_by_tier": dict(cooked),
        "wild_species": sorted(wild_rows, key=lambda r: -r["spawned"]),
        "weak_focus": weak,
        "high_spawn_low_forage": high_spawn_low_forage,
        "reachable_low_pickup": reachable_low_pickup,
        "spawned_totals": dict(sorted(spawned.items(), key=lambda kv: -kv[1])),
        "spawned_reachable_totals": dict(
            sorted(reachable.items(), key=lambda kv: -kv[1])
        ),
        "foraged_totals": dict(sorted(foraged.items(), key=lambda kv: -kv[1])[:60]),
        "consumed_totals": dict(sorted(consumed.items(), key=lambda kv: -kv[1])[:60]),
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== FOCUS: spawn / reachable / forage / used / stock ===", flush=True)
    print(
        f"{'key':14} {'spawn':>7} {'reach':>7} {'forage':>7} {'used':>7} "
        f"{'stock':>6} {'f/s%':>6} {'f/r%':>6}",
        flush=True,
    )
    for row in focus:
        pct_s = (
            f"{100 * row['forage_of_spawn']:.0f}%"
            if row["forage_of_spawn"] is not None
            else "n/a"
        )
        pct_r = (
            f"{100 * row['forage_of_reachable']:.0f}%"
            if row["forage_of_reachable"] is not None
            else "n/a"
        )
        print(
            f"{row['key']:14} {row['spawned']:7d} {row['spawned_reachable']:7d} "
            f"{row['foraged']:7d} {row['consumed']:7d} {row['stock']:6d} "
            f"{pct_s:>6} {pct_r:>6}",
            flush=True,
        )

    print("\n=== Focus recipe demand ===", flush=True)
    for row in focus:
        if not row["recipes"]:
            continue
        recipes = ", ".join(
            f"{r['name']}(T{r['tier']}×{r['need']})" for r in row["recipes"]
        )
        print(
            f"  {row['key']}: foraged={row['foraged']} used={row['consumed']} → {recipes}",
            flush=True,
        )

    print("\n=== Cooked by tier ===", flush=True)
    for tier in ("T1", "T2", "T3", "T4"):
        bucket = cooked.get(tier)
        if not bucket:
            print(f"{tier}: none", flush=True)
            continue
        print(
            f"{tier}: produced={bucket['produced']} consumed={bucket['consumed']} "
            f"stock={bucket['stock']}",
            flush=True,
        )
        for key, item in sorted(
            bucket["items"].items(), key=lambda kv: -kv[1]["produced"]
        )[:8]:
            print(
                f"  {key}: +{item['produced']} -{item['consumed']} stock={item['stock']}",
                flush=True,
            )

    print("\n=== Weak focus (low global spawn or low pickup) ===", flush=True)
    for row in weak:
        pct = (
            f"{100 * row['forage_of_spawn']:.0f}%"
            if row["forage_of_spawn"] is not None
            else "n/a"
        )
        print(
            f"  {row['species']}: spawn={row['spawned']} reach={row['spawned_reachable']} "
            f"forage={row['foraged']} ({pct}) peak={row['spawn_peak']} "
            f"terrains={row['terrains']}",
            flush=True,
        )

    print("\n=== Reachable spawn, low forage rate ===", flush=True)
    for row in reachable_low_pickup[:12]:
        pct = (
            f"{100 * row['forage_of_reachable']:.0f}%"
            if row["forage_of_reachable"] is not None
            else "n/a"
        )
        print(
            f"  {row['resource']}: reach={row['spawned_reachable']} "
            f"forage={row['foraged']} ({pct})",
            flush=True,
        )

    print("\n=== High global spawn, low forage rate ===", flush=True)
    for row in high_spawn_low_forage[:12]:
        pct = (
            f"{100 * row['forage_of_spawn']:.0f}%"
            if row["forage_of_spawn"] is not None
            else "n/a"
        )
        print(
            f"  {row['resource']}: spawn={row['spawned']} reach={row['spawned_reachable']} "
            f"forage={row['foraged']} ({pct})",
            flush=True,
        )

    print(f"\nWrote {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
