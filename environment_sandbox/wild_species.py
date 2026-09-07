"""Central catalogue for wild map flora.

Add or tune a forage plant here — terrain, seasonality, yield, seeding, and
icon — instead of scattering knobs across ``world.py``, ``seasons.py``,
``resource_balance.py``, and ``ui.py``.

``feature`` must match a ``FeatureType`` name (e.g. ``WILD_CROP``, ``REED``).
For ``WILD_CROP``, set ``crop_key`` to a ``CropDef.key`` from ``crops.py``
(plant art then comes from that CropDef unless ``icon_base`` is set).

Non-crop plants (reed, mushroom, …) set ``icon_base`` to an SVG name under
``assets/icons/`` and ``icon_recolour`` for SVG CSS classes.

Day-of-year windows use the 112-day calendar (spring 0–28, summer 28–56,
autumn 56–84, winter 84–112). Spawn envelope = rise×(1−fall) × ``spawn_peak``.
"""

from __future__ import annotations

from dataclasses import dataclass


Colour = tuple[int, int, int]


@dataclass(frozen=True)
class NicheRange:
    minimum: float
    optimum_low: float
    optimum_high: float
    maximum: float


@dataclass(frozen=True)
class PlantSuitability:
    temperature: float
    rainfall: float
    moisture: float
    fertility: float
    disturbance: float
    combined: float


ENVIRONMENT_WEIGHTS = {
    "soil_moisture": 0.35,
    "temperature": 0.20,
    "fertility": 0.20,
    "disturbance": 0.20,
    "rainfall": 0.05,
}
MIN_NICHE_RESPONSE_FOR_ESTABLISHMENT = 0.05
PLANT_STRESS_THRESHOLD = 0.35
PLANT_SEVERE_STRESS_THRESHOLD = 0.15
PLANT_STRESS_MORTALITY = 0.05
PLANT_SEVERE_STRESS_MORTALITY = 0.20
WILD_PROPAGULE_NEIGHBOUR_BONUS = 0.15
WILD_PROPAGULE_MAX_MULTIPLIER = 2.0
# Temperature grids are Celsius; niche catalogue values are normalized to this range.
TEMPERATURE_MIN_C = -10.0
TEMPERATURE_MAX_C = 35.0


@dataclass(frozen=True)
class WildSpeciesDef:
    key: str
    label: str
    feature: str
    # Terrains this may occupy (TerrainType names).
    terrains: tuple[str, ...]
    # If non-empty, tile must also touch at least one of these terrains
    # (ecotone / border placement, e.g. riparian beside grass).
    edge_terrains: tuple[str, ...] = ()
    # Inventory / produce key when harvested (empty = not collectable).
    resource_key: str = ""
    # Deposit left on the tile (or fruit amount when ``fruiting``).
    yield_amount: int = 0
    # CropDef key when feature is WILD_CROP.
    crop_key: str | None = None

    # --- Drawing (SVG under assets/icons/) --------------------------------
    # Empty → WILD_CROP uses CropDef.icon_base; non-crops should set this.
    icon_base: str = ""
    # SVG class → RGB (vibrancy applied at draw time).
    icon_recolour: tuple[tuple[str, Colour], ...] = ()
    # Optional fruit class swapped when tile deposit > 0 (berry bushes).
    fruit_class: str = ""
    fruit_colour: Colour | None = None
    empty_fruit_colour: Colour | None = None

    # --- New-map seeding -------------------------------------------------
    initial_count: int = 0
    initial_fraction: float = 0.0
    # Place beside this FeatureType name (e.g. TREE → fallen wood).
    seed_near_feature: str | None = None
    seed_near_chance: float = 0.0

    # --- Ongoing spawn (per forage/mushroom tick) ------------------------
    spawn_peak: float = 0.0
    spawn_rise: tuple[float, float] = (0.0, 0.0)
    spawn_fall: tuple[float, float] = (0.0, 0.0)
    spawn_activity: float = 1.0
    # Only spawn on empty tiles adjacent to this FeatureType.
    near_feature: str | None = None
    spread_chance: float = 0.0
    # Extra plants when a wild-crop seed lands (min, max inclusive extras).
    patch_extras: tuple[int, int] = (0, 0)

    # --- Despawn / clear -------------------------------------------------
    despawn_fade: tuple[float, float] = (0.0, 0.0)
    despawn_fade_end: tuple[float, float] = (0.0, 0.0)
    despawn_fade_chance: float = 0.0
    despawn_leftover_from: float = -1.0
    despawn_leftover_chance: float = 0.0
    # Hard wipe when local day >= this (−1 = never). Winter mushrooms = 84.
    clear_from_day: float = -1.0
    # Smooth ramp to full despawn over this many days before clear_from_day.
    clear_ramp_days: float = 0.0

    # --- Caps / fruit ----------------------------------------------------
    counts_toward_cap: bool = True
    # Permanent plant; deposit refreshes while fruit window is active.
    fruiting: bool = False
    fruit_rise: tuple[float, float] = (0.0, 0.0)
    fruit_fall: tuple[float, float] = (0.0, 0.0)
    # Chance that harvesting this wild species also yields one seed.
    seed_drop_chance: float = 1.0 / 3.0
    seed_amount_max: int = 1

    # Species that share one spawn roll (wild crops). First entry's envelope wins.
    spawn_group: str | None = None
    temperature_niche: NicheRange | None = None
    rainfall_niche: NicheRange | None = None
    moisture_niche: NicheRange | None = None
    fertility_niche: NicheRange | None = None
    disturbance_niche: NicheRange | None = None
    ecology_tags: tuple[str, ...] = ()


