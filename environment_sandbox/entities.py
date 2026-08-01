"""Player, inventory, buildings, villagers, and work tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from settings import BUILDING_STORAGE_CAPACITY, INVENTORY_CAPACITY


class TaskType(Enum):
    CHOP_TREES = auto()
    PLANT_SAPLINGS = auto()
    FULL_MANAGE = auto()
    COLLECT_ROCKS = auto()
    HUNT = auto()
    FORAGE_MUSHROOMS = auto()
    FORAGE_BERRIES = auto()
    FORAGE_HERBS = auto()
    PLANT_BERRY_SEEDS = auto()
    PLANT_HERB_SEEDS = auto()
    FULL_FORAGE = auto()


TASK_LABELS: dict[TaskType, str] = {
    TaskType.CHOP_TREES: "Chop area",
    TaskType.PLANT_SAPLINGS: "Plant saplings",
    TaskType.FULL_MANAGE: "Full manage",
    TaskType.COLLECT_ROCKS: "Collect rocks",
    TaskType.HUNT: "Hunt area",
    TaskType.FORAGE_MUSHROOMS: "Forage mushrooms",
    TaskType.FORAGE_BERRIES: "Forage berries",
    TaskType.FORAGE_HERBS: "Forage herbs",
    TaskType.PLANT_BERRY_SEEDS: "Plant berry seeds",
    TaskType.PLANT_HERB_SEEDS: "Plant herb seeds",
    TaskType.FULL_FORAGE: "Full forage",
}

FORESTER_TASK_CYCLE: tuple[TaskType, ...] = (
    TaskType.CHOP_TREES,
    TaskType.PLANT_SAPLINGS,
    TaskType.FULL_MANAGE,
)

FORAGER_TASK_CYCLE: tuple[TaskType, ...] = (
    TaskType.FORAGE_MUSHROOMS,
    TaskType.FORAGE_BERRIES,
    TaskType.FORAGE_HERBS,
    TaskType.PLANT_BERRY_SEEDS,
    TaskType.PLANT_HERB_SEEDS,
    TaskType.FULL_FORAGE,
)


class BuildingKind(Enum):
    FORESTER = auto()
    MASON = auto()
    HUNTER = auto()
    FORAGER = auto()


BUILDING_LABELS: dict[BuildingKind, str] = {
    BuildingKind.FORESTER: "Forester",
    BuildingKind.MASON: "Mason",
    BuildingKind.HUNTER: "Hunter",
    BuildingKind.FORAGER: "Forager",
}


class VillagerState(Enum):
    IDLE = auto()
    WORKING = auto()
    DELIVERING = auto()
    HAULING = auto()


@dataclass
class Inventory:
    wood: int = 0
    rock: int = 0
    meat: int = 0
    saplings: int = 0
    mushrooms: int = 0
    berries: int = 0
    berry_seeds: int = 0
    herbs: int = 0
    herb_seeds: int = 0
    capacity: int = INVENTORY_CAPACITY

    @property
    def total(self) -> int:
        return (
            self.wood
            + self.rock
            + self.meat
            + self.saplings
            + self.mushrooms
            + self.berries
            + self.berry_seeds
            + self.herbs
            + self.herb_seeds
        )

    @property
    def is_full(self) -> bool:
        return self.total >= self.capacity

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    def can_add(self, amount: int = 1) -> bool:
        return self.total + amount <= self.capacity

    def add_wood(self, n: int = 1) -> bool:
        if not self.can_add(n):
            return False
        self.wood += n
        return True

    def add_rock(self, n: int = 1) -> bool:
        if not self.can_add(n):
            return False
        self.rock += n
        return True

    def add_meat(self, n: int = 1) -> bool:
        if not self.can_add(n):
            return False
        self.meat += n
        return True

    def add_saplings(self, n: int = 1) -> bool:
        if not self.can_add(n):
            return False
        self.saplings += n
        return True

    def add_mushrooms(self, n: int = 1) -> bool:
        if not self.can_add(n):
            return False
        self.mushrooms += n
        return True

    def add_berries(self, n: int = 1) -> bool:
        if not self.can_add(n):
            return False
        self.berries += n
        return True

    def add_berry_seeds(self, n: int = 1) -> bool:
        if not self.can_add(n):
            return False
        self.berry_seeds += n
        return True

    def add_herbs(self, n: int = 1) -> bool:
        if not self.can_add(n):
            return False
        self.herbs += n
        return True

    def add_herb_seeds(self, n: int = 1) -> bool:
        if not self.can_add(n):
            return False
        self.herb_seeds += n
        return True

    def consume_sapling(self) -> bool:
        if self.saplings <= 0:
            return False
        self.saplings -= 1
        return True

    def consume_berry_seed(self) -> bool:
        if self.berry_seeds <= 0:
            return False
        self.berry_seeds -= 1
        return True

    def consume_herb_seed(self) -> bool:
        if self.herb_seeds <= 0:
            return False
        self.herb_seeds -= 1
        return True

    def clear(self) -> dict[str, int]:
        deposited = {
            "wood": self.wood,
            "rock": self.rock,
            "meat": self.meat,
            "saplings": self.saplings,
            "mushrooms": self.mushrooms,
            "berries": self.berries,
            "berry_seeds": self.berry_seeds,
            "herbs": self.herbs,
            "herb_seeds": self.herb_seeds,
        }
        self.reset()
        return deposited

    def reset(self) -> None:
        self.wood = self.rock = self.meat = self.saplings = 0
        self.mushrooms = self.berries = self.berry_seeds = 0
        self.herbs = self.herb_seeds = 0


@dataclass
class HomeStorage:
    wood: int = 0
    rock: int = 0
    meat: int = 0
    saplings: int = 0
    mushrooms: int = 0
    berries: int = 0
    berry_seeds: int = 0
    herbs: int = 0
    herb_seeds: int = 0

    def deposit_dict(self, items: dict[str, int]) -> None:
        for key, value in items.items():
            setattr(self, key, getattr(self, key) + value)

    def deposit(self, wood: int = 0, rock: int = 0, meat: int = 0, saplings: int = 0, **extra) -> None:
        self.wood += wood
        self.rock += rock
        self.meat += meat
        self.saplings += saplings
        for key, value in extra.items():
            if hasattr(self, key):
                setattr(self, key, getattr(self, key) + value)

    def try_spend(self, wood: int, rock: int) -> bool:
        if self.wood < wood or self.rock < rock:
            return False
        self.wood -= wood
        self.rock -= rock
        return True

    def reset(self) -> None:
        self.wood = self.rock = self.meat = self.saplings = 0
        self.mushrooms = self.berries = self.berry_seeds = 0
        self.herbs = self.herb_seeds = 0


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


_FORAGE_KEYS = ("mushrooms", "berries", "berry_seeds", "herbs", "herb_seeds")


@dataclass
class Building:
    id: int
    kind: BuildingKind
    x: int
    y: int
    wood: int = 0
    rock: int = 0
    meat: int = 0
    saplings: int = 0
    mushrooms: int = 0
    berries: int = 0
    berry_seeds: int = 0
    herbs: int = 0
    herb_seeds: int = 0
    capacity: int = BUILDING_STORAGE_CAPACITY
    areas: list[TaskArea] = field(default_factory=list)
    draw_task_type: TaskType = TaskType.CHOP_TREES

    @property
    def stored_total(self) -> int:
        return (
            self.wood
            + self.rock
            + self.meat
            + self.saplings
            + self.mushrooms
            + self.berries
            + self.berry_seeds
            + self.herbs
            + self.herb_seeds
        )

    @property
    def space_left(self) -> int:
        return max(0, self.capacity - self.stored_total)

    def deposit_from_inventory(self, inventory: Inventory) -> None:
        if self.kind == BuildingKind.FORESTER:
            self._take(inventory, "wood")
            self._take(inventory, "saplings")
        elif self.kind == BuildingKind.MASON:
            self._take(inventory, "rock")
        elif self.kind == BuildingKind.HUNTER:
            self._take(inventory, "meat")
        elif self.kind == BuildingKind.FORAGER:
            for key in _FORAGE_KEYS:
                self._take(inventory, key)

    def _take(self, inventory: Inventory, key: str) -> None:
        room = min(self.space_left, self.capacity - getattr(self, key))
        have = getattr(inventory, key)
        take = min(have, room)
        if take <= 0:
            return
        setattr(self, key, getattr(self, key) + take)
        setattr(inventory, key, have - take)

    def withdraw_to_inventory(self, inventory: Inventory) -> None:
        keys = ("wood", "saplings", "rock", "meat", *_FORAGE_KEYS)
        for key in keys:
            while inventory.can_add(1) and getattr(self, key) > 0:
                setattr(self, key, getattr(self, key) - 1)
                setattr(inventory, key, getattr(inventory, key) + 1)

    def give_item_to(self, inventory: Inventory, key: str) -> bool:
        if getattr(self, key) <= 0 or not inventory.can_add(1):
            return False
        setattr(self, key, getattr(self, key) - 1)
        setattr(inventory, key, getattr(inventory, key) + 1)
        return True

    def give_sapling_to(self, inventory: Inventory) -> bool:
        return self.give_item_to(inventory, "saplings")

    def cycle_draw_task(self) -> TaskType:
        if self.kind == BuildingKind.FORESTER:
            order = FORESTER_TASK_CYCLE
            idx = order.index(self.draw_task_type) if self.draw_task_type in order else 0
            self.draw_task_type = order[(idx + 1) % len(order)]
        elif self.kind == BuildingKind.MASON:
            self.draw_task_type = TaskType.COLLECT_ROCKS
        elif self.kind == BuildingKind.HUNTER:
            self.draw_task_type = TaskType.HUNT
        else:
            order = FORAGER_TASK_CYCLE
            idx = order.index(self.draw_task_type) if self.draw_task_type in order else 0
            self.draw_task_type = order[(idx + 1) % len(order)]
        return self.draw_task_type

    def default_draw_task(self) -> TaskType:
        if self.kind == BuildingKind.FORESTER:
            return TaskType.CHOP_TREES
        if self.kind == BuildingKind.MASON:
            return TaskType.COLLECT_ROCKS
        if self.kind == BuildingKind.HUNTER:
            return TaskType.HUNT
        return TaskType.FULL_FORAGE


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

    def clear_assignment(self) -> None:
        self.building_id = None
        self.assigned_to_home = False
        self.haul_building_id = None
        self.hunt_animal_id = None
        self.hunt_meat_pos = None
        self.state = VillagerState.IDLE
        self.target = None


@dataclass
class Player:
    x: int
    y: int
    inventory: Inventory = field(default_factory=Inventory)

    def move_to(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def reset(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
        self.inventory.reset()
