"""Player, inventory, buildings, villagers, and work tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from crops import PRODUCE_KEYS, SEED_KEYS
from recipes import (
    ALCHEMIST_INPUT_KEYS,
    ALCHEMIST_OUTPUT_KEYS,
    ALCHEMIST_RECIPES,
    BARN_RECIPES,
    COBBLER_INPUT_KEYS,
    COBBLER_OUTPUT_KEYS,
    COBBLER_RECIPES,
    CRAFT_BENCH_INPUT_KEYS,
    CRAFT_BENCH_OUTPUT_KEYS,
    CRAFT_BENCH_RECIPES,
    DRYING_RACK_RECIPES,
    FORESTER_RECIPES,
    FORESTER_PLANT_RECIPES,
    FORESTER_SPLIT_RECIPES,
    FORAGER_RECIPES,
    HUNTER_RECIPES,
    KITCHEN_FUEL_KEY,
    KITCHEN_INPUT_KEYS,
    KITCHEN_OUTPUT_KEYS,
    KITCHEN_RECIPES,
    MILL_INPUT_KEYS,
    MILL_OUTPUT_KEYS,
    MILL_RECIPES,
    PROCESSED_KEYS,
    TAILOR_INPUT_KEYS,
    TAILOR_OUTPUT_KEYS,
    TAILOR_RECIPES,
    Recipe,
    apply_recipe,
    can_craft,
    input_keys_for_recipes,
)
from settings import (
    BUILDING_FOOTPRINT,
    BUILDING_STORAGE_CAPACITY,
    FORESTER_DEFAULT_HARDWOOD_LOGS_MIN,
    FORESTER_DEFAULT_LOGS_MIN,
    INVENTORY_CAPACITY,
    PROCESSOR_RECIPE_STEPS,
    SEED_CARRY_CAPACITY,
    BuildingStorageSpec,
    building_storage_spec,
)
from trees import SAPLING_ITEM_KEYS, sapling_item_key

# Seeds share a dedicated carry pool (separate from wood/food/etc.).
SEED_ITEM_KEYS: tuple[str, ...] = ("berry_seeds", *SEED_KEYS)

# Tools carried in dedicated tool slots (not general cargo stacks).
TOOL_KEYS: tuple[str, ...] = ("axe", "spear", "fishing_rod", "hoe", "knife", "bow")
TOOL_SLOT_MAX: int = 3

# Clothing: one item per slot; cannot equip two of the same slot type.
CLOTHING_SLOTS: tuple[str, ...] = ("hat", "shirt", "trousers", "shoes", "bag")
CLOTHING_SLOT_LABELS: dict[str, str] = {
    "hat": "Hat",
    "shirt": "Shirt",
    "trousers": "Trousers",
    "shoes": "Shoes",
    "bag": "Bag",
}
# item key → clothing slot (CSV ``clothing_slot`` may add more via recipes).
CLOTHING_ITEM_SLOT: dict[str, str] = {
    "sun_hat": "hat",
    "winter_hat": "hat",
    "light_shirt": "shirt",
    "winter_coat": "shirt",
    "leather_shoes": "shoes",
    "leather_satchel": "bag",
}
CLOTHING_KEYS: tuple[str, ...] = tuple(CLOTHING_ITEM_SLOT)
# Chebyshev range for bow shots (hunter skill 4+).
HUNTER_BOW_RANGE: int = 5
HUNTER_BOW_MIN_SKILL: int = 4
HUNTER_BOW_HIT_CHANCE: float = 0.5

# Pull CSV clothing_slot overrides after recipes finish loading.
try:
    from recipes import CLOTHING_SLOT_FROM_CSV

    for _item, _slot in CLOTHING_SLOT_FROM_CSV.items():
        if _slot in CLOTHING_SLOTS:
            CLOTHING_ITEM_SLOT[_item] = _slot
    CLOTHING_KEYS = tuple(CLOTHING_ITEM_SLOT)  # type: ignore[misc]
except Exception:
    pass


def preferred_clothing_for_temp(temp_c: float) -> dict[str, tuple[str, ...]]:
    """Slot → preferred item keys (best first) for the current air temperature."""
    t = float(temp_c)
    if t <= 10.0:
        hat = ("winter_hat", "sun_hat")
        shirt = ("winter_coat", "light_shirt")
    elif t >= 22.0:
        hat = ("sun_hat", "winter_hat")
        shirt = ("light_shirt", "winter_coat")
    else:
        hat = ("sun_hat", "winter_hat")
        shirt = ("light_shirt", "winter_coat")
    return {
        "hat": hat,
        "shirt": shirt,
        "shoes": ("leather_shoes",),
        "bag": ("leather_satchel",),
    }


class TaskType(Enum):
    CHOP_TREES = auto()
    PLANT_SAPLINGS = auto()
    FULL_MANAGE = auto()
    COLLECT_ROCKS = auto()
    HUNT = auto()
    FISH = auto()
    FORAGE_MUSHROOMS = auto()
    FORAGE_BERRIES = auto()
    FORAGE_HERBS = auto()
    PLANT_BERRY_SEEDS = auto()
    PLANT_HERB_SEEDS = auto()
    FULL_FORAGE = auto()
    FARM_FIELD = auto()
    SPLIT_LOGS = auto()


TASK_LABELS: dict[TaskType, str] = {
    TaskType.CHOP_TREES: "Chop area",
    TaskType.PLANT_SAPLINGS: "Plant saplings",
    TaskType.FULL_MANAGE: "All",
    TaskType.COLLECT_ROCKS: "Collect rocks",
    TaskType.HUNT: "Hunt area",
    TaskType.FISH: "Fish area",
    TaskType.FORAGE_MUSHROOMS: "Forage mushrooms",
    TaskType.FORAGE_BERRIES: "Forage berries",
    TaskType.FORAGE_HERBS: "Forage plants",
    TaskType.PLANT_BERRY_SEEDS: "Plant berry seeds",
    TaskType.PLANT_HERB_SEEDS: "Plant herb seeds",
    TaskType.FULL_FORAGE: "Full forage",
    TaskType.FARM_FIELD: "Farm field",
    TaskType.SPLIT_LOGS: "Split logs",
}


class WorkMode(Enum):
    """Workplace behaviour: gather resources, plant, split, or all three."""

    COLLECT = auto()
    PLANT = auto()
    SPLIT = auto()
    ALL = auto()


WORK_MODE_LABELS: dict[WorkMode, str] = {
    WorkMode.COLLECT: "Collect",
    WorkMode.PLANT: "Plant",
    WorkMode.SPLIT: "Split",
    WorkMode.ALL: "All",
}

WORK_MODE_SHORT: dict[WorkMode, str] = {
    WorkMode.COLLECT: "C",
    WorkMode.PLANT: "P",
    WorkMode.SPLIT: "S",
    WorkMode.ALL: "A",
}

# Order used when cycling the behaviour toggle.
WORK_MODE_CYCLE_PLANTABLE: tuple[WorkMode, ...] = (
    WorkMode.COLLECT,
    WorkMode.PLANT,
    WorkMode.ALL,
)

WORK_MODE_CYCLE_FORESTER: tuple[WorkMode, ...] = (
    WorkMode.COLLECT,
    WorkMode.PLANT,
    WorkMode.SPLIT,
    WorkMode.ALL,
)

FORESTER_TASK_CYCLE: tuple[TaskType, ...] = (
    TaskType.CHOP_TREES,
    TaskType.PLANT_SAPLINGS,
    TaskType.FULL_MANAGE,
    TaskType.SPLIT_LOGS,
)

FORAGER_TASK_CYCLE: tuple[TaskType, ...] = (
    TaskType.FULL_FORAGE,
)


class BuildingKind(Enum):
    HOME = auto()
    WORKSTATION = auto()
    FORESTER = auto()
    MASON = auto()
    HUNTER = auto()
    FORAGER = auto()
    FISHER = auto()
    FARM = auto()
    FIELD = auto()
    MILL = auto()
    KITCHEN = auto()
    CRAFT_BENCH = auto()
    ALCHEMIST = auto()
    TAILOR = auto()
    COBBLER = auto()
    MARKET = auto()
    TENT = auto()
    HOUSE_SMALL = auto()  # 1×2
    HOUSE = auto()  # 2×2
    # 1×1 extensions (must be built adjacent to their parent workplace).
    BARN = auto()  # Farm
    PANTRY = auto()  # Kitchen
    DRYING_RACK = auto()  # Hunter


# Tool required in the equipped slot for workplace actions.
WORKPLACE_TOOL: dict[BuildingKind, str] = {
    BuildingKind.FORESTER: "axe",
    BuildingKind.HUNTER: "spear",
    BuildingKind.FISHER: "fishing_rod",
    BuildingKind.FARM: "hoe",
    BuildingKind.KITCHEN: "knife",
}

# Extra tools accepted for a workplace (in addition to WORKPLACE_TOOL).
WORKPLACE_EXTRA_TOOLS: dict[BuildingKind, tuple[str, ...]] = {
    BuildingKind.HUNTER: ("bow",),
}


BUILDING_LABELS: dict[BuildingKind, str] = {
    BuildingKind.HOME: "Storehouse",
    BuildingKind.WORKSTATION: "Hiring hall",
    BuildingKind.FORESTER: "Forester",
    BuildingKind.MASON: "Mason",
    BuildingKind.HUNTER: "Hunter",
    BuildingKind.FORAGER: "Forager",
    BuildingKind.FISHER: "Fisher",
    BuildingKind.FARM: "Farm",
    BuildingKind.FIELD: "Field",
    BuildingKind.MILL: "Mill",
    BuildingKind.KITCHEN: "Kitchen",
    BuildingKind.CRAFT_BENCH: "Craft bench",
    BuildingKind.ALCHEMIST: "Alchemist",
    BuildingKind.TAILOR: "Tailor",
    BuildingKind.COBBLER: "Cobbler",
    BuildingKind.MARKET: "Market",
    BuildingKind.TENT: "Tent",
    BuildingKind.HOUSE_SMALL: "Cottage",
    BuildingKind.HOUSE: "House",
    BuildingKind.BARN: "Barn",
    BuildingKind.PANTRY: "Pantry",
    BuildingKind.DRYING_RACK: "Drying rack",
}


def default_building_plot(kind: BuildingKind) -> tuple[int, int]:
    """Default footprint size. Fields are drag-sized; housing uses custom plots."""
    if kind == BuildingKind.FIELD:
        return 1, 1
    if kind in (
        BuildingKind.TENT,
        BuildingKind.BARN,
        BuildingKind.PANTRY,
        BuildingKind.DRYING_RACK,
    ):
        return 1, 1
    if kind == BuildingKind.HOUSE_SMALL:
        return 1, 2
    if kind == BuildingKind.HOUSE:
        return 2, 2
    n = max(1, int(BUILDING_FOOTPRINT))
    return n, n


def default_building_storage(kind: BuildingKind) -> BuildingStorageSpec:
    """Storage pools from ``settings.BUILDING_STORAGE`` for this kind."""
    return building_storage_spec(kind.name)


def default_processor_capacities(kind: BuildingKind) -> tuple[int, int, int]:
    """Return (capacity, input_capacity, output_capacity) for a new building."""
    spec = default_building_storage(kind)
    return spec.capacity, spec.input_capacity, spec.output_capacity


def apply_building_storage(building: Building) -> None:
    """Apply central storage specs onto ``building`` (settings are source of truth)."""
    spec = default_building_storage(building.kind)
    building.capacity = spec.capacity
    building.input_capacity = spec.input_capacity
    building.output_capacity = spec.output_capacity
    building.fuel_capacity = spec.fuel_capacity
    building.seed_capacity = spec.seed_capacity


def default_item_mins(kind: BuildingKind) -> dict[str, int]:
    if kind == BuildingKind.FORESTER:
        return {
            "logs": FORESTER_DEFAULT_LOGS_MIN,
            "hardwood_logs": FORESTER_DEFAULT_HARDWOOD_LOGS_MIN,
        }
    return {}


class VillagerState(Enum):
    IDLE = auto()
    WORKING = auto()
    DELIVERING = auto()
    HAULING = auto()
    BUILDING = auto()
    SLEEPING = auto()


class WorkPriority(Enum):
    BUILD = auto()
    TRANSPORT = auto()
    WORKPLACE = auto()
    NONE = auto()


PRIORITY_LABELS: dict[WorkPriority, str] = {
    WorkPriority.BUILD: "Build",
    WorkPriority.TRANSPORT: "Transport",
    WorkPriority.WORKPLACE: "Workplace",
    WorkPriority.NONE: "—",
}

PRIORITY_CYCLE: tuple[WorkPriority, ...] = (
    WorkPriority.BUILD,
    WorkPriority.TRANSPORT,
    WorkPriority.WORKPLACE,
    WorkPriority.NONE,
)

PRIORITY_ICONS: dict[WorkPriority, str] = {
    WorkPriority.BUILD: "construction_site",
    WorkPriority.TRANSPORT: "storehouse",
    WorkPriority.WORKPLACE: "forager",
    WorkPriority.NONE: "",
}


class RationMode(Enum):
    """How aggressively a villager tops up satiation."""

    HALF = auto()
    NORMAL = auto()
    DOUBLE = auto()


RATION_LABELS: dict[RationMode, str] = {
    RationMode.HALF: "½",
    RationMode.NORMAL: "×1",
    RationMode.DOUBLE: "×2",
}

RATION_CYCLE: tuple[RationMode, ...] = (
    RationMode.HALF,
    RationMode.NORMAL,
    RationMode.DOUBLE,
)

# Eat when satiation falls to this level.
RATION_EAT_AT: dict[RationMode, float] = {
    RationMode.HALF: 0.25,
    RationMode.NORMAL: 0.50,
    RationMode.DOUBLE: 0.50,
}

# Satiation after a successful meal.
RATION_REFILL: dict[RationMode, float] = {
    RationMode.HALF: 0.50,
    RationMode.NORMAL: 0.75,
    RationMode.DOUBLE: 1.00,
}

RATION_FOOD_AMOUNT: dict[RationMode, int] = {
    RationMode.HALF: 1,
    RationMode.NORMAL: 1,
    RationMode.DOUBLE: 2,
}

DEFAULT_PRIORITIES_UNASSIGNED: tuple[WorkPriority, ...] = (
    WorkPriority.BUILD,
    WorkPriority.TRANSPORT,
    WorkPriority.NONE,
)

DEFAULT_PRIORITIES_WORKPLACE: tuple[WorkPriority, ...] = (
    WorkPriority.WORKPLACE,
    WorkPriority.TRANSPORT,
    WorkPriority.NONE,
)

DEFAULT_PRIORITIES_HOME: tuple[WorkPriority, ...] = (
    WorkPriority.TRANSPORT,
    WorkPriority.BUILD,
    WorkPriority.NONE,
)


@dataclass
class Inventory:
    logs: int = 0
    hardwood_logs: int = 0
    wood: int = 0
    rock: int = 0
    meat: int = 0
    fish: int = 0
    oak_saplings: int = 0
    maple_saplings: int = 0
    pine_saplings: int = 0
    cedar_saplings: int = 0
    mushrooms: int = 0
    honey: int = 0
    berries: int = 0
    berry_seeds: int = 0
    reeds: int = 0
    straw: int = 0
    fur: int = 0
    hide: int = 0
    leather: int = 0
    wheat: int = 0
    flax: int = 0
    sage: int = 0
    mint: int = 0
    hemp: int = 0
    rye: int = 0
    onion: int = 0
    cabbage: int = 0
    carrot: int = 0
    garlic: int = 0
    wheat_seeds: int = 0
    flax_seeds: int = 0
    sage_seeds: int = 0
    mint_seeds: int = 0
    hemp_seeds: int = 0
    rye_seeds: int = 0
    onion_seeds: int = 0
    cabbage_seeds: int = 0
    carrot_seeds: int = 0
    garlic_seeds: int = 0
    wheat_flour: int = 0
    rye_flour: int = 0
    bread: int = 0
    stew: int = 0
    fish_stew: int = 0
    mushroom_stew: int = 0
    grilled_meat: int = 0
    grilled_fish: int = 0
    twine: int = 0
    coins: int = 0
    axe: int = 0
    spear: int = 0
    fishing_rod: int = 0
    hoe: int = 0
    knife: int = 0
    bow: int = 0
    equipped_tools: list[str] = field(default_factory=list)
    # Clothing slot → equipped item key (at most one item per slot).
    equipped_clothing: dict[str, str] = field(default_factory=dict)
    capacity: int = INVENTORY_CAPACITY
    seed_capacity: int = SEED_CARRY_CAPACITY

    @staticmethod
    def clothing_slot_for(key: str) -> str | None:
        return CLOTHING_ITEM_SLOT.get(key)

    @property
    def gear_walk_mult(self) -> float:
        """Walk speed multiplier from equipped shoes (and future gear)."""
        from recipes import clothing_walk_mult

        mult = 1.0
        for key in self.equipped_clothing.values():
            mult *= clothing_walk_mult(key)
        return max(0.1, mult)

    @property
    def gear_capacity_bonus(self) -> int:
        from recipes import clothing_capacity_bonus

        bonus = 0
        for key in self.equipped_clothing.values():
            bonus += clothing_capacity_bonus(key)
        return max(0, bonus)

    @property
    def gear_heat_protection(self) -> float:
        from recipes import clothing_heat_protection

        return sum(
            clothing_heat_protection(key) for key in self.equipped_clothing.values()
        )

    @property
    def gear_cold_protection(self) -> float:
        from recipes import clothing_cold_protection

        return sum(
            clothing_cold_protection(key) for key in self.equipped_clothing.values()
        )

    @property
    def effective_capacity(self) -> int:
        return max(1, int(self.capacity) + self.gear_capacity_bonus)

    @staticmethod
    def is_seed_key(key: str) -> bool:
        return key in SEED_ITEM_KEYS

    @staticmethod
    def is_sapling_key(key: str) -> bool:
        return key in SAPLING_ITEM_KEYS

    @property
    def saplings(self) -> int:
        """Total saplings across all tree species."""
        return sum(getattr(self, key, 0) for key in SAPLING_ITEM_KEYS)

    def first_sapling_key(self) -> str | None:
        for key in SAPLING_ITEM_KEYS:
            if getattr(self, key, 0) > 0:
                return key
        return None

    @property
    def seed_total(self) -> int:
        return sum(getattr(self, key) for key in SEED_ITEM_KEYS)

    @property
    def cargo_total(self) -> int:
        """Non-seed items (wood, food, saplings, produce, …)."""
        from resources import stack_units

        total = (
            self.logs
            + self.hardwood_logs
            + self.wood
            + self.rock
            + self.meat
            + self.fish
            + self.saplings
            + self.mushrooms
            + self.honey
            + self.berries
            + self.reeds
            + self.straw
            + self.fur
            + self.hide
            + self.leather
            + self.twine
            + sum(int(getattr(self, key, 0)) for key in TOOL_KEYS)
            + sum(getattr(self, key) for key in PRODUCE_KEYS)
        )
        for key in PROCESSED_KEYS:
            if key in TOOL_KEYS:
                continue
            total += stack_units(key, int(getattr(self, key, 0)))
        return total

    @property
    def total(self) -> int:
        # Coins are currency: carried, but they do not consume cargo capacity.
        return self.cargo_total + self.seed_total + self.coins

    @property
    def is_full(self) -> bool:
        """True when general cargo is full (seeds use a separate pool)."""
        return self.cargo_total >= self.effective_capacity

    @property
    def seeds_full(self) -> bool:
        return self.seed_total >= self.seed_capacity

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    def can_add(self, amount: int = 1, key: str | None = None) -> bool:
        if key == "coins":
            return True
        if key is not None and self.is_seed_key(key):
            return self.seed_total + amount <= self.seed_capacity
        cap = self.effective_capacity
        if key is not None:
            from resources import cargo_units_after_add, stack_size

            if stack_size(key) is not None:
                have = int(getattr(self, key, 0))
                return self.cargo_total + cargo_units_after_add(key, have, amount) <= cap
        return self.cargo_total + amount <= cap

    def add_item(self, key: str, n: int = 1) -> bool:
        if not hasattr(self, key) or not self.can_add(n, key=key):
            return False
        setattr(self, key, getattr(self, key) + n)
        return True

    def consume_item(self, key: str, n: int = 1) -> bool:
        if getattr(self, key, 0) < n:
            return False
        setattr(self, key, getattr(self, key) - n)
        return True

    def add_logs(self, n: int = 1) -> bool:
        return self.add_item("logs", n)

    def add_hardwood_logs(self, n: int = 1) -> bool:
        return self.add_item("hardwood_logs", n)

    def add_wood(self, n: int = 1) -> bool:
        return self.add_item("wood", n)

    def add_rock(self, n: int = 1) -> bool:
        return self.add_item("rock", n)

    def add_meat(self, n: int = 1) -> bool:
        return self.add_item("meat", n)

    def add_fish(self, n: int = 1) -> bool:
        return self.add_item("fish", n)

    def add_saplings(self, n: int = 1, species: str | None = None) -> bool:
        return self.add_item(sapling_item_key(species), n)

    def add_mushrooms(self, n: int = 1) -> bool:
        return self.add_item("mushrooms", n)

    def add_berries(self, n: int = 1) -> bool:
        return self.add_item("berries", n)

    def add_berry_seeds(self, n: int = 1) -> bool:
        return self.add_item("berry_seeds", n)

    def add_herbs(self, n: int = 1) -> bool:
        return self.add_item("sage", n)

    def add_herb_seeds(self, n: int = 1) -> bool:
        return self.add_item("sage_seeds", n)

    def consume_sapling(self, species: str | None = None) -> bool:
        if species is not None:
            return self.consume_item(sapling_item_key(species), 1)
        key = self.first_sapling_key()
        if key is None:
            return False
        return self.consume_item(key, 1)

    def consume_berry_seed(self) -> bool:
        return self.consume_item("berry_seeds", 1)

    def consume_herb_seed(self) -> bool:
        return self.consume_item("sage_seeds", 1)

    @property
    def equipped_tool(self) -> str | None:
        """First equipped tool (compat)."""
        return self.equipped_tools[0] if self.equipped_tools else None

    @equipped_tool.setter
    def equipped_tool(self, key: str | None) -> None:
        if key is None:
            self.equipped_tools.clear()
        elif key in TOOL_KEYS:
            self.equipped_tools = [key]

    def has_equipped_tool(self, key: str) -> bool:
        return key in self.equipped_tools

    def tool_slots_free(self) -> int:
        return max(0, TOOL_SLOT_MAX - len(self.equipped_tools))

    def can_equip_tool(self, key: str) -> bool:
        return (
            key in TOOL_KEYS
            and key not in self.equipped_tools
            and self.tool_slots_free() > 0
            and int(getattr(self, key, 0)) > 0
        )

    def equip_tool(self, key: str) -> bool:
        if not self.can_equip_tool(key):
            return False
        setattr(self, key, getattr(self, key) - 1)
        self.equipped_tools.append(key)
        return True

    def unequip_tool(self, key: str | None = None) -> bool:
        if not self.equipped_tools:
            return False
        if key is not None and key in self.equipped_tools:
            tool = key
        else:
            tool = self.equipped_tools[-1]
        if not self.can_add(1, key=tool):
            return False
        self.equipped_tools.remove(tool)
        setattr(self, tool, getattr(self, tool) + 1)
        return True

    def equip_tool_from_transfer(self, key: str) -> bool:
        """Equip a tool moved directly into a slot (e.g. from storehouse)."""
        if (
            key not in TOOL_KEYS
            or key in self.equipped_tools
            or self.tool_slots_free() <= 0
        ):
            return False
        self.equipped_tools.append(key)
        return True

    def transfer_equipped_tool_to(self, other: Inventory, key: str | None = None) -> bool:
        if not self.equipped_tools:
            return False
        if key is not None and key in self.equipped_tools:
            tool = key
        else:
            tool = self.equipped_tools[0]
        if not other.can_add(1, key=tool):
            return False
        self.equipped_tools.remove(tool)
        other.add_item(tool, 1)
        return True

    def try_equip_work_tools(self) -> bool:
        """Move tools from cargo into empty slots."""
        for key in TOOL_KEYS:
            if self.equip_tool(key):
                return True
        return False

    def equipped_in_slot(self, slot: str) -> str | None:
        return self.equipped_clothing.get(slot)

    def can_equip_clothing(self, key: str) -> bool:
        slot = CLOTHING_ITEM_SLOT.get(key)
        if slot is None or slot not in CLOTHING_SLOTS:
            return False
        if int(getattr(self, key, 0)) <= 0:
            return False
        # Already wearing this exact item instance path: cargo must have a spare.
        return True

    def equip_clothing(self, key: str) -> bool:
        """Equip clothing from cargo into its slot (unequips prior item in that slot)."""
        slot = CLOTHING_ITEM_SLOT.get(key)
        if slot is None or int(getattr(self, key, 0)) <= 0:
            return False
        current = self.equipped_clothing.get(slot)
        if current == key:
            # Already wearing one; need another in cargo to "re-equip" — no-op.
            return False
        if current is not None:
            # Unequip first — must fit in cargo after removing the new item from cargo.
            # Temporarily move new item out of cargo, unequip old, then put new in slot.
            setattr(self, key, getattr(self, key) - 1)
            if not self.can_add(1, key=current):
                setattr(self, key, getattr(self, key) + 1)
                return False
            setattr(self, current, getattr(self, current) + 1)
            self.equipped_clothing[slot] = key
            return True
        setattr(self, key, getattr(self, key) - 1)
        self.equipped_clothing[slot] = key
        return True

    def equip_clothing_from_transfer(self, key: str) -> bool:
        """Equip clothing that was transferred directly (not currently in cargo)."""
        slot = CLOTHING_ITEM_SLOT.get(key)
        if slot is None or slot not in CLOTHING_SLOTS:
            return False
        current = self.equipped_clothing.get(slot)
        if current == key:
            return True
        if current is not None:
            if not self.can_add(1, key=current):
                return False
            setattr(self, current, getattr(self, current) + 1)
        self.equipped_clothing[slot] = key
        return True

    def unequip_clothing(self, slot_or_key: str) -> bool:
        """Unequip by slot name or item key back into cargo."""
        slot = slot_or_key
        key = self.equipped_clothing.get(slot)
        if key is None and slot_or_key in CLOTHING_ITEM_SLOT:
            key = slot_or_key
            slot = CLOTHING_ITEM_SLOT[key]
            if self.equipped_clothing.get(slot) != key:
                return False
        if key is None or slot not in self.equipped_clothing:
            return False
        if not self.can_add(1, key=key):
            return False
        del self.equipped_clothing[slot]
        setattr(self, key, getattr(self, key) + 1)
        return True

    def has_delivery_cargo(self) -> bool:
        """Cargo worth delivering — loose tools stay on the worker."""
        cargo = self.cargo_total
        for key in TOOL_KEYS:
            cargo -= int(getattr(self, key, 0))
        return cargo > 0 or self.seed_total > 0 or self.coins > 0

    def clear(self) -> dict[str, int]:
        saved_tools = list(self.equipped_tools)
        saved_clothing = dict(self.equipped_clothing)
        deposited = {
            "logs": self.logs,
            "hardwood_logs": self.hardwood_logs,
            "wood": self.wood,
            "rock": self.rock,
            "meat": self.meat,
            "fish": self.fish,
            "mushrooms": self.mushrooms,
            "honey": self.honey,
            "berries": self.berries,
            "berry_seeds": self.berry_seeds,
            "reeds": self.reeds,
            "straw": self.straw,
            "fur": self.fur,
            "hide": self.hide,
            "leather": self.leather,
            "twine": self.twine,
            "coins": self.coins,
            **{key: int(getattr(self, key, 0)) for key in TOOL_KEYS},
            **{key: getattr(self, key) for key in SAPLING_ITEM_KEYS},
            **{key: getattr(self, key) for key in PRODUCE_KEYS},
            **{key: getattr(self, key) for key in SEED_KEYS},
            **{
                key: getattr(self, key)
                for key in PROCESSED_KEYS
                if key not in TOOL_KEYS
            },
        }
        self.reset()
        self.equipped_tools = saved_tools
        self.equipped_clothing = saved_clothing
        return deposited

    def reset(self) -> None:
        self.logs = self.hardwood_logs = self.wood = self.rock = self.meat = self.fish = 0
        self.mushrooms = self.honey = self.berries = self.berry_seeds = self.reeds = 0
        self.straw = self.fur = self.hide = self.leather = 0
        self.twine = self.coins = 0
        for key in TOOL_KEYS:
            setattr(self, key, 0)
        self.equipped_tools.clear()
        self.equipped_clothing.clear()
        for key in SAPLING_ITEM_KEYS + PRODUCE_KEYS + SEED_KEYS + PROCESSED_KEYS:
            setattr(self, key, 0)


@dataclass
class HomeStorage:
    logs: int = 0
    hardwood_logs: int = 0
    wood: int = 0
    rock: int = 0
    meat: int = 0
    fish: int = 0
    oak_saplings: int = 0
    maple_saplings: int = 0
    pine_saplings: int = 0
    cedar_saplings: int = 0
    mushrooms: int = 0
    honey: int = 0
    berries: int = 0
    berry_seeds: int = 0
    reeds: int = 0
    straw: int = 0
    fur: int = 0
    hide: int = 0
    leather: int = 0
    wheat: int = 0
    flax: int = 0
    sage: int = 0
    mint: int = 0
    hemp: int = 0
    rye: int = 0
    onion: int = 0
    cabbage: int = 0
    carrot: int = 0
    garlic: int = 0
    wheat_seeds: int = 0
    flax_seeds: int = 0
    sage_seeds: int = 0
    mint_seeds: int = 0
    hemp_seeds: int = 0
    rye_seeds: int = 0
    onion_seeds: int = 0
    cabbage_seeds: int = 0
    carrot_seeds: int = 0
    garlic_seeds: int = 0
    wheat_flour: int = 0
    rye_flour: int = 0
    bread: int = 0
    stew: int = 0
    fish_stew: int = 0
    mushroom_stew: int = 0
    grilled_meat: int = 0
    grilled_fish: int = 0
    twine: int = 0
    coins: int = 0
    axe: int = 0
    spear: int = 0
    fishing_rod: int = 0
    hoe: int = 0
    knife: int = 0
    bow: int = 0

    @property
    def saplings(self) -> int:
        return sum(getattr(self, key, 0) for key in SAPLING_ITEM_KEYS)

    def deposit_dict(self, items: dict[str, int]) -> None:
        for key, value in items.items():
            if key == "saplings":
                # Legacy generic saplings → oak.
                self.oak_saplings += int(value)
                continue
            if hasattr(self, key):
                setattr(self, key, getattr(self, key) + value)

    def deposit(self, wood: int = 0, rock: int = 0, meat: int = 0, saplings: int = 0, **extra) -> None:
        self.logs += wood
        self.rock += rock
        self.meat += meat
        if saplings:
            self.oak_saplings += saplings
        for key, value in extra.items():
            if key == "saplings":
                self.oak_saplings += int(value)
            elif hasattr(self, key):
                setattr(self, key, getattr(self, key) + value)

    def try_spend(self, wood: int, rock: int) -> bool:
        if self.logs < wood or self.rock < rock:
            return False
        self.logs -= wood
        self.rock -= rock
        return True

    def reset(self) -> None:
        self.logs = self.hardwood_logs = self.wood = self.rock = self.meat = self.fish = 0
        self.mushrooms = self.honey = self.berries = self.berry_seeds = self.reeds = 0
        self.straw = self.fur = self.hide = self.leather = 0
        self.twine = self.coins = 0
        for key in TOOL_KEYS:
            setattr(self, key, 0)
        for key in SAPLING_ITEM_KEYS + PRODUCE_KEYS + SEED_KEYS + PROCESSED_KEYS:
            setattr(self, key, 0)

    def withdraw_keys_to(self, inventory: Inventory, keys: tuple[str, ...]) -> int:
        taken = 0
        for key in keys:
            taken += self.withdraw_key_to(inventory, key)
        return taken

    def withdraw_amounts_to(
        self, inventory: Inventory, amounts: dict[str, int]
    ) -> int:
        """Move up to ``amounts[key]`` of each key, round-robin so no key hogs the pack."""
        if not amounts:
            return 0
        remaining = {k: max(0, int(n)) for k, n in amounts.items() if int(n) > 0}
        taken = 0
        progressed = True
        while progressed and remaining:
            progressed = False
            for key in list(remaining):
                if remaining[key] <= 0:
                    remaining.pop(key, None)
                    continue
                if getattr(self, key, 0) <= 0 or not inventory.can_add(1, key=key):
                    remaining.pop(key, None)
                    continue
                setattr(self, key, getattr(self, key) - 1)
                setattr(inventory, key, getattr(inventory, key) + 1)
                remaining[key] -= 1
                taken += 1
                progressed = True
                if remaining[key] <= 0:
                    remaining.pop(key, None)
        return taken

    def withdraw_key_to(self, inventory: Inventory, key: str) -> int:
        """Move as much of ``key`` as inventory capacity allows."""
        if not hasattr(self, key) or not hasattr(inventory, key):
            return 0
        taken = 0
        while getattr(self, key, 0) > 0 and inventory.can_add(1, key=key):
            setattr(self, key, getattr(self, key) - 1)
            setattr(inventory, key, getattr(inventory, key) + 1)
            taken += 1
        return taken

    def withdraw_one_to(self, inventory: Inventory, key: str) -> bool:
        """Move a single unit of ``key`` into inventory if possible."""
        if not hasattr(self, key) or not hasattr(inventory, key):
            return False
        if getattr(self, key, 0) <= 0 or not inventory.can_add(1, key=key):
            return False
        setattr(self, key, getattr(self, key) - 1)
        setattr(inventory, key, getattr(inventory, key) + 1)
        return True

    def deposit_key_from(self, inventory: Inventory, key: str) -> int:
        """Move all of ``key`` from inventory into storehouse."""
        if not hasattr(self, key) or not hasattr(inventory, key):
            return 0
        n = int(getattr(inventory, key, 0))
        if n <= 0:
            return 0
        setattr(inventory, key, 0)
        setattr(self, key, getattr(self, key) + n)
        return n

    def deposit_one_from(self, inventory: Inventory, key: str) -> bool:
        """Move a single unit of ``key`` from inventory into storehouse."""
        if not hasattr(self, key) or not hasattr(inventory, key):
            return False
        if getattr(inventory, key, 0) <= 0:
            return False
        setattr(inventory, key, getattr(inventory, key) - 1)
        setattr(self, key, getattr(self, key) + 1)
        return True


@dataclass
class TaskArea:
    x0: int
    y0: int
    x1: int
    y1: int
    task_type: TaskType
    building_id: int

    def normalised(self) -> tuple[int, int, int, int]:
        return (
            min(self.x0, self.x1),
            min(self.y0, self.y1),
            max(self.x0, self.x1),
            max(self.y0, self.y1),
        )

    def contains(self, x: int, y: int) -> bool:
        left, top, right, bottom = self.normalised()
        return left <= x <= right and top <= y <= bottom

    def cells(self) -> list[tuple[int, int]]:
        left, top, right, bottom = self.normalised()
        return [(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)]

    def size_label(self) -> str:
        left, top, right, bottom = self.normalised()
        return f"{right - left + 1}×{bottom - top + 1}"


@dataclass
class CropPlan:
    """Sub-area inside a FarmField planted to one crop with a seasonal calendar."""

    id: int
    x0: int
    y0: int
    x1: int
    y1: int
    crop_kind: str
    field_id: int

    def normalised(self) -> tuple[int, int, int, int]:
        return (
            min(self.x0, self.x1),
            min(self.y0, self.y1),
            max(self.x0, self.x1),
            max(self.y0, self.y1),
        )

    def contains(self, x: int, y: int) -> bool:
        left, top, right, bottom = self.normalised()
        return left <= x <= right and top <= y <= bottom

    def cells(self) -> list[tuple[int, int]]:
        left, top, right, bottom = self.normalised()
        return [(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)]

    def clip_to(self, bounds: tuple[int, int, int, int]) -> None:
        bl, bt, br, bb = bounds
        left, top, right, bottom = self.normalised()
        left = max(left, bl)
        top = max(top, bt)
        right = min(right, br)
        bottom = min(bottom, bb)
        self.x0, self.y0, self.x1, self.y1 = left, top, right, bottom

    def is_empty(self) -> bool:
        left, top, right, bottom = self.normalised()
        return left > right or top > bottom


def _rect_subtract(
    outer: tuple[int, int, int, int],
    cut: tuple[int, int, int, int],
) -> list[tuple[int, int, int, int]]:
    """Return axis-aligned rects covering outer − cut (both normalised)."""
    ol, ot, or_, ob = outer
    cl, ct, cr, cb = cut
    # No overlap
    if cr < ol or cl > or_ or cb < ot or ct > ob:
        return [outer]
    # Clip cut to outer
    cl = max(cl, ol)
    ct = max(ct, ot)
    cr = min(cr, or_)
    cb = min(cb, ob)
    parts: list[tuple[int, int, int, int]] = []
    # Top strip
    if ct > ot:
        parts.append((ol, ot, or_, ct - 1))
    # Bottom strip
    if cb < ob:
        parts.append((ol, cb + 1, or_, ob))
    # Middle left
    if cl > ol:
        parts.append((ol, ct, cl - 1, cb))
    # Middle right
    if cr < or_:
        parts.append((cr + 1, ct, or_, cb))
    return parts


def _cells_to_rects(cells: set[tuple[int, int]]) -> list[tuple[int, int, int, int]]:
    """Pack cells into a short list of inclusive bounding rectangles (row runs)."""
    if not cells:
        return []
    by_row: dict[int, list[int]] = {}
    for x, y in cells:
        by_row.setdefault(y, []).append(x)
    rects: list[tuple[int, int, int, int]] = []
    for y, xs in sorted(by_row.items()):
        xs.sort()
        run_start = xs[0]
        prev = xs[0]
        for x in xs[1:]:
            if x == prev + 1:
                prev = x
                continue
            rects.append((run_start, y, prev, y))
            run_start = x
            prev = x
        rects.append((run_start, y, prev, y))
    # Merge vertically adjacent identical x-ranges.
    merged: list[tuple[int, int, int, int]] = []
    for rect in rects:
        if (
            merged
            and merged[-1][0] == rect[0]
            and merged[-1][2] == rect[2]
            and merged[-1][3] + 1 == rect[1]
        ):
            pl, pt, pr, _pb = merged[-1]
            merged[-1] = (pl, pt, pr, rect[3])
        else:
            merged.append(rect)
    return merged


@dataclass
class FarmField:
    """Legacy nested field plot (migrated to standalone Field buildings on load)."""

    id: int
    x0: int
    y0: int
    x1: int
    y1: int
    name: str = ""
    plans: list[CropPlan] = field(default_factory=list)

    def normalised(self) -> tuple[int, int, int, int]:
        return (
            min(self.x0, self.x1),
            min(self.y0, self.y1),
            max(self.x0, self.x1),
            max(self.y0, self.y1),
        )

    def contains(self, x: int, y: int) -> bool:
        left, top, right, bottom = self.normalised()
        return left <= x <= right and top <= y <= bottom

    def cells(self) -> list[tuple[int, int]]:
        left, top, right, bottom = self.normalised()
        return [(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)]

    def size_label(self) -> str:
        left, top, right, bottom = self.normalised()
        return f"{right - left + 1}×{bottom - top + 1}"

    def display_name(self) -> str:
        return self.name or f"Field {self.id}"

    def plan_at(self, x: int, y: int) -> CropPlan | None:
        """Innermost / latest plan covering the cell."""
        hit: CropPlan | None = None
        for plan in self.plans:
            if plan.contains(x, y):
                hit = plan
        return hit


_FORAGE_KEYS = ("mushrooms", "berries", "berry_seeds", "reeds", "honey") + PRODUCE_KEYS + SEED_KEYS


RECIPE_PRIORITY_MIN = 1
RECIPE_PRIORITY_MAX = 3
RECIPE_PRIORITY_DEFAULT = 1
# New kitchen buildings: stews highest, grill lowest (override per recipe in UI).
_KITCHEN_CATEGORY_PRIORITY: dict[str, int] = {
    "stews": 1,
    "bakery": 2,
    "sweet": 2,
    "grill": 3,
}


@dataclass
class Building:
    id: int
    kind: BuildingKind
    x: int
    y: int
    logs: int = 0
    hardwood_logs: int = 0
    wood: int = 0
    rock: int = 0
    meat: int = 0
    fish: int = 0
    oak_saplings: int = 0
    maple_saplings: int = 0
    pine_saplings: int = 0
    cedar_saplings: int = 0
    mushrooms: int = 0
    honey: int = 0
    berries: int = 0
    berry_seeds: int = 0
    reeds: int = 0
    straw: int = 0
    fur: int = 0
    hide: int = 0
    leather: int = 0
    wheat: int = 0
    flax: int = 0
    sage: int = 0
    mint: int = 0
    hemp: int = 0
    rye: int = 0
    onion: int = 0
    cabbage: int = 0
    carrot: int = 0
    garlic: int = 0
    wheat_seeds: int = 0
    flax_seeds: int = 0
    sage_seeds: int = 0
    mint_seeds: int = 0
    hemp_seeds: int = 0
    rye_seeds: int = 0
    onion_seeds: int = 0
    cabbage_seeds: int = 0
    carrot_seeds: int = 0
    garlic_seeds: int = 0
    wheat_flour: int = 0
    rye_flour: int = 0
    bread: int = 0
    stew: int = 0
    fish_stew: int = 0
    mushroom_stew: int = 0
    grilled_meat: int = 0
    grilled_fish: int = 0
    twine: int = 0
    coins: int = 0
    axe: int = 0
    spear: int = 0
    fishing_rod: int = 0
    hoe: int = 0
    knife: int = 0
    bow: int = 0
    capacity: int = BUILDING_STORAGE_CAPACITY
    # Processor buildings use split pools (0 = unused / fall back to capacity).
    input_capacity: int = 0
    output_capacity: int = 0
    fuel_capacity: int = 0
    # Separate seed pool (farm / forager); 0 = seeds share ``capacity``.
    seed_capacity: int = 0
    fuel_wood: int = 0
    # Per-resource stock limits (omit key = unlimited within the pool).
    item_caps: dict[str, int] = field(default_factory=dict)
    # Minimum stock haulers must leave for recipes / splitting.
    item_mins: dict[str, int] = field(default_factory=dict)
    # recipe name → enabled; progress steps toward PROCESSOR_RECIPE_STEPS.
    recipe_enabled: dict[str, bool] = field(default_factory=dict)
    recipe_progress: dict[str, int] = field(default_factory=dict)
    # recipe name → priority 1 (highest) … 3 (lowest). Default 2.
    recipe_priority: dict[str, int] = field(default_factory=dict)
    areas: list[TaskArea] = field(default_factory=list)
    fields: list[FarmField] = field(default_factory=list)  # legacy; migrated away
    # Standalone Field plot size (origin at x,y) and crop plans.
    plot_w: int = 1
    plot_h: int = 1
    plans: list[CropPlan] = field(default_factory=list)
    # Field only: cumulative crop health 0–1; ratchets down on env sample ticks.
    crop_health: float = 1.0
    # Field only: additive pest-control boost from alchemist treatments.
    pest_boost: float = 0.0
    # Market: seasonal buyer demand and player-committed sell quotas.
    market_demand: dict[str, int] = field(default_factory=dict)
    # Enabled supply goods → storehouse reserve (units kept; surplus may sell).
    # Mins persist across seasons while the entry remains enabled.
    market_supply_mins: dict[str, int] = field(default_factory=dict)
    # Enabled supply goods → units to keep stocked at the market stall.
    # 0 means fill up to remaining seasonal demand.
    market_supply_stocks: dict[str, int] = field(default_factory=dict)
    market_demand_season: str | None = None
    draw_task_type: TaskType = TaskType.FULL_MANAGE
    work_mode: WorkMode = WorkMode.ALL
    crop_kind: str = "sage"  # legacy
    next_field_id: int = 1
    next_plan_id: int = 1
    # Extension annexes: parent link (on the extension) and attached kinds (on parent).
    parent_building_id: int | None = None
    linked_extensions: frozenset[BuildingKind] = field(default_factory=frozenset)

    @property
    def saplings(self) -> int:
        return sum(getattr(self, key, 0) for key in SAPLING_ITEM_KEYS)

    def plot_bounds(self) -> tuple[int, int, int, int]:
        w = max(1, self.plot_w)
        h = max(1, self.plot_h)
        return self.x, self.y, self.x + w - 1, self.y + h - 1

    def contains_plot(self, x: int, y: int) -> bool:
        left, top, right, bottom = self.plot_bounds()
        return left <= x <= right and top <= y <= bottom

    def plot_cells(self) -> list[tuple[int, int]]:
        left, top, right, bottom = self.plot_bounds()
        return [(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)]

    def center_cell(self) -> tuple[int, int]:
        left, top, right, bottom = self.plot_bounds()
        return (left + right) // 2, (top + bottom) // 2

    def plot_size_label(self) -> str:
        return f"{max(1, self.plot_w)}×{max(1, self.plot_h)}"

    def plan_covering(self, x: int, y: int) -> CropPlan | None:
        """Latest plan covering the cell (Field buildings)."""
        hit: CropPlan | None = None
        for plan in self.plans:
            if plan.contains(x, y):
                hit = plan
        return hit

    def plans_covering(self, x: int, y: int) -> list[CropPlan]:
        return [plan for plan in self.plans if plan.contains(x, y)]

    def add_field_plan(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        crop_kind: str,
        *,
        cell_planted: object | None = None,
    ) -> CropPlan | None:
        """Paint a crop plan. Compatible rotation plans stack on the same cells.

        Existing coverage is only carved away when schedules conflict (same plant
        season, same harvest season, or grow clash). Harvest+plant in one season
        is allowed so sage→cabbage→rye rotations can share an area.
        ``cell_planted`` is accepted for callers but no longer drives removal.
        """
        del cell_planted  # kept for call-site compatibility
        if self.kind != BuildingKind.FIELD:
            return None
        from crops import CROP_BY_KEY, schedules_conflict

        new_crop = CROP_BY_KEY.get(crop_kind, CROP_BY_KEY["sage"])
        draft = CropPlan(
            id=0,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            crop_kind=crop_kind,
            field_id=self.id,
        )
        draft.clip_to(self.plot_bounds())
        if draft.is_empty():
            return None

        paint_cells = set(draft.cells())
        # Only remove cells from plans that cannot coexist with the new crop.
        replace_by_plan: dict[int, set[tuple[int, int]]] = {}
        for plan in self.plans:
            old_crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
            if not schedules_conflict(old_crop, new_crop):
                continue
            overlap = {cell for cell in plan.cells() if cell in paint_cells}
            if overlap:
                replace_by_plan[plan.id] = overlap

        if replace_by_plan:
            replace_cells = set().union(*replace_by_plan.values())
            rebuilt: list[CropPlan] = []
            for plan in self.plans:
                cut = replace_by_plan.get(plan.id)
                if not cut:
                    rebuilt.append(plan)
                    continue
                remaining = {cell for cell in plan.cells() if cell not in cut}
                if not remaining:
                    continue
                for rect in _cells_to_rects(remaining):
                    rebuilt.append(
                        CropPlan(
                            id=self.next_plan_id,
                            x0=rect[0],
                            y0=rect[1],
                            x1=rect[2],
                            y1=rect[3],
                            crop_kind=plan.crop_kind,
                            field_id=self.id,
                        )
                    )
                    self.next_plan_id += 1
            self.plans = rebuilt

        created: CropPlan | None = None
        for rect in _cells_to_rects(paint_cells):
            plan = CropPlan(
                id=self.next_plan_id,
                x0=rect[0],
                y0=rect[1],
                x1=rect[2],
                y1=rect[3],
                crop_kind=crop_kind,
                field_id=self.id,
            )
            self.next_plan_id += 1
            self.plans.append(plan)
            created = plan
        return created

    def get_field(self, field_id: int) -> FarmField | None:
        for f in self.fields:
            if f.id == field_id:
                return f
        return None

    def field_at_cell(self, x: int, y: int) -> FarmField | None:
        for f in self.fields:
            if f.contains(x, y):
                return f
        return None

    def plan_at_cell(self, x: int, y: int) -> tuple[FarmField, CropPlan] | None:
        for f in self.fields:
            plan = f.plan_at(x, y)
            if plan is not None:
                return f, plan
        return None

    def add_field(self, x0: int, y0: int, x1: int, y1: int) -> FarmField:
        field_obj = FarmField(
            id=self.next_field_id,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            name=f"Field {self.next_field_id}",
        )
        self.next_field_id += 1
        self.fields.append(field_obj)
        return field_obj

    def add_plan(
        self,
        field_id: int,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        crop_kind: str,
    ) -> CropPlan | None:
        field_obj = self.get_field(field_id)
        if field_obj is None:
            return None
        plan = CropPlan(
            id=self.next_plan_id,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            crop_kind=crop_kind,
            field_id=field_id,
        )
        plan.clip_to(field_obj.normalised())
        if plan.is_empty():
            return None
        self.next_plan_id += 1
        field_obj.plans.append(plan)
        return plan

    @property
    def stored_total(self) -> int:
        return self.cargo_stored_total + self.seed_stored_total

    @property
    def seed_stored_total(self) -> int:
        if self.seed_capacity <= 0:
            return 0
        total = sum(int(getattr(self, key, 0)) for key in SEED_KEYS)
        if self.is_seed_storage_key("berry_seeds"):
            total += int(getattr(self, "berry_seeds", 0))
        return total

    @property
    def cargo_stored_total(self) -> int:
        """Stock that counts against ``capacity`` (excludes separate seed pool)."""
        from resources import stack_units

        total = (
            self.logs
            + self.hardwood_logs
            + self.wood
            + self.rock
            + self.meat
            + self.fish
            + self.saplings
            + self.mushrooms
            + self.honey
            + self.berries
            + self.reeds
            + self.straw
            + self.fur
            + self.hide
            + self.leather
            + self.twine
            + sum(int(getattr(self, key, 0)) for key in TOOL_KEYS)
            + sum(getattr(self, key) for key in PRODUCE_KEYS)
        )
        for key in PROCESSED_KEYS:
            if key in TOOL_KEYS:
                continue
            total += stack_units(key, int(getattr(self, key, 0)))
        if self.seed_capacity <= 0:
            total += int(getattr(self, "berry_seeds", 0))
            total += sum(getattr(self, key) for key in SEED_KEYS)
        elif not self.is_seed_storage_key("berry_seeds"):
            total += int(getattr(self, "berry_seeds", 0))
        return total

    def is_seed_storage_key(self, key: str) -> bool:
        if self.seed_capacity <= 0:
            return False
        if key in SEED_KEYS:
            return True
        return key == "berry_seeds" and "berry_seeds" in self.depositable_keys()

    def is_processor(self) -> bool:
        return self.kind in (
            BuildingKind.MILL,
            BuildingKind.KITCHEN,
            BuildingKind.CRAFT_BENCH,
            BuildingKind.ALCHEMIST,
            BuildingKind.TAILOR,
            BuildingKind.COBBLER,
        )

    def is_market(self) -> bool:
        return self.kind == BuildingKind.MARKET

    def market_demand_remaining(self, key: str) -> int:
        return max(0, int(self.market_demand.get(key, 0)))

    def market_supply_enabled(self, key: str) -> bool:
        return key in self.market_supply_mins

    def market_supply_min(self, key: str) -> int:
        return max(0, int(self.market_supply_mins.get(key, 0)))

    def market_supply_stock(self, key: str) -> int:
        return max(0, int(self.market_supply_stocks.get(key, 0)))

    def market_stock_target(self, key: str) -> int:
        """Units to keep on the stall (stock setting, or remaining demand if 0)."""
        if not self.market_supply_enabled(key):
            return 0
        stock = self.market_supply_stock(key)
        if stock > 0:
            return stock
        return self.market_demand_remaining(key)

    def set_market_supply_enabled(self, key: str, enabled: bool) -> None:
        """Enable/disable storehouse surplus sales for ``key`` (settings persist while on)."""
        from market_economy import market_supply_resource_keys

        if key not in market_supply_resource_keys():
            return
        if enabled:
            self.market_supply_mins.setdefault(key, 0)
            self.market_supply_stocks.setdefault(key, 0)
        else:
            self.market_supply_mins.pop(key, None)
            self.market_supply_stocks.pop(key, None)

    def set_market_supply_min(self, key: str, amount: int) -> int:
        """Set storehouse reserve for an enabled supply good."""
        from market_economy import market_supply_resource_keys

        if key not in market_supply_resource_keys():
            return 0
        if key not in self.market_supply_mins:
            self.set_market_supply_enabled(key, True)
        value = max(0, int(amount))
        self.market_supply_mins[key] = value
        return value

    def set_market_supply_stock(self, key: str, amount: int) -> int:
        """Set stall stock target for an enabled supply good (0 = match demand)."""
        from market_economy import market_supply_resource_keys

        if key not in market_supply_resource_keys():
            return 0
        if key not in self.market_supply_mins:
            self.set_market_supply_enabled(key, True)
        value = max(0, int(amount))
        self.market_supply_stocks[key] = value
        return value

    def adjust_market_supply_min(self, key: str, delta: int) -> int:
        if key not in self.market_supply_mins:
            self.set_market_supply_enabled(key, True)
        return self.set_market_supply_min(
            key, self.market_supply_min(key) + int(delta)
        )

    def is_splitter(self) -> bool:
        """True when this forester has any split recipe enabled (logs → wood)."""
        if self.kind != BuildingKind.FORESTER:
            return False
        return bool(self.enabled_split_recipes())

    def has_recipes(self) -> bool:
        return bool(self.known_recipes())

    def is_gather_recipe_building(self) -> bool:
        return self.kind in (
            BuildingKind.FORESTER,
            BuildingKind.HUNTER,
            BuildingKind.FORAGER,
        )

    def known_recipes(self) -> tuple[Recipe, ...]:
        if self.kind == BuildingKind.MILL:
            return MILL_RECIPES
        if self.kind == BuildingKind.KITCHEN:
            return KITCHEN_RECIPES
        if self.kind == BuildingKind.CRAFT_BENCH:
            return CRAFT_BENCH_RECIPES
        if self.kind == BuildingKind.ALCHEMIST:
            return ALCHEMIST_RECIPES
        if self.kind == BuildingKind.TAILOR:
            return TAILOR_RECIPES
        if self.kind == BuildingKind.COBBLER:
            return COBBLER_RECIPES
        if self.kind == BuildingKind.FORESTER:
            return FORESTER_RECIPES
        if self.kind == BuildingKind.HUNTER:
            return HUNTER_RECIPES
        if self.kind == BuildingKind.FORAGER:
            return FORAGER_RECIPES
        if self.kind == BuildingKind.FARM:
            return self.addon_craft_recipes()
        return ()

    def addon_craft_recipes(self) -> tuple[Recipe, ...]:
        """Craft recipes unlocked by attached extensions (barn / drying rack)."""
        if self.kind == BuildingKind.FARM and BuildingKind.BARN in self.linked_extensions:
            return BARN_RECIPES
        if (
            self.kind == BuildingKind.HUNTER
            and BuildingKind.DRYING_RACK in self.linked_extensions
        ):
            return DRYING_RACK_RECIPES
        return ()

    def split_recipes(self) -> tuple[Recipe, ...]:
        if self.kind == BuildingKind.FORESTER:
            return FORESTER_SPLIT_RECIPES
        return ()

    def plant_recipes(self) -> tuple[Recipe, ...]:
        if self.kind == BuildingKind.FORESTER:
            return FORESTER_PLANT_RECIPES
        return ()

    def enabled_output_keys(self) -> frozenset[str]:
        """Resource keys produced by enabled recipes (gather / craft outputs)."""
        keys: set[str] = set()
        for recipe in self.enabled_recipes():
            keys.update(recipe.outputs)
        return frozenset(keys)

    def allows_tree_yield(self, yield_key: str) -> bool:
        if not self.has_recipes():
            return True
        return self.is_recipe_enabled(yield_key)

    def allows_hunt_kind(self, kind_name: str) -> bool:
        """``kind_name`` is ``deer``, ``boar``, or ``rabbit``."""
        if self.kind != BuildingKind.HUNTER:
            return True
        return self.is_recipe_enabled(kind_name.lower())

    def allows_forage_key(self, key: str) -> bool:
        if self.kind != BuildingKind.FORAGER:
            return True
        if not self.has_recipes():
            return True
        return self.is_recipe_enabled(key)

    def ensure_recipe_state(self) -> None:
        # Preserve existing toggles; newly added recipe names default on so they
        # show up and can craft (disable manually if unwanted).
        for recipe in (
            *self.known_recipes(),
            *self.addon_craft_recipes(),
            *self.split_recipes(),
            *self.plant_recipes(),
        ):
            self.recipe_enabled.setdefault(recipe.name, True)
            self.recipe_progress.setdefault(recipe.name, 0)
            default_prio = RECIPE_PRIORITY_DEFAULT
            if self.kind == BuildingKind.KITCHEN and recipe.category:
                default_prio = _KITCHEN_CATEGORY_PRIORITY.get(
                    recipe.category, RECIPE_PRIORITY_DEFAULT
                )
            self.recipe_priority.setdefault(recipe.name, default_prio)

    def is_recipe_enabled(self, name: str) -> bool:
        self.ensure_recipe_state()
        return bool(self.recipe_enabled.get(name, True))

    def get_recipe_priority(self, name: str) -> int:
        self.ensure_recipe_state()
        p = int(self.recipe_priority.get(name, RECIPE_PRIORITY_DEFAULT))
        return max(RECIPE_PRIORITY_MIN, min(RECIPE_PRIORITY_MAX, p))

    def set_recipe_priority(self, name: str, priority: int) -> int:
        self.ensure_recipe_state()
        if name not in self.recipe_enabled:
            return RECIPE_PRIORITY_DEFAULT
        p = max(RECIPE_PRIORITY_MIN, min(RECIPE_PRIORITY_MAX, int(priority)))
        self.recipe_priority[name] = p
        return p

    def cycle_recipe_priority(self, name: str) -> int:
        """Cycle 1 → 2 → 3 → 1. Returns the new priority."""
        current = self.get_recipe_priority(name)
        nxt = current + 1
        if nxt > RECIPE_PRIORITY_MAX:
            nxt = RECIPE_PRIORITY_MIN
        return self.set_recipe_priority(name, nxt)

    def toggle_recipe(self, name: str) -> bool:
        self.ensure_recipe_state()
        if name not in self.recipe_enabled:
            return False
        self.recipe_enabled[name] = not self.recipe_enabled[name]
        if not self.recipe_enabled[name]:
            self.recipe_progress[name] = 0
        return self.recipe_enabled[name]

    def set_recipe_enabled(self, name: str, enabled: bool) -> None:
        self.ensure_recipe_state()
        if name not in self.recipe_enabled:
            return
        self.recipe_enabled[name] = bool(enabled)
        if not enabled:
            self.recipe_progress[name] = 0

    def _recipes_by_priority(self, recipes: tuple[Recipe, ...]) -> tuple[Recipe, ...]:
        """Stable sort: priority 1 first, then 2, then 3."""
        indexed = list(enumerate(recipes))
        indexed.sort(key=lambda pair: (self.get_recipe_priority(pair[1].name), pair[0]))
        return tuple(r for _, r in indexed)

    def enabled_recipes(self) -> tuple[Recipe, ...]:
        self.ensure_recipe_state()
        recipes = list(self.known_recipes())
        if self.kind == BuildingKind.HUNTER:
            recipes.extend(self.addon_craft_recipes())
        enabled = tuple(
            r for r in recipes if self.recipe_enabled.get(r.name, True)
        )
        return self._recipes_by_priority(enabled)

    def recipe_progress_fraction(self, name: str) -> float:
        self.ensure_recipe_state()
        steps = max(1, int(PROCESSOR_RECIPE_STEPS))
        return max(0.0, min(1.0, self.recipe_progress.get(name, 0) / steps))

    def active_supply_keys(self) -> tuple[str, ...]:
        """Ingredient keys needed by enabled gather/craft recipes."""
        from recipes import input_keys_for_recipes

        recipes = list(self.enabled_recipes())
        recipes.extend(self.addon_craft_recipes())
        return input_keys_for_recipes(tuple(recipes))

    def recipe_gap_demand(self) -> dict[str, int]:
        """Missing inputs for the highest-priority target recipe(s) only."""
        from recipes import missing_inputs

        demand: dict[str, int] = {}
        for recipe in self._supply_target_recipes():
            for key, need in missing_inputs(self, recipe).items():
                room = self.space_for_key(key)
                if room <= 0:
                    continue
                want = min(int(need), room)
                if want > 0:
                    demand[key] = max(demand.get(key, 0), want)
        return demand

    def supply_demand(self) -> dict[str, int]:
        """Units of each input still needed for enabled recipes, capped by room.

        Prefer recipe gaps over blind top-ups so haulers fetch vegetables when
        meat is already stocked (instead of filling packs with meat first).
        Also tops up toward ``item_mins`` / recipe reserve so haulers and
        crafters are not fighting over under-min stock.
        """
        from recipes import input_keys_for_recipes

        if self.is_market():
            demand: dict[str, int] = {}
            for key in self.market_supply_mins:
                target = self.market_stock_target(key)
                if target <= 0:
                    continue
                have = int(getattr(self, key, 0))
                if have >= target:
                    continue
                room = self.space_for_key(key)
                if room <= 0:
                    continue
                need = min(target - have, room)
                if need > 0:
                    demand[key] = need
            return demand

        demand = self.recipe_gap_demand()
        # Top up processor / splitter inputs (and craft inputs like twine) to reserve.
        top_keys: set[str] = set()
        if self.is_processor():
            top_keys.update(self.processor_input_keys())
        if self.is_splitter():
            top_keys.update(input_keys_for_recipes(self.enabled_split_recipes()))
        for key in top_keys:
            target = self.reserve_amount(key)
            if target <= 0:
                continue
            have = int(getattr(self, key, 0))
            if have >= target:
                continue
            room = self.space_for_key(key)
            if room <= 0:
                continue
            want = min(target - have, room)
            if want > 0:
                demand[key] = max(demand.get(key, 0), want)
        if self.kind == BuildingKind.KITCHEN:
            fuel_want = self.fuel_space_left()
            if fuel_want > 0:
                demand[KITCHEN_FUEL_KEY] = max(
                    demand.get(KITCHEN_FUEL_KEY, 0), fuel_want
                )
        # Farm / forester: top up plant stock from the storehouse.
        # Farms only request seeds with an explicit min — plan-based demand is
        # applied by the game so unused crop seeds don't fill the pack.
        if self.kind == BuildingKind.FORESTER:
            for key in self.plant_keys():
                target = max(3, int(self.item_mins.get(key, 0)))
                have = int(getattr(self, key, 0))
                if have >= target:
                    continue
                room = self.space_for_key(key)
                if room <= 0:
                    continue
                want = min(target - have, room)
                if want > 0:
                    demand[key] = max(demand.get(key, 0), want)
        elif self.kind == BuildingKind.FARM:
            for key in self.plant_keys():
                target = int(self.item_mins.get(key, 0))
                if target <= 0:
                    continue
                have = int(getattr(self, key, 0))
                if have >= target:
                    continue
                room = self.space_for_key(key)
                if room <= 0:
                    continue
                want = min(target - have, room)
                if want > 0:
                    demand[key] = max(demand.get(key, 0), want)
        return demand

    def fuel_space_left(self) -> int:
        if self.fuel_capacity <= 0:
            return 0
        return max(0, self.fuel_capacity - self.fuel_wood)

    def seed_space_left(self) -> int:
        if self.seed_capacity <= 0:
            return 0
        return max(0, self.seed_capacity - self.seed_stored_total)

    def has_cooking_fuel(self) -> bool:
        return self.fuel_wood > 0

    def input_keep_amount(self, key: str) -> int:
        """How many of ``key`` to retain for enabled recipes (2 crafts of buffer)."""
        keep = 0
        for recipe in self.enabled_recipes():
            n = int(recipe.inputs.get(key, 0))
            if n > 0:
                keep = max(keep, n * 2)
        for recipe in self.enabled_split_recipes():
            n = int(recipe.inputs.get(key, 0))
            if n > 0:
                keep = max(keep, n * 2)
        for recipe in self.addon_craft_recipes():
            n = int(recipe.inputs.get(key, 0))
            if n > 0:
                keep = max(keep, n * 2)
        return keep

    def reserve_amount(self, key: str) -> int:
        """Units haulers must not remove (min reserve + recipe buffer)."""
        return max(int(self.item_mins.get(key, 0)), self.input_keep_amount(key))

    def excess_input_amounts(self) -> dict[str, int]:
        """Input stock beyond reserve (mins + recipe buffer) — safe for haulers to clear."""
        excess: dict[str, int] = {}
        if not self.is_processor():
            return excess
        for key in self.processor_input_keys():
            have = int(getattr(self, key, 0))
            keep = self.reserve_amount(key)
            if have > keep:
                excess[key] = have - keep
        return excess

    def haulable_amount(self, key: str) -> int:
        """How many units of ``key`` haulers may remove right now."""
        have = int(getattr(self, key, 0))
        if have <= 0:
            return 0
        if self.is_market():
            if key == "coins":
                return have
            if key in self.market_supply_mins:
                # Keep stall stock up to the target; haul excess home.
                keep = self.market_stock_target(key)
                return max(0, have - keep)
            return have
        # Extension craft inputs (hide for leather, grain for barn seeds).
        if key in self.active_supply_keys() and self.addon_craft_recipes():
            return int(self.excess_input_amounts().get(key, 0))
        if self.is_processor():
            outputs = self.processor_output_keys()
            inputs = self.processor_input_keys()
            # Dual-role stock (craft twine): keep as an ingredient while any
            # enabled recipe still consumes it — only clear true excess.
            if key in outputs and key in inputs and key in self.active_supply_keys():
                return int(self.excess_input_amounts().get(key, 0))
            # Pure outputs and unused inputs honour item_mins / recipe reserve.
            if key in outputs:
                return max(0, have - self.reserve_amount(key))
            if key in self.unused_input_keys():
                return max(0, have - self.reserve_amount(key))
            return int(self.excess_input_amounts().get(key, 0))
        if key in self.haul_keys():
            return max(0, have - self.reserve_amount(key))
        return 0

    def unused_input_keys(self) -> tuple[str, ...]:
        """Input keys stocked here that no enabled recipe uses."""
        needed = set(self.active_supply_keys())
        return tuple(
            key
            for key in self.processor_input_keys()
            if key not in needed and int(getattr(self, key, 0)) > 0
        )

    def processor_input_keys(self) -> tuple[str, ...]:
        if self.kind == BuildingKind.MILL:
            return MILL_INPUT_KEYS
        if self.kind == BuildingKind.KITCHEN:
            return KITCHEN_INPUT_KEYS
        if self.kind == BuildingKind.CRAFT_BENCH:
            return CRAFT_BENCH_INPUT_KEYS
        if self.kind == BuildingKind.ALCHEMIST:
            return ALCHEMIST_INPUT_KEYS
        if self.kind == BuildingKind.TAILOR:
            return TAILOR_INPUT_KEYS
        if self.kind == BuildingKind.COBBLER:
            return COBBLER_INPUT_KEYS
        return ()

    def processor_output_keys(self) -> tuple[str, ...]:
        if self.kind == BuildingKind.MILL:
            return MILL_OUTPUT_KEYS
        if self.kind == BuildingKind.KITCHEN:
            return KITCHEN_OUTPUT_KEYS
        if self.kind == BuildingKind.CRAFT_BENCH:
            return CRAFT_BENCH_OUTPUT_KEYS
        if self.kind == BuildingKind.ALCHEMIST:
            return ALCHEMIST_OUTPUT_KEYS
        if self.kind == BuildingKind.TAILOR:
            return TAILOR_OUTPUT_KEYS
        if self.kind == BuildingKind.COBBLER:
            return COBBLER_OUTPUT_KEYS
        return ()

    def input_stored_total(self) -> int:
        from resources import stack_units

        if self.is_market():
            from market_economy import market_supply_resource_keys

            return sum(
                stack_units(key, int(getattr(self, key, 0)))
                for key in market_supply_resource_keys()
            )
        return sum(
            stack_units(key, int(getattr(self, key, 0)))
            for key in self.processor_input_keys()
        )

    def output_stored_total(self) -> int:
        from resources import stack_units

        if self.is_market():
            # Coins are currency and do not fill the output pool.
            return 0
        return sum(
            stack_units(key, int(getattr(self, key, 0)))
            for key in self.processor_output_keys()
        )

    def input_space_left(self) -> int:
        if self.input_capacity <= 0:
            return self.space_left
        return max(0, self.input_capacity - self.input_stored_total())

    def output_space_left(self) -> int:
        if self.output_capacity <= 0:
            return self.space_left
        return max(0, self.output_capacity - self.output_stored_total())

    def space_for_key(self, key: str) -> int:
        from resources import items_for_stack_room, stack_size

        if key == "coins":
            # Currency is uncapped (still subject to an optional item cap).
            room = 10**9
            cap = self.item_caps.get(key)
            if cap is not None:
                have = int(getattr(self, "coins", 0))
                room = min(room, max(0, int(cap) - have))
            return max(0, room)
        if self.kind == BuildingKind.KITCHEN and key == KITCHEN_FUEL_KEY:
            return self.fuel_space_left()
        if self.is_seed_storage_key(key):
            room = self.seed_space_left()
        elif self.is_market() and (self.input_capacity > 0 or self.output_capacity > 0):
            if key in self.depositable_keys():
                room = self.input_space_left()
            else:
                return 0
        elif self.is_processor() and (self.input_capacity > 0 or self.output_capacity > 0):
            if key in self.processor_input_keys():
                room = self.input_space_left()
            elif key in self.processor_output_keys():
                room = self.output_space_left()
            else:
                return 0
        else:
            room = self.space_left
        have = int(getattr(self, key, 0))
        if stack_size(key) is not None:
            room = items_for_stack_room(key, have, room)
        cap = self.item_caps.get(key)
        if cap is not None:
            room = min(room, max(0, int(cap) - have))
        return max(0, room)

    def item_cap(self, key: str) -> int | None:
        """Return the per-item cap, or None if unlimited."""
        cap = self.item_caps.get(key)
        return int(cap) if cap is not None else None

    def max_item_cap(self, key: str) -> int:
        """Upper bound when setting a cap.

        Local trays (fuel / seeds / processor inputs) stay pool-sized.
        Output / gather Max is village-wide, so the ceiling is high.
        """
        production_ceiling = 9999
        if self.kind == BuildingKind.KITCHEN and key == KITCHEN_FUEL_KEY:
            return max(1, self.fuel_capacity)
        if self.is_seed_storage_key(key):
            return max(1, self.seed_capacity)
        if self.is_processor() and (self.input_capacity > 0 or self.output_capacity > 0):
            if key in self.processor_input_keys():
                return max(1, self.input_capacity)
            if key in self.processor_output_keys():
                return production_ceiling
            return production_ceiling
        return production_ceiling

    def set_item_cap(self, key: str, cap: int | None) -> None:
        """Set or clear a per-item stock limit. ``None`` / <=0 clears."""
        if key not in self.depositable_keys():
            return
        if cap is None or int(cap) <= 0:
            self.item_caps.pop(key, None)
            return
        self.item_caps[key] = min(int(cap), self.max_item_cap(key))

    def adjust_item_cap(self, key: str, delta: int) -> int | None:
        """Nudge cap by ``delta``. From unlimited, ``+`` starts at 1. Returns new cap or None."""
        if key not in self.depositable_keys():
            return None
        current = self.item_cap(key)
        if current is None:
            if delta <= 0:
                return None
            self.set_item_cap(key, delta)
            return self.item_cap(key)
        nxt = current + delta
        if nxt <= 0:
            self.set_item_cap(key, None)
            return None
        self.set_item_cap(key, nxt)
        return self.item_cap(key)

    def item_min(self, key: str) -> int | None:
        val = self.item_mins.get(key)
        return int(val) if val is not None and int(val) > 0 else None

    def set_item_min(self, key: str, minimum: int | None) -> None:
        if key not in self.depositable_keys():
            return
        if minimum is None or int(minimum) <= 0:
            self.item_mins.pop(key, None)
            return
        self.item_mins[key] = min(int(minimum), self.max_item_cap(key))

    def adjust_item_min(self, key: str, delta: int) -> int | None:
        if key not in self.depositable_keys():
            return None
        current = self.item_min(key)
        if current is None:
            if delta <= 0:
                return None
            self.set_item_min(key, delta)
            return self.item_min(key)
        nxt = current + delta
        if nxt <= 0:
            self.set_item_min(key, None)
            return None
        self.set_item_min(key, nxt)
        return self.item_min(key)

    @property
    def space_left(self) -> int:
        if (self.is_processor() or self.is_market()) and (
            self.input_capacity > 0 or self.output_capacity > 0
        ):
            return self.input_space_left() + self.output_space_left()
        return max(0, self.capacity - self.cargo_stored_total)

    def capacity_label(self) -> str:
        if self.is_market():
            enabled = len(self.market_supply_mins)
            demand_n = sum(1 for n in self.market_demand.values() if int(n) > 0)
            stocked = self.input_stored_total()
            label = f"{stocked}/{self.input_capacity} stock  · supply {enabled}  · demand {demand_n}"
        elif self.is_processor() and self.input_capacity > 0:
            label = (
                f"{self.input_stored_total()}/{self.input_capacity} in  "
                f"{self.output_stored_total()}/{self.output_capacity} out"
            )
        else:
            label = f"{self.cargo_stored_total}/{self.capacity}"
        if self.seed_capacity > 0:
            label += f"  · seeds {self.seed_stored_total}/{self.seed_capacity}"
        if self.fuel_capacity > 0:
            label += f"  · fuel {self.fuel_wood}/{self.fuel_capacity}"
        return label

    def _recipe_craft_rank(self, recipe: Recipe) -> tuple[int, int, int]:
        """Sort key: priority 1 first, then richer recipes (more input units)."""
        return (
            self.get_recipe_priority(recipe.name),
            -sum(recipe.inputs.values()),
            -len(recipe.inputs),
        )

    def _recipe_output_fits(
        self,
        recipe: Recipe,
        *,
        stock_amounts: dict[str, int] | None = None,
    ) -> bool:
        from recipes import recipe_output_fits

        if self.output_capacity > 0:
            return recipe_output_fits(
                self,
                recipe,
                output_capacity=self.output_capacity,
                output_keys=self.processor_output_keys(),
                stock_amounts=stock_amounts,
            )
        return recipe_output_fits(
            self,
            recipe,
            capacity=self.capacity,
            stock_amounts=stock_amounts,
        )

    def _recipe_input_blocked_only(
        self,
        recipe: Recipe,
        *,
        worker=None,
        worker_skill_level: int | None = None,
        stock_amounts: dict[str, int] | None = None,
    ) -> bool:
        """True when a recipe could run except for missing inputs (not fuel/caps/skill)."""
        from recipes import recipe_ready
        from society import recipe_skill_gate

        if not recipe.inputs or not self.is_recipe_enabled(recipe.name):
            return False
        if not recipe_skill_gate(
            recipe, worker=worker, worker_skill_level=worker_skill_level
        ):
            return False
        if self.kind == BuildingKind.KITCHEN and not self.has_cooking_fuel():
            return False
        if not self._recipe_output_fits(recipe, stock_amounts=stock_amounts):
            return False
        return not recipe_ready(self, recipe)

    def _supply_target_recipes(self) -> list[Recipe]:
        """Recipes whose missing inputs haulers should fetch (by priority tier)."""
        from recipes import missing_inputs

        recipes = [r for r in self.enabled_recipes() if r.inputs]
        if self.is_splitter():
            recipes.extend(r for r in self.enabled_split_recipes() if r.inputs)
        if not recipes:
            return []

        def _missing_units(recipe: Recipe) -> int:
            return sum(missing_inputs(self, recipe).values())

        def _supply_rank(recipe: Recipe) -> tuple:
            return (
                self.get_recipe_priority(recipe.name),
                _missing_units(recipe),
                self._recipe_craft_rank(recipe),
            )

        for prio in range(RECIPE_PRIORITY_MIN, RECIPE_PRIORITY_MAX + 1):
            tier = [r for r in recipes if self.get_recipe_priority(r.name) == prio]
            blocked = [r for r in tier if self._recipe_input_blocked_only(r)]
            if blocked:
                return [min(blocked, key=_supply_rank)]
        return []

    def craftable_recipe(
        self,
        *,
        worker=None,
        worker_skill_level: int | None = None,
        prefer_name: str | None = None,
        avoid_names: set[str] | frozenset[str] | None = None,
        stock_amounts: dict[str, int] | None = None,
    ) -> Recipe | None:
        """Pick an enabled recipe that can run now.

        Respects recipe priority (1 before 2 before 3). At the same priority,
        prefer richer recipes (more input units) so e.g. spiced stew beats
        grilled meat when both are stocked.

        ``prefer_name`` continues a worker's sticky order when still ready.
        ``avoid_names`` steers co-workers onto other ready recipes when possible
        so two cooks can progress stew and jam at the same time.
        ``stock_amounts`` (village-wide) is used for Max production caps.

        ``worker`` gates recipes by ``Recipe.skill_reqs`` when set.
        ``worker_skill_level`` is a legacy single-level fallback.
        """
        from recipes import recipe_ready
        from society import recipe_skill_gate

        recipes = self.enabled_recipes()
        if not recipes:
            return None
        if self.kind == BuildingKind.KITCHEN and not self.has_cooking_fuel():
            return None
        candidates: list[Recipe] = []
        for recipe in recipes:
            if not recipe.inputs:
                continue
            if not recipe_skill_gate(
                recipe, worker=worker, worker_skill_level=worker_skill_level
            ):
                continue
            if not recipe_ready(self, recipe):
                continue
            if not self._recipe_output_fits(recipe, stock_amounts=stock_amounts):
                continue
            candidates.append(recipe)
        if not candidates:
            return None

        rank = self._recipe_craft_rank
        avoid = avoid_names or ()
        free = [r for r in candidates if r.name not in avoid]
        pool = free if free else list(candidates)
        best_rank = min(rank(r) for r in pool)
        tier = [r for r in pool if rank(r) == best_rank]

        in_progress = [
            r
            for r in tier
            if int(self.recipe_progress.get(r.name, 0)) > 0
        ]
        if in_progress:
            if prefer_name:
                for recipe in in_progress:
                    if recipe.name == prefer_name:
                        return recipe
            return min(in_progress, key=lambda r: r.name)

        if prefer_name:
            for recipe in tier:
                if recipe.name == prefer_name:
                    return recipe

        return min(tier, key=lambda r: r.name)

    def enabled_split_recipes(self) -> tuple[Recipe, ...]:
        self.ensure_recipe_state()
        enabled = tuple(
            r for r in self.split_recipes() if self.recipe_enabled.get(r.name, True)
        )
        return self._recipes_by_priority(enabled)

    def enabled_plant_recipes(self) -> tuple[Recipe, ...]:
        self.ensure_recipe_state()
        enabled = tuple(
            r for r in self.plant_recipes() if self.recipe_enabled.get(r.name, True)
        )
        return self._recipes_by_priority(enabled)

    def craftable_split_recipe(
        self,
        *,
        worker=None,
        worker_skill_level: int | None = None,
        stock_amounts: dict[str, int] | None = None,
    ) -> Recipe | None:
        from society import recipe_skill_gate

        recipes = self.enabled_split_recipes()
        if not recipes:
            return None
        recipes = tuple(
            r
            for r in recipes
            if recipe_skill_gate(
                r, worker=worker, worker_skill_level=worker_skill_level
            )
        )
        if not recipes:
            return None
        return can_craft(
            self, recipes, capacity=self.capacity, stock_amounts=stock_amounts
        )

    def advance_recipe_progress(self, recipe: Recipe, *, split: bool = False) -> bool:
        """Advance one work step. Returns True when the craft completes.

        Multiple recipes may be in progress at once so co-workers can cook /
        craft different orders in parallel without canceling each other.
        """
        self.ensure_recipe_state()
        steps = max(1, int(PROCESSOR_RECIPE_STEPS))
        _ = split  # progress is keyed by recipe name for craft and split alike
        self.recipe_progress[recipe.name] = int(self.recipe_progress.get(recipe.name, 0)) + 1
        if self.recipe_progress[recipe.name] >= steps:
            self.recipe_progress[recipe.name] = 0
            return True
        return False

    def deposit_from_inventory(
        self, inventory: Inventory, *, keep_plantables: bool = False
    ) -> None:
        if self.is_processor() or self.is_market():
            self.deposit_supply_from(inventory)
            return
        keys = self.depositable_keys()
        if keep_plantables:
            keys = tuple(
                k
                for k in keys
                if k not in (*SAPLING_ITEM_KEYS, "berry_seeds", *SEED_KEYS)
            )
        for key in keys:
            self._take(inventory, key)

    def deposit_needed_from(self, inventory: Inventory) -> int:
        """Deposit only recipe gaps (``supply_demand``). Returns units moved."""
        moved = 0
        # Snapshot wants; restock updates change demand as we go.
        for key, want in list(self.supply_demand().items()):
            for _ in range(want):
                if not self.deposit_one_from(inventory, key):
                    break
                moved += 1
        return moved

    def deposit_supply_from(self, inventory: Inventory) -> int:
        """Fill input / fuel / plant stock from inventory up to capacity and caps."""
        moved = 0
        if self.is_market():
            for key in self.market_supply_mins:
                moved += self.deposit_key_from(inventory, key)
            return moved
        if self.is_processor():
            for key in self.processor_input_keys():
                moved += self.deposit_key_from(inventory, key)
            if self.kind == BuildingKind.KITCHEN:
                while self.deposit_one_from(inventory, KITCHEN_FUEL_KEY):
                    moved += 1
            return moved
        if self.is_splitter():
            for key in ("logs", "hardwood_logs"):
                moved += self.deposit_key_from(inventory, key)
            # Fall through so foresters also accept sapling restocks.
        if self.kind in (BuildingKind.FARM, BuildingKind.FORESTER):
            for key in self.plant_keys():
                moved += self.deposit_key_from(inventory, key)
            return moved
        return moved

    def deposit_key_from(self, inventory: Inventory, key: str) -> int:
        """Deposit as much of one key as capacity allows. Returns amount moved."""
        if (
            self.kind == BuildingKind.KITCHEN
            and key == KITCHEN_FUEL_KEY
        ):
            moved = 0
            while self.deposit_one_from(inventory, key):
                moved += 1
            return moved
        if key not in self.depositable_keys():
            return 0
        before = int(getattr(inventory, key, 0))
        self._take(inventory, key)
        return before - int(getattr(inventory, key, 0))

    def deposit_one_from(self, inventory: Inventory, key: str) -> bool:
        """Deposit a single unit of ``key`` if capacity allows."""
        if (
            self.kind == BuildingKind.KITCHEN
            and key == KITCHEN_FUEL_KEY
            and self.fuel_space_left() > 0
            and inventory.wood > 0
        ):
            inventory.wood -= 1
            self.fuel_wood += 1
            return True
        if key not in self.depositable_keys() or self.space_for_key(key) <= 0:
            return False
        if getattr(inventory, key, 0) <= 0:
            return False
        setattr(inventory, key, getattr(inventory, key) - 1)
        setattr(self, key, getattr(self, key) + 1)
        return True

    def depositable_keys(self) -> tuple[str, ...]:
        if self.kind == BuildingKind.HOME:
            # Display-only; actual stock lives on Game.home_storage.
            return (
                "logs",
                "hardwood_logs",
                "wood",
                "rock",
                "meat",
                "fish",
                *SAPLING_ITEM_KEYS,
                "mushrooms",
                "berries",
                "berry_seeds",
                "reeds",
                "straw",
                "fur",
                "hide",
                "leather",
                "twine",
                "axe",
            ) + PRODUCE_KEYS + SEED_KEYS + PROCESSED_KEYS
        if self.kind == BuildingKind.WORKSTATION:
            return ()
        if self.kind == BuildingKind.FORESTER:
            return ("logs", "hardwood_logs", "wood", *SAPLING_ITEM_KEYS)
        if self.kind == BuildingKind.MASON:
            return ("rock",)
        if self.kind == BuildingKind.HUNTER:
            return ("meat", "fur", "hide", "leather")
        if self.kind == BuildingKind.FISHER:
            return ("fish",)
        if self.kind == BuildingKind.FORAGER:
            return ("wood", "rock", *_FORAGE_KEYS)
        if self.kind == BuildingKind.FARM:
            return PRODUCE_KEYS + SEED_KEYS + ("straw",)
        if self.kind in (
            BuildingKind.BARN,
            BuildingKind.PANTRY,
            BuildingKind.DRYING_RACK,
            BuildingKind.FIELD,
        ):
            return ()
        if self.kind == BuildingKind.MILL:
            return MILL_INPUT_KEYS + MILL_OUTPUT_KEYS
        if self.kind == BuildingKind.KITCHEN:
            return KITCHEN_INPUT_KEYS + KITCHEN_OUTPUT_KEYS + (KITCHEN_FUEL_KEY,)
        if self.kind == BuildingKind.CRAFT_BENCH:
            return CRAFT_BENCH_INPUT_KEYS + CRAFT_BENCH_OUTPUT_KEYS
        if self.kind == BuildingKind.ALCHEMIST:
            return ALCHEMIST_INPUT_KEYS + ALCHEMIST_OUTPUT_KEYS
        if self.kind == BuildingKind.TAILOR:
            return TAILOR_INPUT_KEYS + TAILOR_OUTPUT_KEYS
        if self.kind == BuildingKind.COBBLER:
            return COBBLER_INPUT_KEYS + COBBLER_OUTPUT_KEYS
        if self.kind == BuildingKind.MARKET:
            from market_economy import market_supply_resource_keys

            return market_supply_resource_keys()
        return ()

    def haul_keys(self) -> tuple[str, ...]:
        """Items home haulers may remove. Plant stock is reserved while planting."""
        if self.kind == BuildingKind.FORESTER:
            # Always allow hauling logs / wood; mins keep a split buffer on-site.
            return ("logs", "hardwood_logs", "wood")
        if self.kind == BuildingKind.FORAGER:
            return ("wood", "rock", *_FORAGE_KEYS)
        if self.kind == BuildingKind.FARM:
            return PRODUCE_KEYS + ("straw",)
        if self.kind == BuildingKind.HUNTER:
            # Hide stays at the hut for drying-rack tanning; haul meat/fur/leather only.
            return ("meat", "fur", "leather")
        if self.is_market():
            from market_economy import market_supply_resource_keys

            keys: list[str] = []
            if int(getattr(self, "coins", 0)) > 0:
                keys.append("coins")
            for key in market_supply_resource_keys():
                if self.haulable_amount(key) > 0:
                    keys.append(key)
            return tuple(keys)
        if self.is_processor():
            # Produce first, then inputs no enabled recipe uses. Do NOT haul excess
            # stock of active ingredients — that fights supply stockpiling.
            keys: list[str] = []
            seen: set[str] = set()
            for key in (
                *self.processor_output_keys(),
                *self.unused_input_keys(),
            ):
                if key not in seen and self.haulable_amount(key) > 0:
                    seen.add(key)
                    keys.append(key)
            return tuple(keys)
        return self.depositable_keys()

    def plant_keys(self) -> tuple[str, ...]:
        if self.kind == BuildingKind.FORESTER:
            return SAPLING_ITEM_KEYS
        if self.kind == BuildingKind.FARM:
            return SEED_KEYS
        return ()

    def haulable_total(self) -> int:
        return sum(self.haulable_amount(key) for key in self.haul_keys())

    def can_accept_from(self, inventory: Inventory) -> bool:
        """True if inventory holds something this building can take right now."""
        if self.is_processor():
            for key in self.processor_input_keys():
                if int(getattr(inventory, key, 0)) > 0 and self.space_for_key(key) > 0:
                    return True
            if (
                self.kind == BuildingKind.KITCHEN
                and int(getattr(inventory, KITCHEN_FUEL_KEY, 0)) > 0
                and self.fuel_space_left() > 0
            ):
                return True
            return False
        if self.is_market():
            return any(
                int(getattr(inventory, key, 0)) > 0 and self.space_for_key(key) > 0
                for key in self.depositable_keys()
            )
        # Gather / forester lodge: accept any depositable cargo with room.
        keys = self.depositable_keys()
        return any(
            int(getattr(inventory, key, 0)) > 0 and self.space_for_key(key) > 0
            for key in keys
        )

    def needs_supplied(self) -> bool:
        if self.is_processor() or self.is_splitter() or self.is_market():
            return True
        # Farm / forester plant stock — concrete demand is plan-aware in game code.
        if self.kind in (BuildingKind.FARM, BuildingKind.FORESTER):
            return True
        # Hunter drying rack / farm barn craft inputs (e.g. hide, grain).
        if self.addon_craft_recipes() and self.active_supply_keys():
            return True
        return False

    def _take(self, inventory: Inventory, key: str) -> None:
        room = self.space_for_key(key)
        have = getattr(inventory, key)
        take = min(have, room)
        if take <= 0:
            return
        setattr(self, key, getattr(self, key) + take)
        setattr(inventory, key, have - take)

    def withdraw_to_inventory(
        self, inventory: Inventory, keys: tuple[str, ...] | None = None
    ) -> None:
        use_keys = keys if keys is not None else self.haul_keys()
        for key in use_keys:
            # Always honour haulable_amount — passing keys= must not strip
            # reserved dual-role stock (e.g. craft-bench twine used as input).
            limit = self.haulable_amount(key)
            taken = 0
            while (
                taken < limit
                and int(getattr(self, key, 0)) > 0
                and inventory.can_add(1, key=key)
            ):
                setattr(self, key, getattr(self, key) - 1)
                setattr(inventory, key, getattr(inventory, key) + 1)
                taken += 1

    def give_item_to(self, inventory: Inventory, key: str) -> bool:
        if getattr(self, key) <= 0 or not inventory.can_add(1, key=key):
            return False
        setattr(self, key, getattr(self, key) - 1)
        setattr(inventory, key, getattr(inventory, key) + 1)
        return True

    def give_sapling_to(self, inventory: Inventory) -> bool:
        for key in SAPLING_ITEM_KEYS:
            if self.give_item_to(inventory, key):
                return True
        return False

    def withdraw_plantables_to(
        self, inventory: Inventory, *, max_items: int = 3
    ) -> int:
        """Pull a few planting items into inventory (seeds use the seed pool)."""
        taken = 0
        while taken < max_items:
            progressed = False
            for key in self.plant_keys():
                if taken >= max_items:
                    break
                if getattr(self, key) <= 0 or not inventory.can_add(1, key=key):
                    continue
                # Leave one cargo slot free when withdrawing saplings.
                if (
                    not Inventory.is_seed_key(key)
                    and inventory.cargo_total >= inventory.capacity - 1
                ):
                    continue
                setattr(self, key, getattr(self, key) - 1)
                setattr(inventory, key, getattr(inventory, key) + 1)
                taken += 1
                progressed = True
            if not progressed:
                break
        return taken

    def gather_deposit_keys(self) -> tuple[str, ...]:
        """Depositable resources excluding reserved plant stock."""
        plant = set(self.plant_keys())
        return tuple(k for k in self.depositable_keys() if k not in plant)

    def has_gather_cargo(self, inventory: Inventory) -> bool:
        return any(getattr(inventory, key, 0) > 0 for key in self.gather_deposit_keys())

    def holding_only_plantables(self, inventory: Inventory) -> bool:
        if inventory.is_empty:
            return False
        plant = self.plant_keys()
        if not plant:
            return False
        if not any(getattr(inventory, key, 0) > 0 for key in plant):
            return False
        return not self.has_gather_cargo(inventory)

    def allows_planting(self) -> bool:
        return self.kind in (BuildingKind.FORESTER, BuildingKind.FARM)

    def supported_work_modes(self) -> tuple[WorkMode, ...]:
        if self.kind in (
            BuildingKind.HOME,
            BuildingKind.WORKSTATION,
            BuildingKind.MILL,
            BuildingKind.KITCHEN,
            BuildingKind.CRAFT_BENCH,
            BuildingKind.ALCHEMIST,
            BuildingKind.TAILOR,
            BuildingKind.COBBLER,
            BuildingKind.TENT,
            BuildingKind.HOUSE_SMALL,
            BuildingKind.HOUSE,
        ):
            return ()
        if self.kind == BuildingKind.FORESTER:
            return ()
        if self.kind == BuildingKind.FARM:
            return WORK_MODE_CYCLE_PLANTABLE
        if self.kind == BuildingKind.FIELD:
            return (WorkMode.COLLECT,)  # unused; Farm workers manage Fields
        return (WorkMode.COLLECT,)

    def work_mode_label(self) -> str:
        return WORK_MODE_LABELS[self.work_mode]

    def sync_draw_task_from_mode(self) -> None:
        """Keep area-draw task aligned with the behaviour toggle."""
        if self.kind == BuildingKind.FORESTER:
            self.draw_task_type = {
                WorkMode.COLLECT: TaskType.CHOP_TREES,
                WorkMode.PLANT: TaskType.PLANT_SAPLINGS,
                WorkMode.SPLIT: TaskType.SPLIT_LOGS,
                WorkMode.ALL: TaskType.FULL_MANAGE,
            }[self.work_mode]
        elif self.kind == BuildingKind.FORAGER:
            self.draw_task_type = TaskType.FULL_FORAGE
            self.work_mode = WorkMode.COLLECT
        elif self.kind in (BuildingKind.FARM, BuildingKind.FIELD):
            self.draw_task_type = TaskType.FARM_FIELD
        elif self.kind == BuildingKind.MASON:
            self.draw_task_type = TaskType.COLLECT_ROCKS
            self.work_mode = WorkMode.COLLECT
        elif self.kind == BuildingKind.HUNTER:
            self.draw_task_type = TaskType.HUNT
            self.work_mode = WorkMode.COLLECT
        elif self.kind == BuildingKind.FISHER:
            self.draw_task_type = TaskType.FISH
            self.work_mode = WorkMode.COLLECT

    def set_work_mode(self, mode: WorkMode) -> WorkMode:
        modes = self.supported_work_modes()
        if not modes:
            return self.work_mode
        if mode not in modes:
            mode = modes[0]
        self.work_mode = mode
        self.sync_draw_task_from_mode()
        return self.work_mode

    def cycle_work_mode(self) -> WorkMode:
        modes = self.supported_work_modes()
        if not modes:
            return self.work_mode
        if len(modes) == 1:
            self.work_mode = modes[0]
            self.sync_draw_task_from_mode()
            return self.work_mode
        idx = modes.index(self.work_mode) if self.work_mode in modes else 0
        return self.set_work_mode(modes[(idx + 1) % len(modes)])

    def cycle_draw_task(self) -> TaskType:
        # T key cycles the simplified behaviour modes.
        self.cycle_work_mode()
        return self.draw_task_type

    def default_draw_task(self) -> TaskType:
        if self.kind == BuildingKind.FORESTER:
            return TaskType.CHOP_TREES
        if self.kind == BuildingKind.MASON:
            return TaskType.COLLECT_ROCKS
        if self.kind == BuildingKind.HUNTER:
            return TaskType.HUNT
        if self.kind == BuildingKind.FISHER:
            return TaskType.FISH
        if self.kind in (BuildingKind.FARM, BuildingKind.FIELD):
            return TaskType.FARM_FIELD
        return TaskType.FULL_FORAGE

    @staticmethod
    def work_mode_from_task(kind: BuildingKind, task: TaskType) -> WorkMode:
        if kind == BuildingKind.FORESTER:
            if task == TaskType.CHOP_TREES:
                return WorkMode.COLLECT
            if task == TaskType.PLANT_SAPLINGS:
                return WorkMode.PLANT
            if task == TaskType.SPLIT_LOGS:
                return WorkMode.SPLIT
            return WorkMode.ALL
        if kind == BuildingKind.FARM:
            return WorkMode.ALL
        return WorkMode.COLLECT

    def default_work_mode(self) -> WorkMode:
        if self.kind == BuildingKind.FORESTER:
            return WorkMode.ALL
        if self.kind == BuildingKind.FARM:
            return WorkMode.ALL
        return WorkMode.COLLECT


# ConstructionSite.phase values
SITE_PHASE_BUILD = "build"
SITE_PHASE_DECONSTRUCT = "deconstruct"


@dataclass
class ConstructionSite:
    id: int
    x: int
    y: int
    kind: BuildingKind
    need_wood: int = 0  # processed wood
    need_rock: int = 0
    need_logs: int = 0  # softwood logs
    need_hardwood: int = 0
    have_wood: int = 0
    have_rock: int = 0
    have_logs: int = 0
    have_hardwood: int = 0
    build_progress: int = 0
    plot_w: int = 1
    plot_h: int = 1
    # "build" = normal / relocate destination; "deconstruct" = old relocate site.
    phase: str = SITE_PHASE_BUILD
    # Paired site id for relocate (build ↔ deconstruct).
    relocate_pair_id: int | None = None
    # Building id that started a relocate (informational).
    relocate_from_building_id: int | None = None
    # On deconstruct sites: original building id before teardown.
    source_building_id: int | None = None
    # Extension construction: parent workplace this annex attaches to.
    parent_building_id: int | None = None

    def plot_bounds(self) -> tuple[int, int, int, int]:
        w = max(1, self.plot_w)
        h = max(1, self.plot_h)
        return self.x, self.y, self.x + w - 1, self.y + h - 1

    def contains_plot(self, x: int, y: int) -> bool:
        left, top, right, bottom = self.plot_bounds()
        return left <= x <= right and top <= y <= bottom

    def plot_cells(self) -> list[tuple[int, int]]:
        left, top, right, bottom = self.plot_bounds()
        return [(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)]

    def center_cell(self) -> tuple[int, int]:
        left, top, right, bottom = self.plot_bounds()
        return (left + right) // 2, (top + bottom) // 2

    @property
    def is_deconstruct(self) -> bool:
        return self.phase == SITE_PHASE_DECONSTRUCT

    @property
    def wood_needed(self) -> int:
        return max(0, self.need_wood - self.have_wood)

    @property
    def rock_needed(self) -> int:
        return max(0, self.need_rock - self.have_rock)

    @property
    def logs_needed(self) -> int:
        return max(0, self.need_logs - self.have_logs)

    @property
    def hardwood_needed(self) -> int:
        return max(0, self.need_hardwood - self.have_hardwood)

    @property
    def materials_ready(self) -> bool:
        return (
            self.have_wood >= self.need_wood
            and self.have_rock >= self.need_rock
            and self.have_logs >= self.need_logs
            and self.have_hardwood >= self.need_hardwood
        )

    @property
    def total_items(self) -> int:
        return self.need_wood + self.need_rock + self.need_logs + self.need_hardwood

    def build_required_ticks(self) -> int:
        from settings import BUILD_TICKS_PER_ITEM

        return max(1, self.total_items * BUILD_TICKS_PER_ITEM)

    @property
    def is_complete(self) -> bool:
        return self.materials_ready and self.build_progress >= self.build_required_ticks()

    def materials_delivered_frac(self) -> float:
        total = self.total_items
        if total <= 0:
            return 1.0
        have = (
            min(self.have_wood, self.need_wood)
            + min(self.have_rock, self.need_rock)
            + min(self.have_logs, self.need_logs)
            + min(self.have_hardwood, self.need_hardwood)
        )
        return max(0.0, min(1.0, have / total))

    def work_progress_frac(self) -> float:
        need = self.build_required_ticks()
        if need <= 0:
            return 1.0
        return max(0.0, min(1.0, self.build_progress / need))

    def phase_label(self) -> str:
        if self.is_deconstruct:
            return "Moving — deconstruct"
        if self.relocate_pair_id is not None:
            return "Moving — construct"
        return "Building"

    def material_rows(self) -> list[tuple[str, int, int]]:
        """(resource_key, have, need) for UI."""
        rows: list[tuple[str, int, int]] = []
        if self.need_wood or self.have_wood:
            rows.append(("wood", self.have_wood, self.need_wood))
        if self.need_logs or self.have_logs:
            rows.append(("logs", self.have_logs, self.need_logs))
        if self.need_hardwood or self.have_hardwood:
            rows.append(("hardwood_logs", self.have_hardwood, self.need_hardwood))
        if self.need_rock or self.have_rock:
            rows.append(("rock", self.have_rock, self.need_rock))
        return rows


@dataclass
class Villager:
    id: int
    x: int
    y: int
    inventory: Inventory = field(default_factory=Inventory)
    state: VillagerState = VillagerState.IDLE
    building_id: int | None = None
    assigned_to_home: bool = False
    move_cooldown: int = 0
    work_cooldown: int = 0
    target: tuple[int, int] | None = None
    haul_building_id: int | None = None
    hunt_animal_id: int | None = None
    hunt_colony_id: int | None = None
    hunt_meat_pos: tuple[int, int] | None = None
    # After a job change: walk to storehouse and deposit old cargo/tools first.
    job_change_deposit: bool = False
    # Pending bow shot resolution (animal_id, hit, ticks_remaining).
    hunt_shot: tuple[int, bool, int] | None = None
    fish_target_id: int | None = None
    fish_catch_pos: tuple[int, int] | None = None
    fish_post_pos: tuple[int, int] | None = None
    forage_colony_id: int | None = None
    construction_id: int | None = None
    # Sticky processor craft order (kitchen / mill / craft bench).
    craft_recipe_name: str | None = None
    priorities: list[WorkPriority] = field(
        default_factory=lambda: list(DEFAULT_PRIORITIES_UNASSIGNED)
    )
    seasonal_priorities: bool = False
    season_priorities: dict[str, list[WorkPriority]] = field(default_factory=dict)
    workplace_slots: list[int | None] = field(default_factory=lambda: [None, None, None])
    season_workplace_slots: dict[str, list[int | None]] = field(default_factory=dict)
    satiation: float = 0.75
    ration_mode: RationMode = RationMode.NORMAL
    seeking_food: bool = False
    # Food keys from the most recent meal (up to 3 types, one each).
    last_meal: list[str] = field(default_factory=list)
    # Meal buffs (reset on each meal from foods eaten).
    food_walk_mult: float = 1.0
    food_work_mult: float = 1.0
    food_hunger_mult: float = 1.0
    # Society / wellbeing.
    name: str = ""
    energy: float = 1.0
    happiness: float = 0.7
    housed: bool = False
    housing_id: int | None = None
    housing_need: int = 1
    required_foods: list[str] = field(default_factory=lambda: ["meat"])
    favourite_foods: list[str] = field(default_factory=list)
    favourite_is_junk: bool = False
    join_fee_paid: bool = False  # legacy save field; no longer used for fees
    seasons_without_reqs: int = 0
    coins_paid_total: int = 0
    season_pay_due: int = 0
    happiness_events: list[dict] = field(default_factory=list)
    low_happiness_days: float = 0.0  # legacy
    low_happiness_seasons: int = 0
    skills: dict = field(default_factory=dict)
    community_id: int | None = None
    virtues: list[str] = field(default_factory=list)
    vices: list[str] = field(default_factory=list)
    portrait_seed: int = 0
    template_id: str = ""
    tier: int = 1

    def __post_init__(self) -> None:
        if not self.skills:
            from society import blank_skills

            self.skills = blank_skills()
        if not self.name:
            from society import random_name
            import random

            self.name = random_name(random.Random(self.id * 7919 + 17))
        if not self.portrait_seed:
            self.portrait_seed = self.id * 9973 + (hash(self.name) % 10000)
        if not self.virtues and not self.vices:
            from society import pick_traits
            import random

            self.virtues, self.vices = pick_traits(
                random.Random(self.portrait_seed ^ 0xA5A5)
            )
            if self.favourite_is_junk and "Glutton" not in self.vices:
                self.vices = (self.vices + ["Glutton"])[:2]

    def clear_work_stickies(self) -> None:
        """Drop in-progress task state without changing workplace assignment."""
        self.haul_building_id = None
        self.hunt_animal_id = None
        self.hunt_colony_id = None
        self.hunt_meat_pos = None
        self.hunt_shot = None
        self.fish_target_id = None
        self.fish_catch_pos = None
        self.fish_post_pos = None
        self.forage_colony_id = None
        self.construction_id = None
        self.craft_recipe_name = None
        self.target = None

    def clear_assignment(self) -> None:
        self.building_id = None
        self.assigned_to_home = False
        self.clear_work_stickies()
        self.state = VillagerState.IDLE
        self.workplace_slots = [None, None, None]

    def ensure_priorities(self) -> list[WorkPriority]:
        while len(self.priorities) < 3:
            self.priorities.append(WorkPriority.NONE)
        return self.priorities

    def ensure_season_priorities(
        self, *, copy_from: list[WorkPriority] | None = None
    ) -> None:
        from seasons import SEASON_ORDER

        template = list(copy_from if copy_from is not None else self.ensure_priorities())
        while len(template) < 3:
            template.append(WorkPriority.NONE)
        for season in SEASON_ORDER:
            key = season.name
            if key not in self.season_priorities:
                self.season_priorities[key] = list(template)
            else:
                while len(self.season_priorities[key]) < 3:
                    self.season_priorities[key].append(WorkPriority.NONE)

    def ensure_workplace_slots(self) -> list[int | None]:
        while len(self.workplace_slots) < 3:
            self.workplace_slots.append(None)
        return self.workplace_slots

    def ensure_season_workplace_slots(
        self, *, copy_from: list[int | None] | None = None
    ) -> None:
        from seasons import SEASON_ORDER

        template = list(
            copy_from if copy_from is not None else self.ensure_workplace_slots()
        )
        while len(template) < 3:
            template.append(None)
        for season in SEASON_ORDER:
            key = season.name
            if key not in self.season_workplace_slots:
                self.season_workplace_slots[key] = list(template)
            else:
                while len(self.season_workplace_slots[key]) < 3:
                    self.season_workplace_slots[key].append(None)

    def active_workplace_slot_ids(self, season: object | None = None) -> list[int | None]:
        self.ensure_workplace_slots()
        if self.seasonal_priorities and season is not None:
            key = getattr(season, "name", str(season))
            self.ensure_season_workplace_slots()
            row = list(self.season_workplace_slots.get(key, [None, None, None]))
            while len(row) < 3:
                row.append(None)
            if any(bid is not None for bid in row):
                return row
        if any(bid is not None for bid in self.workplace_slots):
            return list(self.workplace_slots)
        if self.building_id is not None:
            return [self.building_id, None, None]
        return [None, None, None]

    def sync_workplace_slot_zero(self) -> None:
        """Legacy migrate / restore only — never overwrite assigned P1 with active work.

        ``building_id`` is the AI's *current* workplace (may be P2/P3).
        ``workplace_slots[0]`` is the player's P1 assignment and must stay put.
        """
        self.ensure_workplace_slots()
        has_slots = any(bid is not None for bid in self.workplace_slots)
        if has_slots:
            # Prefer assigned P1 when idle / unassigned; do not clobber slots from
            # a transient building_id (e.g. working P2).
            if self.building_id is None and self.workplace_slots[0] is not None:
                self.building_id = self.workplace_slots[0]
            return
        if self.building_id is not None:
            self.workplace_slots[0] = self.building_id

    def active_priorities(self, season: object | None = None) -> list[WorkPriority]:
        self.ensure_priorities()
        prios = list(self.priorities)
        if self.building_id is not None or self.assigned_to_home:
            prios = [p for p in prios if p != WorkPriority.BUILD]
        return prios

    def set_default_priorities(self) -> None:
        if self.assigned_to_home:
            base = list(DEFAULT_PRIORITIES_HOME)
        elif self.building_id is not None:
            base = list(DEFAULT_PRIORITIES_WORKPLACE)
        else:
            base = list(DEFAULT_PRIORITIES_UNASSIGNED)
        self.priorities = base
        if self.seasonal_priorities:
            self.ensure_season_workplace_slots(copy_from=self.workplace_slots)

    def cycle_priority_slot(
        self, index: int, *, season: object | None = None
    ) -> WorkPriority:
        if self.seasonal_priorities and season is not None:
            key = getattr(season, "name", str(season))
            self.ensure_season_priorities()
            row = self.season_priorities.setdefault(key, list(self.priorities))
            while len(row) < 3:
                row.append(WorkPriority.NONE)
            current = row[index]
            idx = PRIORITY_CYCLE.index(current) if current in PRIORITY_CYCLE else 0
            row[index] = PRIORITY_CYCLE[(idx + 1) % len(PRIORITY_CYCLE)]
            return row[index]
        self.ensure_priorities()
        current = self.priorities[index]
        idx = PRIORITY_CYCLE.index(current) if current in PRIORITY_CYCLE else 0
        self.priorities[index] = PRIORITY_CYCLE[(idx + 1) % len(PRIORITY_CYCLE)]
        return self.priorities[index]

    def cycle_ration_mode(self) -> RationMode:
        idx = RATION_CYCLE.index(self.ration_mode) if self.ration_mode in RATION_CYCLE else 0
        self.ration_mode = RATION_CYCLE[(idx + 1) % len(RATION_CYCLE)]
        return self.ration_mode

    def eat_threshold(self) -> float:
        return RATION_EAT_AT[self.ration_mode]

    def ration_refill(self) -> float:
        return RATION_REFILL[self.ration_mode]

    def ration_food_amount(self) -> int:
        return RATION_FOOD_AMOUNT[self.ration_mode]

    def needs_food(self) -> bool:
        return self.satiation <= self.eat_threshold()

    def apply_food_buffs(
        self, walk: float = 1.0, work: float = 1.0, hunger: float = 1.0
    ) -> None:
        self.food_walk_mult = max(0.1, float(walk))
        self.food_work_mult = max(0.1, float(work))
        self.food_hunger_mult = max(0.05, float(hunger))

    def clear_food_buffs(self) -> None:
        self.food_walk_mult = 1.0
        self.food_work_mult = 1.0
        self.food_hunger_mult = 1.0


@dataclass
class Player:
    x: int
    y: int
    inventory: Inventory = field(default_factory=Inventory)
    move_cooldown: int = 0
    work_cooldown: int = 0
    satiation: float = 0.75
    energy: float = 1.0
    happiness: float = 0.7
    last_meal: list[str] = field(default_factory=list)
    food_walk_mult: float = 1.0
    food_work_mult: float = 1.0
    food_hunger_mult: float = 1.0
    ration_mode: RationMode = RationMode.NORMAL
    auto_eat: bool = False

    def __post_init__(self) -> None:
        snap_entity_visual(self)

    def move_to(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
        snap_entity_visual(self)

    def reset(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
        self.move_cooldown = 0
        self.work_cooldown = 0
        self.satiation = 0.75
        self.energy = 1.0
        self.happiness = 0.7
        self.last_meal.clear()
        self.clear_food_buffs()
        self.ration_mode = RationMode.NORMAL
        self.auto_eat = False
        self.inventory.reset()
        snap_entity_visual(self)

    def eat_threshold(self) -> float:
        return RATION_EAT_AT[self.ration_mode]

    def ration_refill(self) -> float:
        return RATION_REFILL[self.ration_mode]

    def needs_food(self) -> bool:
        return self.satiation <= self.eat_threshold()

    def apply_food_buffs(
        self, walk: float = 1.0, work: float = 1.0, hunger: float = 1.0
    ) -> None:
        self.food_walk_mult = max(0.1, float(walk))
        self.food_work_mult = max(0.1, float(work))
        self.food_hunger_mult = max(0.05, float(hunger))

    def clear_food_buffs(self) -> None:
        self.food_walk_mult = 1.0
        self.food_work_mult = 1.0
        self.food_hunger_mult = 1.0


def note_cell_step(entity: object, nx: int, ny: int) -> None:
    """Record a logical cell change so drawing can interpolate from the prior cell."""
    x = int(getattr(entity, "x"))
    y = int(getattr(entity, "y"))
    if (x, y) == (nx, ny):
        return
    setattr(entity, "_vis_from_x", float(x))
    setattr(entity, "_vis_from_y", float(y))
    setattr(entity, "_vis_pending", True)
    setattr(entity, "x", nx)
    setattr(entity, "y", ny)


def arm_cell_step_visual(entity: object, duration: int) -> None:
    """Bind a pending cell step to a move duration (usually ``move_cooldown``)."""
    if getattr(entity, "_vis_pending", False):
        setattr(entity, "_vis_duration", max(1, int(duration)))
        setattr(entity, "_vis_pending", False)


def snap_entity_visual(entity: object) -> None:
    """Snap draw position to the logical cell (spawn, load, teleport)."""
    setattr(entity, "_vis_from_x", float(getattr(entity, "x")))
    setattr(entity, "_vis_from_y", float(getattr(entity, "y")))
    setattr(entity, "_vis_duration", 0)
    setattr(entity, "_vis_pending", False)


def entity_draw_xy(entity: object) -> tuple[float, float]:
    """Fractional cell indices for drawing (lerp between cell centres)."""
    x = float(getattr(entity, "x"))
    y = float(getattr(entity, "y"))
    duration = int(getattr(entity, "_vis_duration", 0) or 0)
    cooldown = int(getattr(entity, "move_cooldown", 0) or 0)
    fx = getattr(entity, "_vis_from_x", None)
    fy = getattr(entity, "_vis_from_y", None)
    if fx is None or fy is None or duration <= 0 or cooldown <= 0:
        return x, y
    progress = 1.0 - (cooldown / duration)
    if progress < 0.0:
        progress = 0.0
    elif progress > 1.0:
        progress = 1.0
    return float(fx) + (x - float(fx)) * progress, float(fy) + (y - float(fy)) * progress


def ensure_storage_item_fields() -> None:
    """Ensure Inventory / HomeStorage / Building expose every recipe cargo key.

    Directory-loaded recipes may introduce new output keys; class attrs are
    created so ``hasattr`` / ``add_item`` / ``PROCESSED_KEYS`` totals work.
    """
    for cls in (Inventory, HomeStorage, Building):
        for key in PROCESSED_KEYS:
            if not hasattr(cls, key):
                setattr(cls, key, 0)


ensure_storage_item_fields()