# Max fraction of each terrain that may be covered by cap-counting wild plants.
WILD_PLANT_MAX_FRACTION: float = 0.20

# FeatureType names drawn / resolved via this catalogue (not buildings/trees).
WILD_FEATURE_NAMES: frozenset[str] = frozenset(
    {"WILD_CROP", "HERB", "REED", "MUSHROOM", "BERRY_BUSH", "WOOD_BUSH"}
)

# ---------------------------------------------------------------------------
# Catalogue — edit this list to add species
# ---------------------------------------------------------------------------
# Shared wild-crop seasonality (spring sprout, late-summer/autumn wither).
_WC_RISE = (0.0, 8.0)
_WC_FALL = (18.0, 30.0)
_WC_DESPAWN_FADE = (48.0, 58.0)
_WC_DESPAWN_FADE_END = (72.0, 82.0)
_WC_DESPAWN_FADE_CHANCE = 0.08
_WC_LEFTOVER_FROM = 70.0
_WC_LEFTOVER_CHANCE = 0.15
_WC_PEAK = 0.045
_WC_PATCH = (1, 4)


def _wild_crop(
    key: str,
    label: str,
    terrains: tuple[str, ...],
    niches: tuple[tuple[float, float, float, float], ...],
) -> WildSpeciesDef:
    return WildSpeciesDef(
        key=key,
        label=label,
        feature="WILD_CROP",
        crop_key=key,
        terrains=terrains,
        resource_key=key,
        yield_amount=3,
        # Art from CropDef (stem/flower recolour); leave icon_base empty.
        spawn_peak=_WC_PEAK,
        spawn_rise=_WC_RISE,
        spawn_fall=_WC_FALL,
        spawn_activity=0.55,
        patch_extras=_WC_PATCH,
        despawn_fade=_WC_DESPAWN_FADE,
        despawn_fade_end=_WC_DESPAWN_FADE_END,
        despawn_fade_chance=_WC_DESPAWN_FADE_CHANCE,
        despawn_leftover_from=_WC_LEFTOVER_FROM,
        despawn_leftover_chance=_WC_LEFTOVER_CHANCE,
        spawn_group="wild_crop",
        temperature_niche=NicheRange(*niches[0]),
        rainfall_niche=NicheRange(*niches[1]),
        moisture_niche=NicheRange(*niches[2]),
        fertility_niche=NicheRange(*niches[3]),
        disturbance_niche=NicheRange(*niches[4]),
        ecology_tags=("feral_crop", "grazer_forage"),
    )


