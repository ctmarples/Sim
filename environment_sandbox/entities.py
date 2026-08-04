"""Player, inventory, buildings, villagers, and work tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from crops import PRODUCE_KEYS, SEED_KEYS
from settings import (
    BUILDING_FOOTPRINT,
    BUILDING_STORAGE_CAPACITY,
    INVENTORY_CAPACITY,
    SEED_CARRY_CAPACITY,
)
from trees import SAPLING_ITEM_KEYS, sapling_item_key

# Seeds share a dedicated carry pool (separate from wood/food/etc.).
SEED_ITEM_KEYS: tuple[str, ...] = ("berry_seeds", *SEED_KEYS)


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


TASK_LABELS: dict[TaskType, str] = {
    TaskType.CHOP_TREES: "Chop area",
    TaskType.PLANT_SAPLINGS: "Plant saplings",
    TaskType.FULL_MANAGE: "Full manage",
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
}


class WorkMode(Enum):
    """Workplace behaviour: gather resources, plant, or both."""

    COLLECT = auto()
    PLANT = auto()
    BOTH = auto()


WORK_MODE_LABELS: dict[WorkMode, str] = {
    WorkMode.COLLECT: "Collect",
    WorkMode.PLANT: "Plant",
    WorkMode.BOTH: "Both",
}

WORK_MODE_SHORT: dict[WorkMode, str] = {
    WorkMode.COLLECT: "C",
    WorkMode.PLANT: "P",
    WorkMode.BOTH: "B",
}

# Order used when cycling the behaviour toggle.
WORK_MODE_CYCLE_PLANTABLE: tuple[WorkMode, ...] = (
    WorkMode.COLLECT,
    WorkMode.PLANT,
    WorkMode.BOTH,
)

FORESTER_TASK_CYCLE: tuple[TaskType, ...] = (
    TaskType.CHOP_TREES,
    TaskType.PLANT_SAPLINGS,
    TaskType.FULL_MANAGE,
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
}


def default_building_plot(kind: BuildingKind) -> tuple[int, int]:
    """Default footprint size. Fields are drag-sized; all other buildings are square."""
    if kind == BuildingKind.FIELD:
        return 1, 1
    n = max(1, int(BUILDING_FOOTPRINT))
    return n, n


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
    wood: int = 0
    hardwood: int = 0
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
    wheat_seeds: int = 0
    flax_seeds: int = 0
    sage_seeds: int = 0
    hemp_seeds: int = 0
    rye_seeds: int = 0
    onion_seeds: int = 0
    cabbage_seeds: int = 0
    carrot_seeds: int = 0
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
            self.wood
            + self.hardwood
            + self.rock
            + self.meat
            + self.fish
            + self.saplings
            + self.mushrooms
            + self.berries
            + self.reeds
            + sum(getattr(self, key) for key in PRODUCE_KEYS)
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

    def add_wood(self, n: int = 1) -> bool:
        return self.add_item("wood", n)

    def add_hardwood(self, n: int = 1) -> bool:
        return self.add_item("hardwood", n)

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

    def clear(self) -> dict[str, int]:
        deposited = {
            "wood": self.wood,
            "hardwood": self.hardwood,
            "rock": self.rock,
            "meat": self.meat,
            "fish": self.fish,
            "mushrooms": self.mushrooms,
            "berries": self.berries,
            "berry_seeds": self.berry_seeds,
            "reeds": self.reeds,
            **{key: getattr(self, key) for key in SAPLING_ITEM_KEYS},
            **{key: getattr(self, key) for key in PRODUCE_KEYS},
            **{key: getattr(self, key) for key in SEED_KEYS},
        }
        self.reset()
        return deposited

    def reset(self) -> None:
        self.wood = self.hardwood = self.rock = self.meat = self.fish = 0
        self.mushrooms = self.berries = self.berry_seeds = self.reeds = 0
        for key in SAPLING_ITEM_KEYS + PRODUCE_KEYS + SEED_KEYS:
            setattr(self, key, 0)


@dataclass
class HomeStorage:
    wood: int = 0
    hardwood: int = 0
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
    wheat_seeds: int = 0
    flax_seeds: int = 0
    sage_seeds: int = 0
    hemp_seeds: int = 0
    rye_seeds: int = 0
    onion_seeds: int = 0
    cabbage_seeds: int = 0
    carrot_seeds: int = 0

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
        self.wood += wood
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
        if self.wood < wood or self.rock < rock:
            return False
        self.wood -= wood
        self.rock -= rock
        return True

    def reset(self) -> None:
        self.wood = self.hardwood = self.rock = self.meat = self.fish = 0
        self.mushrooms = self.berries = self.berry_seeds = self.reeds = 0
        for key in SAPLING_ITEM_KEYS + PRODUCE_KEYS + SEED_KEYS:
            setattr(self, key, 0)

    def withdraw_keys_to(self, inventory: Inventory, keys: tuple[str, ...]) -> int:
        taken = 0
        for key in keys:
            taken += self.withdraw_key_to(inventory, key)
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


@dataclass
class Building:
    id: int
    kind: BuildingKind
    x: int
    y: int
    wood: int = 0
    hardwood: int = 0
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
    wheat_seeds: int = 0
    flax_seeds: int = 0
    sage_seeds: int = 0
    hemp_seeds: int = 0
    rye_seeds: int = 0
    onion_seeds: int = 0
    cabbage_seeds: int = 0
    carrot_seeds: int = 0
    capacity: int = BUILDING_STORAGE_CAPACITY
    areas: list[TaskArea] = field(default_factory=list)
    fields: list[FarmField] = field(default_factory=list)  # legacy; migrated away
    # Standalone Field plot size (origin at x,y) and crop plans.
    plot_w: int = 1
    plot_h: int = 1
    plans: list[CropPlan] = field(default_factory=list)
    draw_task_type: TaskType = TaskType.FULL_MANAGE
    work_mode: WorkMode = WorkMode.BOTH
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
            self.wood
            + self.hardwood
            + self.rock
            + self.meat
            + self.fish
            + self.saplings
            + self.mushrooms
            + self.berries
            + self.berry_seeds
            + self.reeds
            + sum(getattr(self, key) for key in PRODUCE_KEYS)
            + sum(getattr(self, key) for key in SEED_KEYS)
        )

    @property
    def space_left(self) -> int:
        return max(0, self.capacity - self.stored_total)

    def deposit_from_inventory(
        self, inventory: Inventory, *, keep_plantables: bool = False
    ) -> None:
        keys = self.depositable_keys()
        if keep_plantables:
            keys = tuple(
                k
                for k in keys
                if k not in (*SAPLING_ITEM_KEYS, "berry_seeds", *SEED_KEYS)
            )
        for key in keys:
            self._take(inventory, key)

    def deposit_key_from(self, inventory: Inventory, key: str) -> int:
        """Deposit as much of one key as capacity allows. Returns amount moved."""
        if key not in self.depositable_keys():
            return 0
        before = int(getattr(inventory, key, 0))
        self._take(inventory, key)
        return before - int(getattr(inventory, key, 0))

    def deposit_one_from(self, inventory: Inventory, key: str) -> bool:
        """Deposit a single unit of ``key`` if capacity allows."""
        if key not in self.depositable_keys() or self.space_left <= 0:
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
                "wood",
                "hardwood",
                "rock",
                "meat",
                "fish",
                *SAPLING_ITEM_KEYS,
                "mushrooms",
                "berries",
                "berry_seeds",
                "reeds",
            ) + PRODUCE_KEYS + SEED_KEYS
        if self.kind == BuildingKind.WORKSTATION:
            return ()
        if self.kind == BuildingKind.FORESTER:
            return ("wood", "hardwood", *SAPLING_ITEM_KEYS)
        if self.kind == BuildingKind.MASON:
            return ("rock",)
        if self.kind == BuildingKind.HUNTER:
            return ("meat",)
        if self.kind == BuildingKind.FISHER:
            return ("fish",)
        if self.kind == BuildingKind.FORAGER:
            return _FORAGE_KEYS
        if self.kind == BuildingKind.FARM:
            return PRODUCE_KEYS + SEED_KEYS
        if self.kind == BuildingKind.FIELD:
            return ()
        return ()

    def haul_keys(self) -> tuple[str, ...]:
        """Items home haulers may remove. Plant stock is reserved while planting."""
        if self.kind == BuildingKind.FORESTER:
            if self.work_mode == WorkMode.COLLECT:
                return ("wood", "hardwood", *SAPLING_ITEM_KEYS)
            return ("wood", "hardwood")
        if self.kind == BuildingKind.FORAGER:
            return _FORAGE_KEYS
        if self.kind == BuildingKind.FARM:
            return PRODUCE_KEYS
        return self.depositable_keys()

    def plant_keys(self) -> tuple[str, ...]:
        if self.kind == BuildingKind.FORESTER:
            return SAPLING_ITEM_KEYS
        if self.kind == BuildingKind.FARM:
            return SEED_KEYS
        return ()

    def haulable_total(self) -> int:
        return sum(getattr(self, key, 0) for key in self.haul_keys())

    def can_accept_from(self, inventory: Inventory) -> bool:
        """True if inventory holds at least one item this building will store."""
        if self.space_left <= 0:
            return False
        return any(getattr(inventory, key, 0) > 0 for key in self.depositable_keys())

    def _take(self, inventory: Inventory, key: str) -> None:
        room = min(self.space_left, self.capacity - getattr(self, key))
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
            while getattr(self, key) > 0 and inventory.can_add(1, key=key):
                setattr(self, key, getattr(self, key) - 1)
                setattr(inventory, key, getattr(inventory, key) + 1)

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
        if self.kind in (BuildingKind.HOME, BuildingKind.WORKSTATION):
            return ()
        if self.kind in (BuildingKind.FORESTER, BuildingKind.FARM):
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
                WorkMode.BOTH: TaskType.FULL_MANAGE,
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
            return WorkMode.BOTH
        if kind == BuildingKind.FARM:
            return WorkMode.BOTH
        return WorkMode.COLLECT

    def default_work_mode(self) -> WorkMode:
        if self.kind == BuildingKind.FORESTER:
            return WorkMode.BOTH
        if self.kind == BuildingKind.FARM:
            return WorkMode.BOTH
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
    last_food: str | None = None

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
