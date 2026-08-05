"""Player, inventory, buildings, villagers, and work tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from crops import PRODUCE_KEYS, SEED_KEYS
from recipes import (
    CRAFT_BENCH_INPUT_KEYS,
    CRAFT_BENCH_OUTPUT_KEYS,
    CRAFT_BENCH_RECIPES,
    FORESTER_RECIPES,
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
    Recipe,
    apply_recipe,
    can_craft,
    input_keys_for_recipes,
)
from settings import (
    BUILDING_FOOTPRINT,
    BUILDING_STORAGE_CAPACITY,
    CRAFT_BENCH_INPUT_CAPACITY,
    CRAFT_BENCH_OUTPUT_CAPACITY,
    FORESTER_DEFAULT_HARDWOOD_LOGS_MIN,
    FORESTER_DEFAULT_LOGS_MIN,
    INVENTORY_CAPACITY,
    KITCHEN_FUEL_CAPACITY,
    KITCHEN_INPUT_CAPACITY,
    KITCHEN_OUTPUT_CAPACITY,
    MILL_INPUT_CAPACITY,
    MILL_OUTPUT_CAPACITY,
    PROCESSOR_RECIPE_STEPS,
    SEED_CARRY_CAPACITY,
)
from trees import SAPLING_ITEM_KEYS, sapling_item_key

# Seeds share a dedicated carry pool (separate from wood/food/etc.).
SEED_ITEM_KEYS: tuple[str, ...] = ("berry_seeds", *SEED_KEYS)

# Tools carried in the dedicated tool slot (not general cargo stacks).
TOOL_KEYS: tuple[str, ...] = ("axe", "spear", "fishing_rod", "hoe", "knife")


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


# Tool required in the equipped slot for workplace actions.
WORKPLACE_TOOL: dict[BuildingKind, str] = {
    BuildingKind.FORESTER: "axe",
    BuildingKind.HUNTER: "spear",
    BuildingKind.FISHER: "fishing_rod",
    BuildingKind.FARM: "hoe",
    BuildingKind.KITCHEN: "knife",
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
}


def default_building_plot(kind: BuildingKind) -> tuple[int, int]:
    """Default footprint size. Fields are drag-sized; all other buildings are square."""
    if kind == BuildingKind.FIELD:
        return 1, 1
    n = max(1, int(BUILDING_FOOTPRINT))
    return n, n


def default_processor_capacities(kind: BuildingKind) -> tuple[int, int, int]:
    """Return (capacity, input_capacity, output_capacity) for a new building."""
    if kind == BuildingKind.MILL:
        return (
            MILL_INPUT_CAPACITY + MILL_OUTPUT_CAPACITY,
            MILL_INPUT_CAPACITY,
            MILL_OUTPUT_CAPACITY,
        )
    if kind == BuildingKind.KITCHEN:
        return (
            KITCHEN_INPUT_CAPACITY + KITCHEN_OUTPUT_CAPACITY,
            KITCHEN_INPUT_CAPACITY,
            KITCHEN_OUTPUT_CAPACITY,
        )
    if kind == BuildingKind.CRAFT_BENCH:
        return (
            CRAFT_BENCH_INPUT_CAPACITY + CRAFT_BENCH_OUTPUT_CAPACITY,
            CRAFT_BENCH_INPUT_CAPACITY,
            CRAFT_BENCH_OUTPUT_CAPACITY,
        )
    return BUILDING_STORAGE_CAPACITY, 0, 0


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
    berries: int = 0
    berry_seeds: int = 0
    reeds: int = 0
    wheat: int = 0
    flax: int = 0
    sage: int = 0
    hemp: int = 0
    rye: int = 0
    onion: int = 0
    cabbage: int = 0
    carrot: int = 0
    garlic: int = 0
    wheat_seeds: int = 0
    flax_seeds: int = 0
    sage_seeds: int = 0
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
    axe: int = 0
    spear: int = 0
    fishing_rod: int = 0
    hoe: int = 0
    knife: int = 0
    equipped_tool: str | None = None
    capacity: int = INVENTORY_CAPACITY
    seed_capacity: int = SEED_CARRY_CAPACITY

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
        return (
            self.logs
            + self.hardwood_logs
            + self.wood
            + self.rock
            + self.meat
            + self.fish
            + self.saplings
            + self.mushrooms
            + self.berries
            + self.reeds
            + self.twine
            + self.axe
            + sum(getattr(self, key) for key in PRODUCE_KEYS)
            + sum(getattr(self, key) for key in PROCESSED_KEYS)
        )

    @property
    def total(self) -> int:
        return self.cargo_total + self.seed_total

    @property
    def is_full(self) -> bool:
        """True when general cargo is full (seeds use a separate pool)."""
        return self.cargo_total >= self.capacity

    @property
    def seeds_full(self) -> bool:
        return self.seed_total >= self.seed_capacity

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    def can_add(self, amount: int = 1, key: str | None = None) -> bool:
        if key is not None and self.is_seed_key(key):
            return self.seed_total + amount <= self.seed_capacity
        return self.cargo_total + amount <= self.capacity

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

    def has_equipped_tool(self, key: str) -> bool:
        return self.equipped_tool == key

    def can_equip_tool(self, key: str) -> bool:
        return (
            key in TOOL_KEYS
            and self.equipped_tool is None
            and int(getattr(self, key, 0)) > 0
        )

    def equip_tool(self, key: str) -> bool:
        if not self.can_equip_tool(key):
            return False
        setattr(self, key, getattr(self, key) - 1)
        self.equipped_tool = key
        return True

    def unequip_tool(self) -> bool:
        if self.equipped_tool is None:
            return False
        key = self.equipped_tool
        if not self.can_add(1, key=key):
            return False
        self.equipped_tool = None
        setattr(self, key, getattr(self, key) + 1)
        return True

    def equip_tool_from_transfer(self, key: str) -> bool:
        """Equip a tool moved directly into the slot (e.g. from the player)."""
        if key not in TOOL_KEYS or self.equipped_tool is not None:
            return False
        self.equipped_tool = key
        return True

    def transfer_equipped_tool_to(self, other: Inventory) -> bool:
        if self.equipped_tool is None:
            return False
        key = self.equipped_tool
        if not other.can_add(1, key=key):
            return False
        self.equipped_tool = None
        other.add_item(key, 1)
        return True

    def try_equip_work_tools(self) -> bool:
        """Move a tool from cargo into the tool slot when empty."""
        if self.equipped_tool is not None:
            return False
        for key in TOOL_KEYS:
            if self.equip_tool(key):
                return True
        return False

    def has_delivery_cargo(self) -> bool:
        """Cargo worth delivering — loose tools stay on the worker."""
        cargo = self.cargo_total
        for key in TOOL_KEYS:
            cargo -= int(getattr(self, key, 0))
        return cargo > 0 or self.seed_total > 0

    def clear(self) -> dict[str, int]:
        saved_tool = self.equipped_tool
        deposited = {
            "logs": self.logs,
            "hardwood_logs": self.hardwood_logs,
            "wood": self.wood,
            "rock": self.rock,
            "meat": self.meat,
            "fish": self.fish,
            "mushrooms": self.mushrooms,
            "berries": self.berries,
            "berry_seeds": self.berry_seeds,
            "reeds": self.reeds,
            "twine": self.twine,
            "axe": self.axe,
            **{key: getattr(self, key) for key in SAPLING_ITEM_KEYS},
            **{key: getattr(self, key) for key in PRODUCE_KEYS},
            **{key: getattr(self, key) for key in SEED_KEYS},
            **{key: getattr(self, key) for key in PROCESSED_KEYS},
        }
        self.reset()
        self.equipped_tool = saved_tool
        return deposited

    def reset(self) -> None:
        self.logs = self.hardwood_logs = self.wood = self.rock = self.meat = self.fish = 0
        self.mushrooms = self.berries = self.berry_seeds = self.reeds = 0
        self.twine = self.axe = self.spear = self.fishing_rod = self.hoe = self.knife = 0
        self.equipped_tool = None
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
    berries: int = 0
    berry_seeds: int = 0
    reeds: int = 0
    wheat: int = 0
    flax: int = 0
    sage: int = 0
    hemp: int = 0
    rye: int = 0
    onion: int = 0
    cabbage: int = 0
    carrot: int = 0
    garlic: int = 0
    wheat_seeds: int = 0
    flax_seeds: int = 0
    sage_seeds: int = 0
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
    axe: int = 0
    spear: int = 0
    fishing_rod: int = 0
    hoe: int = 0
    knife: int = 0

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
        self.mushrooms = self.berries = self.berry_seeds = self.reeds = 0
        self.twine = self.axe = self.spear = self.fishing_rod = self.hoe = self.knife = 0
        for key in TOOL_KEYS:
            if key not in ("axe",):
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


_FORAGE_KEYS = ("mushrooms", "berries", "berry_seeds", "reeds") + PRODUCE_KEYS + SEED_KEYS


RECIPE_PRIORITY_MIN = 1
RECIPE_PRIORITY_MAX = 3
RECIPE_PRIORITY_DEFAULT = 1


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
    berries: int = 0
    berry_seeds: int = 0
    reeds: int = 0
    wheat: int = 0
    flax: int = 0
    sage: int = 0
    hemp: int = 0
    rye: int = 0
    onion: int = 0
    cabbage: int = 0
    carrot: int = 0
    garlic: int = 0
    wheat_seeds: int = 0
    flax_seeds: int = 0
    sage_seeds: int = 0
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
    axe: int = 0
    spear: int = 0
    fishing_rod: int = 0
    hoe: int = 0
    knife: int = 0
    capacity: int = BUILDING_STORAGE_CAPACITY
    # Processor buildings use split pools (0 = unused / fall back to capacity).
    input_capacity: int = 0
    output_capacity: int = 0
    fuel_capacity: int = 0
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
    draw_task_type: TaskType = TaskType.FULL_MANAGE
    work_mode: WorkMode = WorkMode.ALL
    crop_kind: str = "sage"  # legacy
    next_field_id: int = 1
    next_plan_id: int = 1

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
        return (
            self.logs
            + self.hardwood_logs
            + self.wood
            + self.rock
            + self.meat
            + self.fish
            + self.saplings
            + self.mushrooms
            + self.berries
            + self.berry_seeds
            + self.reeds
            + self.twine
            + self.axe
            + sum(getattr(self, key) for key in PRODUCE_KEYS)
            + sum(getattr(self, key) for key in SEED_KEYS)
            + sum(getattr(self, key) for key in PROCESSED_KEYS)
        )

    def is_processor(self) -> bool:
        return self.kind in (BuildingKind.MILL, BuildingKind.KITCHEN, BuildingKind.CRAFT_BENCH)

    def is_splitter(self) -> bool:
        return self.kind == BuildingKind.FORESTER and self.work_mode in (
            WorkMode.SPLIT,
            WorkMode.ALL,
        )

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
        if self.kind == BuildingKind.FORESTER:
            return FORESTER_RECIPES
        if self.kind == BuildingKind.HUNTER:
            return HUNTER_RECIPES
        if self.kind == BuildingKind.FORAGER:
            return FORAGER_RECIPES
        return ()

    def split_recipes(self) -> tuple[Recipe, ...]:
        if self.kind == BuildingKind.FORESTER:
            return FORESTER_SPLIT_RECIPES
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
        """``kind_name`` is ``deer`` or ``boar``."""
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
        for recipe in self.known_recipes():
            self.recipe_enabled.setdefault(recipe.name, True)
            self.recipe_progress.setdefault(recipe.name, 0)
            self.recipe_priority.setdefault(recipe.name, RECIPE_PRIORITY_DEFAULT)
        for recipe in self.split_recipes():
            self.recipe_enabled.setdefault(recipe.name, True)
            self.recipe_progress.setdefault(recipe.name, 0)
            self.recipe_priority.setdefault(recipe.name, RECIPE_PRIORITY_DEFAULT)

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
        enabled = tuple(
            r for r in self.known_recipes() if self.recipe_enabled.get(r.name, True)
        )
        return self._recipes_by_priority(enabled)

    def recipe_progress_fraction(self, name: str) -> float:
        self.ensure_recipe_state()
        steps = max(1, int(PROCESSOR_RECIPE_STEPS))
        return max(0.0, min(1.0, self.recipe_progress.get(name, 0) / steps))

    def active_supply_keys(self) -> tuple[str, ...]:
        """Ingredient keys needed by currently enabled recipes."""
        return input_keys_for_recipes(self.enabled_recipes())

    def supply_demand(self) -> dict[str, int]:
        """Units of each input still needed for enabled recipes, capped by room.

        Prefer recipe gaps over blind top-ups so haulers fetch vegetables when
        meat is already stocked (instead of filling packs with meat first).
        Also tops up toward ``item_mins`` / recipe reserve so haulers and
        crafters are not fighting over under-min stock.
        """
        from recipes import input_keys_for_recipes, missing_inputs

        demand: dict[str, int] = {}
        for recipe in self.enabled_recipes():
            if not recipe.inputs:
                continue
            for key, need in missing_inputs(self, recipe).items():
                room = self.space_for_key(key)
                if room <= 0:
                    continue
                want = min(int(need), room)
                if want > 0:
                    demand[key] = max(demand.get(key, 0), want)
        if self.is_splitter():
            for recipe in self.enabled_split_recipes():
                if not recipe.inputs:
                    continue
                for key, need in missing_inputs(self, recipe).items():
                    room = self.space_for_key(key)
                    if room <= 0:
                        continue
                    want = min(int(need), room)
                    if want > 0:
                        demand[key] = max(demand.get(key, 0), want)
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
        return demand

    def fuel_space_left(self) -> int:
        if self.fuel_capacity <= 0:
            return 0
        return max(0, self.fuel_capacity - self.fuel_wood)

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
        if self.is_processor():
            # Outputs and unused inputs still honour item_mins / recipe reserve.
            if key in self.processor_output_keys():
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
        return ()

    def processor_output_keys(self) -> tuple[str, ...]:
        if self.kind == BuildingKind.MILL:
            return MILL_OUTPUT_KEYS
        if self.kind == BuildingKind.KITCHEN:
            return KITCHEN_OUTPUT_KEYS
        if self.kind == BuildingKind.CRAFT_BENCH:
            return CRAFT_BENCH_OUTPUT_KEYS
        return ()

    def input_stored_total(self) -> int:
        return sum(int(getattr(self, key, 0)) for key in self.processor_input_keys())

    def output_stored_total(self) -> int:
        return sum(int(getattr(self, key, 0)) for key in self.processor_output_keys())

    def input_space_left(self) -> int:
        if self.input_capacity <= 0:
            return self.space_left
        return max(0, self.input_capacity - self.input_stored_total())

    def output_space_left(self) -> int:
        if self.output_capacity <= 0:
            return self.space_left
        return max(0, self.output_capacity - self.output_stored_total())

    def space_for_key(self, key: str) -> int:
        if self.kind == BuildingKind.KITCHEN and key == KITCHEN_FUEL_KEY:
            return self.fuel_space_left()
        if self.is_processor() and (self.input_capacity > 0 or self.output_capacity > 0):
            if key in self.processor_input_keys():
                room = self.input_space_left()
            elif key in self.processor_output_keys():
                room = self.output_space_left()
            else:
                return 0
        else:
            room = self.space_left
        cap = self.item_caps.get(key)
        if cap is not None:
            have = int(getattr(self, key, 0))
            room = min(room, max(0, int(cap) - have))
        return max(0, room)

    def item_cap(self, key: str) -> int | None:
        """Return the per-item cap, or None if unlimited."""
        cap = self.item_caps.get(key)
        return int(cap) if cap is not None else None

    def max_item_cap(self, key: str) -> int:
        """Upper bound when setting a cap (pool size for this key)."""
        if self.is_processor() and (self.input_capacity > 0 or self.output_capacity > 0):
            if key in self.processor_input_keys():
                return max(1, self.input_capacity)
            if key in self.processor_output_keys():
                return max(1, self.output_capacity)
            return 1
        return max(1, self.capacity)

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
        if self.is_processor() and (self.input_capacity > 0 or self.output_capacity > 0):
            return self.input_space_left() + self.output_space_left()
        return max(0, self.capacity - self.stored_total)

    def capacity_label(self) -> str:
        if self.is_processor() and self.input_capacity > 0:
            return (
                f"{self.input_stored_total()}/{self.input_capacity} in  "
                f"{self.output_stored_total()}/{self.output_capacity} out"
            )
        return f"{self.stored_total}/{self.capacity}"

    def craftable_recipe(self) -> Recipe | None:
        recipes = self.enabled_recipes()
        if not recipes:
            return None
        if self.kind == BuildingKind.KITCHEN and not self.has_cooking_fuel():
            return None
        if self.output_capacity > 0:
            return can_craft(
                self,
                recipes,
                output_capacity=self.output_capacity,
                output_keys=self.processor_output_keys(),
            )
        return can_craft(self, recipes, capacity=self.capacity)

    def enabled_split_recipes(self) -> tuple[Recipe, ...]:
        self.ensure_recipe_state()
        enabled = tuple(
            r for r in self.split_recipes() if self.recipe_enabled.get(r.name, True)
        )
        return self._recipes_by_priority(enabled)

    def craftable_split_recipe(self) -> Recipe | None:
        recipes = self.enabled_split_recipes()
        if not recipes:
            return None
        return can_craft(self, recipes, capacity=self.capacity)

    def advance_recipe_progress(self, recipe: Recipe, *, split: bool = False) -> bool:
        """Advance one work step. Returns True when the craft completes."""
        self.ensure_recipe_state()
        steps = max(1, int(PROCESSOR_RECIPE_STEPS))
        primary = self.split_recipes() if split else self.known_recipes()
        secondary = self.known_recipes() if split else self.split_recipes()
        for other in primary:
            if other.name != recipe.name:
                self.recipe_progress[other.name] = 0
        for other in secondary:
            self.recipe_progress[other.name] = 0
        self.recipe_progress[recipe.name] = int(self.recipe_progress.get(recipe.name, 0)) + 1
        if self.recipe_progress[recipe.name] >= steps:
            self.recipe_progress[recipe.name] = 0
            return True
        return False

    def deposit_from_inventory(
        self, inventory: Inventory, *, keep_plantables: bool = False
    ) -> None:
        if self.is_processor():
            self.deposit_needed_from(inventory)
            return
        if self.is_splitter():
            for key in ("logs", "hardwood_logs"):
                while self.deposit_one_from(inventory, key):
                    pass
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

    def deposit_key_from(self, inventory: Inventory, key: str) -> int:
        """Deposit as much of one key as capacity allows. Returns amount moved."""
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
            return ("meat",)
        if self.kind == BuildingKind.FISHER:
            return ("fish",)
        if self.kind == BuildingKind.FORAGER:
            return ("wood", *_FORAGE_KEYS)
        if self.kind == BuildingKind.FARM:
            return PRODUCE_KEYS + SEED_KEYS
        if self.kind == BuildingKind.MILL:
            return MILL_INPUT_KEYS + MILL_OUTPUT_KEYS
        if self.kind == BuildingKind.KITCHEN:
            return KITCHEN_INPUT_KEYS + KITCHEN_OUTPUT_KEYS + (KITCHEN_FUEL_KEY,)
        if self.kind == BuildingKind.CRAFT_BENCH:
            return CRAFT_BENCH_INPUT_KEYS + CRAFT_BENCH_OUTPUT_KEYS
        if self.kind == BuildingKind.FIELD:
            return ()
        return ()

    def haul_keys(self) -> tuple[str, ...]:
        """Items home haulers may remove. Plant stock is reserved while planting."""
        if self.kind == BuildingKind.FORESTER:
            if self.work_mode == WorkMode.COLLECT:
                return ("logs", "hardwood_logs", *SAPLING_ITEM_KEYS)
            if self.work_mode == WorkMode.SPLIT:
                return ("wood",)
            return ("logs", "hardwood_logs", "wood")
        if self.kind == BuildingKind.FORAGER:
            return ("wood", *_FORAGE_KEYS)
        if self.kind == BuildingKind.FARM:
            return PRODUCE_KEYS
        if self.is_processor():
            # Outputs, unused inputs, and excess stock of still-needed inputs.
            keys: list[str] = []
            seen: set[str] = set()
            for key in (
                *self.processor_output_keys(),
                *self.unused_input_keys(),
                *self.excess_input_amounts().keys(),
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
        if self.is_splitter():
            for key in ("logs", "hardwood_logs"):
                if int(getattr(inventory, key, 0)) > 0 and self.space_for_key(key) > 0:
                    return True
        if self.is_processor() or self.is_splitter():
            demand = self.supply_demand()
            return any(
                int(getattr(inventory, key, 0)) > 0 and demand.get(key, 0) > 0
                for key in demand
            )
        keys = self.depositable_keys()
        return any(
            int(getattr(inventory, key, 0)) > 0 and self.space_for_key(key) > 0
            for key in keys
        )

    def needs_supplied(self) -> bool:
        return self.is_processor() or self.is_splitter()

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
            limit = (
                self.haulable_amount(key)
                if keys is None
                else int(getattr(self, key, 0))
            )
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
        ):
            return ()
        if self.kind == BuildingKind.FORESTER:
            return WORK_MODE_CYCLE_FORESTER
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
            return TaskType.FULL_MANAGE
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


@dataclass
class ConstructionSite:
    id: int
    x: int
    y: int
    kind: BuildingKind
    need_wood: int
    need_rock: int
    have_wood: int = 0
    have_rock: int = 0
    build_progress: int = 0
    plot_w: int = 1
    plot_h: int = 1

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
    def wood_needed(self) -> int:
        return max(0, self.need_wood - self.have_wood)

    @property
    def rock_needed(self) -> int:
        return max(0, self.need_rock - self.have_rock)

    @property
    def materials_ready(self) -> bool:
        return self.have_wood >= self.need_wood and self.have_rock >= self.need_rock

    @property
    def total_items(self) -> int:
        return self.need_wood + self.need_rock

    def build_required_ticks(self) -> int:
        from settings import BUILD_TICKS_PER_ITEM

        return self.total_items * BUILD_TICKS_PER_ITEM

    @property
    def is_complete(self) -> bool:
        return self.materials_ready and self.build_progress >= self.build_required_ticks()


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
    hunt_meat_pos: tuple[int, int] | None = None
    fish_target_id: int | None = None
    fish_catch_pos: tuple[int, int] | None = None
    construction_id: int | None = None
    priorities: list[WorkPriority] = field(
        default_factory=lambda: list(DEFAULT_PRIORITIES_UNASSIGNED)
    )
    satiation: float = 0.75
    ration_mode: RationMode = RationMode.NORMAL
    seeking_food: bool = False
    # Food keys from the most recent meal (up to 3 types, one each).
    last_meal: list[str] = field(default_factory=list)
    # Meal buffs (reset on each meal from foods eaten).
    food_walk_mult: float = 1.0
    food_work_mult: float = 1.0
    food_hunger_mult: float = 1.0

    def clear_assignment(self) -> None:
        self.building_id = None
        self.assigned_to_home = False
        self.haul_building_id = None
        self.hunt_animal_id = None
        self.hunt_meat_pos = None
        self.fish_target_id = None
        self.fish_catch_pos = None
        self.construction_id = None
        self.state = VillagerState.IDLE
        self.target = None

    def set_default_priorities(self) -> None:
        if self.assigned_to_home:
            self.priorities = list(DEFAULT_PRIORITIES_HOME)
        elif self.building_id is not None:
            self.priorities = list(DEFAULT_PRIORITIES_WORKPLACE)
        else:
            self.priorities = list(DEFAULT_PRIORITIES_UNASSIGNED)

    def cycle_priority_slot(self, index: int) -> WorkPriority:
        while len(self.priorities) < 3:
            self.priorities.append(WorkPriority.NONE)
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
    vis_x: float = 0.0
    vis_y: float = 0.0

    def __post_init__(self) -> None:
        self.vis_x = float(self.x)
        self.vis_y = float(self.y)

    def move_to(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def reset(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
        self.vis_x = float(x)
        self.vis_y = float(y)
        self.inventory.reset()

    def update_visual(self, dt: float, speed: float) -> None:
        """Lerp draw position toward the logical cell each frame."""
        tx, ty = float(self.x), float(self.y)
        dx = tx - self.vis_x
        dy = ty - self.vis_y
        dist = (dx * dx + dy * dy) ** 0.5
        step = max(0.0, speed) * max(0.0, dt)
        if dist <= step or dist < 1e-6:
            self.vis_x, self.vis_y = tx, ty
        else:
            self.vis_x += dx / dist * step
            self.vis_y += dy / dist * step


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