WILD_SPECIES: tuple[WildSpeciesDef, ...] = (
    # --- Permanent berry / nut bushes ------------------------------------
    WildSpeciesDef(
        key="blackberry",
        label="Blackberry bush",
        feature="BERRY_BUSH",
        terrains=("GRASS",),
        resource_key="blackberries",
        yield_amount=4,
        icon_base="berry_bush",
        icon_recolour=(("bush", (45, 100, 45)),),
        fruit_class="berry",
        fruit_colour=(40, 20, 55),
        empty_fruit_colour=(70, 95, 55),
        initial_count=2,
        spawn_peak=0.0,
        fruiting=True,
        fruit_rise=(26.0, 36.0),
        fruit_fall=(48.0, 58.0),
        counts_toward_cap=True,
        temperature_niche=NicheRange(.20,.35,.65,.85), rainfall_niche=NicheRange(.25,.40,.70,.90),
        moisture_niche=NicheRange(.25,.40,.70,.85), fertility_niche=NicheRange(.25,.40,.75,.95),
        disturbance_niche=NicheRange(.00,.05,.25,.60), ecology_tags=("flowering", "pollinator_food", "grazer_forage"),
    ),
    WildSpeciesDef(
        key="sloe",
        label="Sloe berry bush",
        feature="BERRY_BUSH",
        terrains=("GRASS",),
        resource_key="sloe_berries",
        yield_amount=4,
        icon_base="berry_bush",
        icon_recolour=(("bush", (55, 105, 50)),),
        fruit_class="berry",
        fruit_colour=(55, 45, 120),
        empty_fruit_colour=(75, 100, 55),
        initial_count=2,
        spawn_peak=0.0,
        fruiting=True,
        fruit_rise=(26.0, 36.0),
        fruit_fall=(48.0, 58.0),
        counts_toward_cap=True,
        temperature_niche=NicheRange(.18,.32,.62,.82), rainfall_niche=NicheRange(.20,.35,.65,.85),
        moisture_niche=NicheRange(.20,.35,.65,.80), fertility_niche=NicheRange(.20,.35,.70,.90),
        disturbance_niche=NicheRange(.00,.05,.25,.55), ecology_tags=("flowering", "pollinator_food", "grazer_forage"),
    ),
    WildSpeciesDef(
        key="elderberry",
        label="Elder berry bush",
        feature="BERRY_BUSH",
        terrains=("GRASS",),
        resource_key="elderberries",
        yield_amount=4,
        icon_base="berry_bush",
        icon_recolour=(("bush", (50, 115, 55)),),
        fruit_class="berry",
        fruit_colour=(110, 30, 90),
        empty_fruit_colour=(70, 95, 55),
        initial_count=1,
        spawn_peak=0.0,
        fruiting=True,
        fruit_rise=(26.0, 36.0),
        fruit_fall=(48.0, 58.0),
        counts_toward_cap=True,
        temperature_niche=NicheRange(.22,.38,.68,.88), rainfall_niche=NicheRange(.28,.42,.72,.92),
        moisture_niche=NicheRange(.28,.42,.72,.88), fertility_niche=NicheRange(.28,.42,.78,.95),
        disturbance_niche=NicheRange(.00,.05,.22,.55), ecology_tags=("flowering", "pollinator_food", "grazer_forage"),
    ),
    WildSpeciesDef(
        key="hazel",
        label="Hazel bush",
        feature="BERRY_BUSH",
        terrains=("GRASS",),
        resource_key="hazelnuts",
        yield_amount=3,
        icon_base="berry_bush",
        icon_recolour=(("bush", (60, 110, 50)),),
        fruit_class="berry",
        fruit_colour=(150, 105, 45),
        empty_fruit_colour=(85, 100, 60),
        initial_count=1,
        spawn_peak=0.0,
        fruiting=True,
        fruit_rise=(48.0, 58.0),
        fruit_fall=(70.0, 80.0),
        counts_toward_cap=True,
        temperature_niche=NicheRange(.15,.30,.60,.80), rainfall_niche=NicheRange(.22,.38,.68,.88),
        moisture_niche=NicheRange(.22,.38,.68,.85), fertility_niche=NicheRange(.25,.40,.75,.95),
        disturbance_niche=NicheRange(.00,.05,.20,.50), ecology_tags=("flowering", "grazer_forage"),
    ),
    WildSpeciesDef(
        key="reed",
        label="Reed",
        feature="REED",
        terrains=("RIPARIAN"),
        edge_terrains=("RIVER","WATER"),
        resource_key="reeds",
        yield_amount=3,
        icon_base="reed",
        initial_fraction=0.55,
        spawn_peak=0.09,
        spawn_rise=(0.0, 6.0),
        spawn_fall=(52.0, 58.0),
        spawn_activity=0.85,
        counts_toward_cap=True,
        temperature_niche=NicheRange(.15,.30,.75,.95), rainfall_niche=NicheRange(.30,.50,.90,1),
        moisture_niche=NicheRange(.65,.80,1,1), fertility_niche=NicheRange(.20,.40,.90,1),
        disturbance_niche=NicheRange(0,.10,.40,.75), ecology_tags=("wetland_cover",),
    ),
    WildSpeciesDef(
        key="sedge",
        label="Sedge",
        feature="REED",
        terrains=("RIPARIAN",),
        # Landward rim of the shore strip (beside open grass / meadow).
        edge_terrains=("GRASS", "MEADOW"),
        resource_key="",  # scenery only — not collectable
        yield_amount=0,
        icon_base="sedge",
        initial_fraction=0.55,
        spawn_peak=0.08,
        spawn_rise=(0.0, 6.0),
        spawn_fall=(52.0, 58.0),
        spawn_activity=0.85,
        counts_toward_cap=True,
        temperature_niche=NicheRange(.10,.25,.70,.90), rainfall_niche=NicheRange(.25,.45,.85,1),
        moisture_niche=NicheRange(.50,.65,.90,1), fertility_niche=NicheRange(.10,.25,.70,.90),
        disturbance_niche=NicheRange(0,.05,.30,.65), ecology_tags=("wetland_cover",),
    ),
    WildSpeciesDef(
        key="cattail",
        label="Cattail",
        feature="REED",
        terrains=("WATER"),
        edge_terrains=("RIPARIAN","GRASS","MEADOW","SOIL"),
        resource_key="",  # scenery only — not collectable
        yield_amount=0,
        icon_base="cattail",
        initial_fraction=0.55,
        spawn_peak=0.08,
        spawn_rise=(0.0, 6.0),
        spawn_fall=(52.0, 58.0),
        spawn_activity=0.85,
        counts_toward_cap=True,
        temperature_niche=NicheRange(.20,.40,.80,1), rainfall_niche=NicheRange(.35,.55,.95,1),
        moisture_niche=NicheRange(.75,.90,1,1), fertility_niche=NicheRange(.35,.60,1,1),
        disturbance_niche=NicheRange(0,.10,.45,.75), ecology_tags=("wetland_cover", "amphibian_habitat"),
    ),
    WildSpeciesDef(
        key="mushroom",
        label="Mushroom",
        feature="MUSHROOM",
        terrains=("SOIL", "FOREST_FLOOR"),
        resource_key="mushrooms",
        yield_amount=4,
        icon_base="mushroom",
        icon_recolour=(
            ("cap", (200, 170, 140)),
            ("stem", (210, 200, 180)),
        ),
        spawn_peak=0.025,
        spawn_rise=(56.0, 64.0),
        spawn_fall=(78.0, 84.0),
        near_feature="TREE",
        spread_chance=0.01,
        clear_from_day=84.0,
        clear_ramp_days=4.0,
        counts_toward_cap=False,
        temperature_niche=NicheRange(.05,.20,.55,.75), rainfall_niche=NicheRange(.45,.60,1,1),
        # Autumn forest floor can be viable before the cached soil-water layer
        # fully recharges. Keep bone-dry cells poor, without excluding nearly
        # every tree-adjacent site after a dry summer.
        moisture_niche=NicheRange(.03,.20,.75,.95), fertility_niche=NicheRange(.25,.40,.80,.95),
        disturbance_niche=NicheRange(0,0,.20,.45),
    ),
    WildSpeciesDef(
        key="wood_bush",
        label="Fallen wood",
        feature="WOOD_BUSH",
        terrains=("SOIL", "FOREST_FLOOR", "GRASS", "MEADOW"),
        resource_key="wood",
        yield_amount=1,
        icon_base="wood_loose",
        icon_recolour=(
            ("body", (120, 90, 50)),
            ("leaf", (70, 130, 55)),
        ),
        seed_near_feature="TREE",
        seed_near_chance=0.1,
        spawn_peak=0.01,
        spawn_rise=(54.0, 62.0),
        spawn_fall=(78.0, 84.0),
        near_feature="TREE",
        clear_from_day=84.0,
        counts_toward_cap=False,
    ),
    # --- Wild crops by terrain (art from crops.CropDef) --------------------
    _wild_crop("flax", "Flax", ("MEADOW",), ((.20,.35,.65,.80),(.25,.40,.70,.85),(.30,.45,.70,.80),(.30,.45,.75,.90),(.10,.30,.55,.75))),
    _wild_crop("hemp", "Hemp", ("MEADOW",), ((.30,.50,.80,.95),(.25,.40,.75,.90),(.30,.45,.75,.90),(.45,.65,1,1),(.10,.30,.60,.80))),
    _wild_crop("sage", "Sage", ("MEADOW",), ((.35,.55,.85,1),(.00,.10,.40,.65),(.10,.20,.45,.65),(.10,.25,.60,.80),(.05,.20,.45,.70))),
    _wild_crop("mint", "Mint", ("MEADOW",), ((.15,.30,.70,.90),(.35,.50,.85,1),(.45,.60,.90,1),(.25,.45,.85,1),(.05,.15,.40,.65))),
    _wild_crop("wheat", "Wheat", ("GRASS",), ((.20,.40,.70,.85),(.15,.30,.60,.80),(.20,.35,.60,.75),(.45,.65,1,1),(.15,.35,.65,.85))),
    _wild_crop("rye", "Rye", ("GRASS",), ((.05,.25,.60,.80),(.10,.25,.60,.80),(.15,.25,.55,.70),(.15,.30,.65,.85),(.10,.30,.60,.85))),
    _wild_crop("barley", "Barley", ("GRASS",), ((.20,.35,.70,.85),(.10,.25,.55,.75),(.15,.30,.60,.75),(.35,.55,.90,1),(.15,.35,.65,.85))),
    _wild_crop("peas", "Peas", ("MEADOW", "FOREST_FLOOR"), ((.10,.25,.60,.78),(.25,.40,.75,.90),(.30,.45,.80,.95),(.40,.60,.95,1),(.05,.20,.50,.75))),
    _wild_crop("beans", "Beans", ("MEADOW",), ((.30,.45,.80,.95),(.25,.40,.75,.90),(.30,.45,.80,.95),(.45,.65,1,1),(.05,.20,.50,.75))),
    _wild_crop("onion", "Onion", ("SOIL", "FOREST_FLOOR"), ((.20,.35,.70,.85),(.15,.30,.60,.80),(.20,.35,.60,.75),(.35,.55,.85,1),(.15,.35,.65,.85))),
    _wild_crop("cabbage", "Cabbage", ("SOIL", "FOREST_FLOOR"), ((.10,.25,.60,.75),(.30,.45,.75,.90),(.35,.50,.75,.90),(.55,.70,1,1),(.10,.30,.60,.80))),
    _wild_crop("carrot", "Carrot", ("SOIL", "FOREST_FLOOR"), ((.15,.30,.70,.85),(.20,.35,.65,.80),(.20,.35,.65,.80),(.30,.45,.80,.95),(.15,.35,.70,.90))),
    _wild_crop("turnip", "Turnip", ("SOIL", "FOREST_FLOOR"), ((.05,.20,.60,.78),(.25,.40,.75,.90),(.30,.45,.80,.95),(.45,.65,1,1),(.10,.30,.60,.80))),
    _wild_crop("garlic", "Garlic", ("SOIL", "FOREST_FLOOR"), ((.10,.25,.65,.80),(.15,.30,.60,.80),(.20,.35,.60,.75),(.30,.45,.80,.95),(.10,.30,.60,.80))),
    WildSpeciesDef(key="clover", label="Clover", feature="HERB", terrains=("GRASS","MEADOW"), icon_base="flower_plant", icon_recolour=(("stem", (65, 145, 65)), ("flower", (65, 145, 65))), spawn_peak=.035, spawn_rise=_WC_RISE, spawn_fall=_WC_FALL, spawn_activity=.55, spread_chance=.01, temperature_niche=NicheRange(.20,.35,.70,.85), rainfall_niche=NicheRange(.20,.35,.70,.85), moisture_niche=NicheRange(.25,.40,.70,.85), fertility_niche=NicheRange(.20,.35,.70,.90), disturbance_niche=NicheRange(.05,.20,.45,.70), ecology_tags=("flowering","pollinator_food","grazer_forage")),
    WildSpeciesDef(key="yarrow", label="Yarrow", feature="HERB", terrains=("GRASS","MEADOW","SOIL"), icon_base="flower_plant", icon_recolour=(("stem", (75, 130, 60)), ("flower", (240, 240, 225))), spawn_peak=.035, spawn_rise=_WC_RISE, spawn_fall=_WC_FALL, spawn_activity=.55, spread_chance=.01, temperature_niche=NicheRange(.25,.45,.80,.95), rainfall_niche=NicheRange(.05,.15,.45,.70), moisture_niche=NicheRange(.10,.20,.50,.70), fertility_niche=NicheRange(.05,.20,.55,.75), disturbance_niche=NicheRange(.10,.25,.55,.80), ecology_tags=("flowering","pollinator_food","grazer_forage")),
    WildSpeciesDef(key="meadowsweet", label="Meadowsweet", feature="HERB", terrains=("MEADOW","RIPARIAN"), icon_base="flower_plant", icon_recolour=(("stem", (115, 170, 90)), ("flower", (225, 240, 210))), spawn_peak=.035, spawn_rise=_WC_RISE, spawn_fall=_WC_FALL, spawn_activity=.55, spread_chance=.01, temperature_niche=NicheRange(.15,.30,.70,.85), rainfall_niche=NicheRange(.35,.50,.90,1), moisture_niche=NicheRange(.45,.60,.90,1), fertility_niche=NicheRange(.25,.40,.80,.95), disturbance_niche=NicheRange(0,.10,.30,.55), ecology_tags=("flowering","pollinator_food","wetland_cover")),
    WildSpeciesDef(key="nettle", label="Nettle", feature="HERB", terrains=("GRASS","MEADOW","SOIL","FOREST_FLOOR"), icon_base="flower_plant", icon_recolour=(("stem", (35, 90, 45)), ("flower", (35, 90, 45))), spawn_peak=.035, spawn_rise=_WC_RISE, spawn_fall=_WC_FALL, spawn_activity=.55, spread_chance=.01, temperature_niche=NicheRange(.20,.40,.75,.90), rainfall_niche=NicheRange(.20,.35,.75,.90), moisture_niche=NicheRange(.25,.40,.75,.90), fertility_niche=NicheRange(.55,.75,1,1), disturbance_niche=NicheRange(.15,.35,.65,.85), ecology_tags=("flowering","pollinator_food")),
)

WILD_BY_KEY: dict[str, WildSpeciesDef] = {s.key: s for s in WILD_SPECIES}
WILD_FOOTPRINTS: dict[str, tuple[int, ...]] = {}


def species_for_feature(feature_name: str) -> WildSpeciesDef | None:
    """Default species for a FeatureType (first non-group match, else any)."""
    for s in WILD_SPECIES:
        if s.feature == feature_name and s.spawn_group is None:
            return s
    for s in WILD_SPECIES:
        if s.feature == feature_name:
            return s
    return None


def resolve_species(
    feature_name: str,
    kind: str | None = None,
) -> WildSpeciesDef | None:
    """Resolve catalogue entry from feature + optional cell kind key."""
    if kind == "berry_bush":
        kind = "blackberry"
    if kind:
        s = WILD_BY_KEY.get(kind)
        if s is not None and (
            s.feature == feature_name
            or (feature_name in ("WILD_CROP", "HERB", "CROP_HERB") and s.feature == "WILD_CROP")
        ):
            return s
        # Farm / wild crop keyed only in crops.py.
        if feature_name in ("WILD_CROP", "HERB", "CROP_HERB"):
            crop_match = WILD_BY_KEY.get(kind)
            if crop_match is not None and crop_match.feature == "WILD_CROP":
                return crop_match
    return species_for_feature(feature_name)


def species_sharing_feature(feature_name: str) -> tuple[WildSpeciesDef, ...]:
    return tuple(s for s in WILD_SPECIES if s.feature == feature_name)


def non_crop_on_terrain(terrain_name: str) -> tuple[WildSpeciesDef, ...]:
    return tuple(
        s
        for s in WILD_SPECIES
        if s.feature != "WILD_CROP" and terrain_name in s.terrains
    )


def is_harvestable(species: WildSpeciesDef | None) -> bool:
    """True when the plant yields a collectable inventory resource."""
    if species is None:
        return False
    return bool(species.resource_key) and int(species.yield_amount) > 0


def plant_forage_yield(
    feature_name: str, kind: str | None
) -> tuple[str, int] | None:
    """Inventory key + max yield for a wild plant cell, or None if not collectable.

    Scenic HERB flora (clover, yarrow, …) have no resource_key and must not
    fall back to sage. Wild crops resolve through ``crops.CROP_BY_KEY``.
    """
    from crops import CROP_BY_KEY

    if feature_name == "REED":
        species = resolve_species("REED", kind)
        if not is_harvestable(species):
            return None
        assert species is not None
        return (species.resource_key or "reeds", max(1, int(species.yield_amount)))

    if feature_name not in ("HERB", "WILD_CROP", "CROP_HERB"):
        return None

    crop_key = kind
    if not crop_key and feature_name in ("WILD_CROP", "CROP_HERB"):
        crop_key = "sage"
    if crop_key and crop_key in CROP_BY_KEY:
        crop = CROP_BY_KEY[crop_key]
        wild = WILD_BY_KEY.get(crop_key)
        ymax = max(1, int(wild.yield_amount) if wild is not None else 3)
        return crop.produce_key, ymax

    species = resolve_species(feature_name, kind)
    # Mis-tagged scenic herbs (e.g. clover saved as WILD_CROP) must not use the
    # feature default wild-crop species — only honour an exact kind match.
    if kind:
        exact = WILD_BY_KEY.get(kind)
        if exact is not None and exact.feature == "HERB":
            if is_harvestable(exact):
                return exact.resource_key, max(1, int(exact.yield_amount))
            return None
    if is_harvestable(species):
        assert species is not None
        return species.resource_key, max(1, int(species.yield_amount))
    return None


# Always available on forager Collect (not gated by diary flora).
ALWAYS_FORAGE_KEYS: frozenset[str] = frozenset({"wood", "rock", "honey"})


def forage_resource_keys_for_flora(flora_keys: set[str] | None) -> frozenset[str] | None:
    """Inventory keys a forager may collect given diary flora.

    ``None`` flora_keys means unrestricted (sandbox / post-tutorial).
    Wood, rock, and honey stay available even with an empty flora list.
    """
    if flora_keys is None:
        return None
    allowed: set[str] = set(ALWAYS_FORAGE_KEYS)
    from crops import CROP_BY_KEY
    from trees import TREE_BY_KEY

    for raw in flora_keys:
        key = str(raw or "")
        if ":" not in key:
            continue
        group, name = key.split(":", 1)
        if group == "tree":
            tree = TREE_BY_KEY.get(name)
            if tree is not None:
                allowed.add(tree.yield_key)
            continue
        if group not in ("wild", "plant"):
            continue
        species = WILD_BY_KEY.get(name)
        if species is not None and species.resource_key:
            allowed.add(species.resource_key)
            continue
        crop = CROP_BY_KEY.get(name)
        if crop is not None:
            allowed.add(crop.produce_key)
    return frozenset(allowed)


def wild_crops_by_terrain() -> dict[str, tuple[str, ...]]:
    """Terrain name → crop keys allowed on that terrain."""
    out: dict[str, list[str]] = {}
    for s in WILD_SPECIES:
        if s.feature != "WILD_CROP" or not s.crop_key:
            continue
        for t in s.terrains:
            out.setdefault(t, []).append(s.crop_key)
    return {k: tuple(v) for k, v in out.items()}


def spawn_group_leader(group: str) -> WildSpeciesDef | None:
    for s in WILD_SPECIES:
        if s.spawn_group == group:
            return s
    return None


def icon_recolour_for(
    species: WildSpeciesDef,
    *,
    deposit: int = 0,
) -> dict[str, Colour]:
    """Build SVG class→colour map for blit_icon (before vibrancy)."""
    out: dict[str, Colour] = {cls: rgb for cls, rgb in species.icon_recolour}
    if species.fruit_class:
        if deposit > 0 and species.fruit_colour is not None:
            out[species.fruit_class] = species.fruit_colour
        elif species.empty_fruit_colour is not None:
            out[species.fruit_class] = species.empty_fruit_colour
    return out


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 <= edge0:
        return 1.0 if x >= edge1 else 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def niche_response(value: float, niche: NicheRange | None) -> float:
    """Smooth trapezoidal response; ``None`` is unconstrained/neutral."""
    if niche is None:
        return 1.0
    lo, opt_lo, opt_hi, hi = (
        float(niche.minimum), float(niche.optimum_low),
        float(niche.optimum_high), float(niche.maximum),
    )
    if not (0.0 <= lo <= opt_lo <= opt_hi <= hi <= 1.0):
        return 0.0
    x = max(0.0, min(1.0, float(value)))
    if x < lo or x > hi or (x == lo and lo < opt_lo) or (x == hi and opt_hi < hi):
        return 0.0
    if opt_lo <= x <= opt_hi:
        return 1.0
    if x < opt_lo:
        return _smoothstep(lo, opt_lo, x)
    return 1.0 - _smoothstep(opt_hi, hi, x)


def normalize_temperature_c(value: float) -> float:
    return max(0.0, min(1.0, (float(value) - TEMPERATURE_MIN_C) /
                             (TEMPERATURE_MAX_C - TEMPERATURE_MIN_C)))


def species_environment_suitability(
    species: WildSpeciesDef, *, temperature: float, rainfall: float,
    soil_moisture: float, fertility: float, disturbance: float,
) -> PlantSuitability:
    """Score cached environmental state; temperature is normalized 0..1 here."""
    values = {
        "temperature": (temperature, species.temperature_niche),
        "rainfall": (rainfall, species.rainfall_niche),
        "soil_moisture": (soil_moisture, species.moisture_niche),
        "fertility": (fertility, species.fertility_niche),
        "disturbance": (disturbance, species.disturbance_niche),
    }
    scores = {name: niche_response(value, niche) for name, (value, niche) in values.items()}
    included = [(ENVIRONMENT_WEIGHTS[name], scores[name]) for name, (_, niche) in values.items()
                if niche is not None]
    total = sum(weight for weight, _ in included)
    combined = sum(weight * score for weight, score in included) / total if total else 1.0
    return PlantSuitability(scores["temperature"], scores["rainfall"],
                            scores["soil_moisture"], scores["fertility"],
                            scores["disturbance"], max(0.0, min(1.0, combined)))


def environment_allows_establishment(species: WildSpeciesDef, suitability: PlantSuitability) -> bool:
    """Apply hard failure to persistent site dimensions, not daily rainfall.

    Rainfall is instantaneous weather in the authoritative grid and already
    feeds soil moisture.  Its response therefore modifies annual abundance
    through ``combined`` without making every rainless day impossible.
    """
    # Temperature and moisture can make plant physiology impossible. Rainfall
    # is transient, while fertility and disturbance describe competitive
    # advantage rather than absolute survival; those remain weighted quality.
    pairs = ((species.temperature_niche, suitability.temperature),
             (species.moisture_niche, suitability.moisture))
    return all(niche is None or score >= MIN_NICHE_RESPONSE_FOR_ESTABLISHMENT
               for niche, score in pairs)


def environmental_mortality_rate(suitability: float) -> float:
    if suitability < PLANT_SEVERE_STRESS_THRESHOLD:
        return PLANT_SEVERE_STRESS_MORTALITY
    if suitability < PLANT_STRESS_THRESHOLD:
        return PLANT_STRESS_MORTALITY
    return 0.0


NICHE_AUDIT_SCENARIOS = {
    "cool_wet_low_disturbance": (.35, .80, .82, .45, .10),
    "warm_wet_low_disturbance": (.68, .78, .82, .55, .12),
    "warm_dry_low_disturbance": (.75, .25, .28, .30, .15),
    "warm_fertile_disturbed": (.65, .55, .55, .90, .50),
    "cool_poor_disturbed": (.30, .35, .35, .20, .50),
    "saturated_fertile": (.65, .90, .96, .92, .20),
    "saturated_nutrient_poor": (.50, .85, .90, .25, .12),
}


def niche_audit(top_n: int = 5) -> dict[str, tuple[tuple[str, float], ...]]:
    """Deterministic tuning diagnostic, independent of terrain availability."""
    result = {}
    for name, (temp, rain, moisture, fertility, disturbance) in NICHE_AUDIT_SCENARIOS.items():
        ranked = []
        for species in WILD_SPECIES:
            if not any((species.temperature_niche, species.rainfall_niche,
                        species.moisture_niche, species.fertility_niche,
                        species.disturbance_niche)):
                continue
            score = species_environment_suitability(
                species, temperature=temp, rainfall=rain, soil_moisture=moisture,
                fertility=fertility, disturbance=disturbance)
            if environment_allows_establishment(species, score):
                ranked.append((species.key, score.combined))
        result[name] = tuple(sorted(ranked, key=lambda item: (-item[1], item[0]))[:top_n])
    return result


def format_environment_debug(species: WildSpeciesDef, suitability: PlantSuitability,
                             *, temperature: float, rainfall: float,
                             soil_moisture: float, fertility: float,
                             disturbance: float, day: float) -> str:
    rows = (("Temperature", temperature, suitability.temperature),
            ("Rainfall", rainfall, suitability.rainfall),
            ("Soil moisture", soil_moisture, suitability.moisture),
            ("Fertility", fertility, suitability.fertility),
            ("Disturbance", disturbance, suitability.disturbance))
    lines = [f"Species: {species.label}"]
    lines.extend(f"{label:<16} {value:5.2f}   suitability {score:5.2f}"
                 for label, value, score in rows)
    envelope = _envelope(day, species.spawn_rise, species.spawn_fall)
    effective = species_spawn_rate(species, day) * species.spawn_activity * suitability.combined
    lines += [f"Combined suitability: {suitability.combined:.2f}",
              f"Seasonal spawn envelope: {envelope:.2f}",
              f"Effective spawn probability: {effective:.5f}"]
    return "\n".join(lines)


def _envelope(
    day: float,
    rise: tuple[float, float],
    fall: tuple[float, float],
) -> float:
    if rise == (0.0, 0.0) and fall == (0.0, 0.0):
        return 0.0
    r = _smoothstep(rise[0], rise[1], day) if rise != (0.0, 0.0) else 1.0
    f = (
        (1.0 - _smoothstep(fall[0], fall[1], day))
        if fall != (0.0, 0.0)
        else 1.0
    )
    return r * f


def species_spawn_rate(species: WildSpeciesDef, day: float) -> float:
    """Chance contribution at peak×envelope for this species."""
    if species.spawn_peak <= 0:
        return 0.0
    return species.spawn_peak * _envelope(day, species.spawn_rise, species.spawn_fall)


def species_despawn_rate(species: WildSpeciesDef, day: float) -> float:
    if species.clear_from_day >= 0:
        if day >= species.clear_from_day:
            return 1.0
        if species.clear_ramp_days > 0:
            ramp = _smoothstep(
                species.clear_from_day - species.clear_ramp_days,
                species.clear_from_day,
                day,
            )
            if ramp > 0:
                return ramp
    rate = 0.0
    if species.despawn_fade_chance > 0 and species.despawn_fade != (0.0, 0.0):
        fade = _envelope(day, species.despawn_fade, species.despawn_fade_end)
        rate += species.despawn_fade_chance * fade
    if species.despawn_leftover_from >= 0 and species.despawn_leftover_chance > 0:
        leftover = _smoothstep(
            species.despawn_leftover_from,
            species.despawn_leftover_from + 8.0,
            day,
        )
        rate += species.despawn_leftover_chance * leftover
    return min(1.0, rate)


def species_fruiting(species: WildSpeciesDef, day: float) -> bool:
    if not species.fruiting:
        return False
    return _envelope(day, species.fruit_rise, species.fruit_fall) > 0.05
