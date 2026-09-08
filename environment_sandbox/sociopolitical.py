"""Sociopolitical sandbox: values, principles, institutions, and decision events.

First-test design (data-driven): three settlement values, four principle
categories, four institutions, two recruitment policies, and a fixed event deck.
Values summarise history and colour decisions; institutions supply the only
persistent mechanical modifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


VALUE_MIN = 0
VALUE_MAX = 100
VALUE_NEUTRAL = 50
VALUE_SHIFT_DEFAULT = 10

INSTITUTION_PRINCIPLE_THRESHOLD = 3
TEST_SEASON_LIMIT = 8

# Institution effect placeholders (noticeable, not balanced).
OFFICE_WORK_EFFICIENCY = 0.10
OFFICE_MISMATCH_HAPPINESS = -5
PROVISION_RATION_HAPPINESS_REDUCTION = 0.25
EXCHANGE_MATCH_EFFICIENCY = 0.10
EXCHANGE_SEASON_PAY_COINS = 3  # vs society.SEASON_MISSING_REQ_PAY_COINS (2)
COVENANT_ECOLOGY_BONUS = 0.10
COVENANT_EXTRACTIVE_SLOWDOWN = 0.10

CONTRACT_SEASON_PAY_DEFAULT = 2


class PrincipleCategory(str, Enum):
    COMMAND = "command"
    MUTUAL_AID = "mutual_aid"
    ENTERPRISE = "enterprise"
    STEWARDSHIP = "stewardship"


class RecruitmentPolicy(str, Enum):
    CONTRACT = "contract"
    OPEN_ADMISSION = "open_admission"


CATEGORY_LABELS: dict[PrincipleCategory, str] = {
    PrincipleCategory.COMMAND: "Command",
    PrincipleCategory.MUTUAL_AID: "Mutual Aid",
    PrincipleCategory.ENTERPRISE: "Enterprise",
    PrincipleCategory.STEWARDSHIP: "Stewardship",
}

CATEGORY_INSTITUTION_ID: dict[PrincipleCategory, str] = {
    PrincipleCategory.COMMAND: "settlement_office",
    PrincipleCategory.MUTUAL_AID: "common_provision",
    PrincipleCategory.ENTERPRISE: "labour_exchange",
    PrincipleCategory.STEWARDSHIP: "covenant_of_the_land",
}


@dataclass(frozen=True)
class Principle:
    id: str
    name: str
    category: PrincipleCategory
    description: str
    source_event_id: str


@dataclass(frozen=True)
class InstitutionDef:
    id: str
    name: str
    category: PrincipleCategory
    description: str
    benefit: str
    cost: str


@dataclass(frozen=True)
class ImmediateEffect:
    """Fixed, guaranteed consequences of a decision option."""

    kind: str
    amount: float = 0.0
    label: str = ""


@dataclass(frozen=True)
class DecisionOption:
    id: str
    label: str
    principle_id: str
    value_changes: dict[str, int]
    immediate_effects: tuple[ImmediateEffect, ...]
    summary_line: str
    # Optional: switch recruitment policy when chosen.
    set_recruitment_policy: RecruitmentPolicy | None = None


@dataclass(frozen=True)
class DecisionEvent:
    id: str
    trigger: str
    title: str
    description: str
    options: tuple[DecisionOption, ...]


@dataclass
class DiaryEntry:
    day: int
    kind: str  # principle | institution | decision | note
    text: str
    detail: str = ""


@dataclass
class PendingInstitutionReveal:
    institution_id: str
    principle_ids: tuple[str, ...]
    summary_lines: tuple[str, ...]


@dataclass
class OpenApplicant:
    """Open-admission candidate waiting for accept/refuse."""

    name: str
    skills: dict[str, int]
    housing_need: int = 1
    required_foods: list[str] = field(default_factory=lambda: ["bread"])
    favourite_foods: list[str] = field(default_factory=list)
    template_id: str = ""
    portrait_seed: int = 0
    happiness: float = 0.65
    energy: float = 1.0
    satiation: float = 0.8

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "skills": dict(self.skills),
            "housing_need": self.housing_need,
            "required_foods": list(self.required_foods),
            "favourite_foods": list(self.favourite_foods),
            "template_id": self.template_id,
            "portrait_seed": self.portrait_seed,
            "happiness": self.happiness,
            "energy": self.energy,
            "satiation": self.satiation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OpenApplicant:
        return cls(
            name=str(data.get("name", "Applicant")),
            skills={str(k): int(v) for k, v in dict(data.get("skills") or {}).items()},
            housing_need=max(1, int(data.get("housing_need", 1) or 1)),
            required_foods=list(data.get("required_foods") or ["bread"]),
            favourite_foods=list(data.get("favourite_foods") or []),
            template_id=str(data.get("template_id", "") or ""),
            portrait_seed=int(data.get("portrait_seed", 0) or 0),
            happiness=float(data.get("happiness", 0.65) or 0.65),
            energy=float(data.get("energy", 1.0) or 1.0),
            satiation=float(data.get("satiation", 0.8) or 0.8),
        )


@dataclass
class SettlementPoliticalState:
    authority: int = VALUE_NEUTRAL
    solidarity: int = VALUE_NEUTRAL
    stewardship: int = VALUE_NEUTRAL
    enacted_principle_ids: list[str] = field(default_factory=list)
    institution_ids: list[str] = field(default_factory=list)
    recruitment_policy: RecruitmentPolicy = RecruitmentPolicy.CONTRACT
    seasons_elapsed: int = 0
    decisions_resolved: int = 0
    diary: list[DiaryEntry] = field(default_factory=list)
    fired_event_ids: list[str] = field(default_factory=list)
    pending_reveal: PendingInstitutionReveal | None = None
    active_event_id: str | None = None
    seasonal_work_bonus: float = 0.0  # from immediate effects this season
    seasonal_work_source: str = ""  # short cause label for the seasonal bonus
    settlement_ration_mode: str = "NORMAL"  # Common Provision lock
    open_applicant: OpenApplicant | None = None
    # Metrics for end-of-test summary
    starting_population: int = 0
    gold_spent_recruitment: int = 0
    villagers_accepted: int = 0
    villagers_refused: int = 0
    happiness_samples: list[float] = field(default_factory=list)
    efficiency_samples: list[float] = field(default_factory=list)
    ecology_samples: list[float] = field(default_factory=list)
    cumulative_happiness_delta: float = 0.0
    test_active: bool = False
    summary_shown: bool = False
    principle_source_lines: dict[str, str] = field(default_factory=dict)

    def clamp_values(self) -> None:
        self.authority = max(VALUE_MIN, min(VALUE_MAX, int(self.authority)))
        self.solidarity = max(VALUE_MIN, min(VALUE_MAX, int(self.solidarity)))
        self.stewardship = max(VALUE_MIN, min(VALUE_MAX, int(self.stewardship)))

    def reset_politics(self) -> None:
        """Clear values / principles / institutions; keep test_active and metrics."""
        self.authority = VALUE_NEUTRAL
        self.solidarity = VALUE_NEUTRAL
        self.stewardship = VALUE_NEUTRAL
        self.enacted_principle_ids.clear()
        self.institution_ids.clear()
        self.diary.clear()
        self.fired_event_ids.clear()
        self.pending_reveal = None
        self.active_event_id = None
        self.seasonal_work_bonus = 0.0
        self.seasonal_work_source = ""
        self.settlement_ration_mode = "NORMAL"
        self.principle_source_lines.clear()
        self.decisions_resolved = 0
        self.summary_shown = False
        self.add_diary(0, "note", "Sociopolitical state reset.")

    def add_diary(self, day: int, kind: str, text: str, detail: str = "") -> None:
        self.diary.append(DiaryEntry(day=int(day), kind=kind, text=text, detail=detail))
        if len(self.diary) > 80:
            self.diary = self.diary[-80:]

    def has_institution(self, institution_id: str) -> bool:
        return institution_id in self.institution_ids

    def has_category_institution(self, category: PrincipleCategory) -> bool:
        return self.has_institution(CATEGORY_INSTITUTION_ID[category])

    def principle_count(self, category: PrincipleCategory) -> int:
        return sum(
            1
            for pid in self.enacted_principle_ids
            if PRINCIPLES[pid].category == category
        )

    def category_progress(self) -> dict[PrincipleCategory, tuple[int, int]]:
        return {
            cat: (self.principle_count(cat), INSTITUTION_PRINCIPLE_THRESHOLD)
            for cat in PrincipleCategory
        }

    def active_effects(self) -> list[str]:
        lines: list[str] = []
        for iid in self.institution_ids:
            inst = INSTITUTIONS.get(iid)
            if inst is None:
                continue
            lines.append(f"{inst.name}: {inst.benefit}")
            lines.append(f"{inst.name}: {inst.cost}")
        if self.seasonal_work_bonus:
            source = str(self.seasonal_work_source or "").strip() or "decision"
            lines.append(
                f"Seasonal bonus from {source}: "
                f"{self.seasonal_work_bonus:+.0%} work efficiency"
            )
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "solidarity": self.solidarity,
            "stewardship": self.stewardship,
            "enacted_principle_ids": list(self.enacted_principle_ids),
            "institution_ids": list(self.institution_ids),
            "recruitment_policy": self.recruitment_policy.value,
            "seasons_elapsed": self.seasons_elapsed,
            "decisions_resolved": self.decisions_resolved,
            "diary": [
                {"day": e.day, "kind": e.kind, "text": e.text, "detail": e.detail}
                for e in self.diary
            ],
            "fired_event_ids": list(self.fired_event_ids),
            "active_event_id": self.active_event_id,
            "seasonal_work_bonus": self.seasonal_work_bonus,
            "seasonal_work_source": self.seasonal_work_source,
            "settlement_ration_mode": self.settlement_ration_mode,
            "open_applicant": (
                self.open_applicant.to_dict() if self.open_applicant else None
            ),
            "starting_population": self.starting_population,
            "gold_spent_recruitment": self.gold_spent_recruitment,
            "villagers_accepted": self.villagers_accepted,
            "villagers_refused": self.villagers_refused,
            "happiness_samples": list(self.happiness_samples),
            "efficiency_samples": list(self.efficiency_samples),
            "ecology_samples": list(self.ecology_samples),
            "cumulative_happiness_delta": self.cumulative_happiness_delta,
            "test_active": self.test_active,
            "summary_shown": self.summary_shown,
            "principle_source_lines": dict(self.principle_source_lines),
            "pending_reveal": (
                {
                    "institution_id": self.pending_reveal.institution_id,
                    "principle_ids": list(self.pending_reveal.principle_ids),
                    "summary_lines": list(self.pending_reveal.summary_lines),
                }
                if self.pending_reveal
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SettlementPoliticalState:
        if not data:
            return cls()
        state = cls(
            authority=int(data.get("authority", VALUE_NEUTRAL)),
            solidarity=int(data.get("solidarity", VALUE_NEUTRAL)),
            stewardship=int(data.get("stewardship", VALUE_NEUTRAL)),
            enacted_principle_ids=list(data.get("enacted_principle_ids") or []),
            institution_ids=list(data.get("institution_ids") or []),
            seasons_elapsed=int(data.get("seasons_elapsed", 0) or 0),
            decisions_resolved=int(data.get("decisions_resolved", 0) or 0),
            fired_event_ids=list(data.get("fired_event_ids") or []),
            active_event_id=data.get("active_event_id"),
            seasonal_work_bonus=float(data.get("seasonal_work_bonus", 0) or 0),
            seasonal_work_source=str(data.get("seasonal_work_source", "") or ""),
            settlement_ration_mode=str(data.get("settlement_ration_mode", "NORMAL")),
            starting_population=int(data.get("starting_population", 0) or 0),
            gold_spent_recruitment=int(data.get("gold_spent_recruitment", 0) or 0),
            villagers_accepted=int(data.get("villagers_accepted", 0) or 0),
            villagers_refused=int(data.get("villagers_refused", 0) or 0),
            happiness_samples=[float(x) for x in data.get("happiness_samples") or []],
            efficiency_samples=[float(x) for x in data.get("efficiency_samples") or []],
            ecology_samples=[float(x) for x in data.get("ecology_samples") or []],
            cumulative_happiness_delta=float(
                data.get("cumulative_happiness_delta", 0) or 0
            ),
            test_active=bool(data.get("test_active", False)),
            summary_shown=bool(data.get("summary_shown", False)),
            principle_source_lines={
                str(k): str(v)
                for k, v in dict(data.get("principle_source_lines") or {}).items()
            },
        )
        try:
            state.recruitment_policy = RecruitmentPolicy(
                str(data.get("recruitment_policy", "contract"))
            )
        except ValueError:
            state.recruitment_policy = RecruitmentPolicy.CONTRACT
        for raw in data.get("diary") or []:
            state.diary.append(
                DiaryEntry(
                    day=int(raw.get("day", 0)),
                    kind=str(raw.get("kind", "note")),
                    text=str(raw.get("text", "")),
                    detail=str(raw.get("detail", "")),
                )
            )
        applicant = data.get("open_applicant")
        if isinstance(applicant, dict):
            state.open_applicant = OpenApplicant.from_dict(applicant)
        reveal = data.get("pending_reveal")
        if isinstance(reveal, dict) and reveal.get("institution_id"):
            state.pending_reveal = PendingInstitutionReveal(
                institution_id=str(reveal["institution_id"]),
                principle_ids=tuple(str(x) for x in reveal.get("principle_ids") or []),
                summary_lines=tuple(str(x) for x in reveal.get("summary_lines") or []),
            )
        state.clamp_values()
        return state


# ---------------------------------------------------------------------------
# Content catalogues
# ---------------------------------------------------------------------------

PRINCIPLES: dict[str, Principle] = {
    "assigned_labour": Principle(
        "assigned_labour",
        "Assigned Labour",
        PrincipleCategory.COMMAND,
        "Work roles are directed by settlement authority.",
        "work_organisation",
    ),
    "voluntary_priorities": Principle(
        "voluntary_priorities",
        "Voluntary Priorities",
        PrincipleCategory.ENTERPRISE,
        "Workers choose priorities according to inclination and reward.",
        "work_organisation",
    ),
    "common_harvest": Principle(
        "common_harvest",
        "Common Harvest",
        PrincipleCategory.MUTUAL_AID,
        "Food produced by the settlement belongs to everyone.",
        "first_harvest",
    ),
    "rewarded_labour": Principle(
        "rewarded_labour",
        "Rewarded Labour",
        PrincipleCategory.ENTERPRISE,
        "Those who work the fields keep a greater share of the yield.",
        "first_harvest",
    ),
    "equal_rations": Principle(
        "equal_rations",
        "Equal Rations",
        PrincipleCategory.MUTUAL_AID,
        "Everyone eats according to the same ration setting.",
        "low_food",
    ),
    "directed_rations": Principle(
        "directed_rations",
        "Directed Rations",
        PrincipleCategory.COMMAND,
        "Rations are allocated according to settlement need.",
        "low_food",
    ),
    "open_door": Principle(
        "open_door",
        "Open Door",
        PrincipleCategory.MUTUAL_AID,
        "Empty housing may be offered to whoever arrives.",
        "empty_house",
    ),
    "admission_by_need": Principle(
        "admission_by_need",
        "Admission by Need",
        PrincipleCategory.STEWARDSHIP,
        "Admission is judged against settlement capacity and care of the land.",
        "empty_house",
    ),
    "private_contract": Principle(
        "private_contract",
        "Private Contract",
        PrincipleCategory.ENTERPRISE,
        "Compensation for unmet needs is an individual bargain.",
        "first_paid_recruit",
    ),
    "equal_provision": Principle(
        "equal_provision",
        "Equal Provision",
        PrincipleCategory.MUTUAL_AID,
        "Newcomers share the same provision terms as everyone else.",
        "first_paid_recruit",
    ),
    "shared_burdens": Principle(
        "shared_burdens",
        "Shared Burdens",
        PrincipleCategory.MUTUAL_AID,
        "Unpleasant work rotates so no one bears it alone.",
        "unpleasant_job",
    ),
    "necessary_assignments": Principle(
        "necessary_assignments",
        "Necessary Assignments",
        PrincipleCategory.COMMAND,
        "Hard tasks are assigned to those best able to finish them.",
        "unpleasant_job",
    ),
    "protected_habitat": Principle(
        "protected_habitat",
        "Protected Habitat",
        PrincipleCategory.STEWARDSHIP,
        "Habitat is not cleared merely for convenience.",
        "habitat_removal",
    ),
    "land_for_use": Principle(
        "land_for_use",
        "Land for Use",
        PrincipleCategory.ENTERPRISE,
        "Productive need may override habitat when the settlement requires it.",
        "habitat_removal",
    ),
    "specialist_reward": Principle(
        "specialist_reward",
        "Specialist Reward",
        PrincipleCategory.ENTERPRISE,
        "Skilled workers decide within their profession and keep the reward.",
        "skilled_joins",
    ),
    "central_direction": Principle(
        "central_direction",
        "Central Direction",
        PrincipleCategory.COMMAND,
        "Even specialists work under settlement direction.",
        "skilled_joins",
    ),
    "compensated_labour": Principle(
        "compensated_labour",
        "Compensated Labour",
        PrincipleCategory.ENTERPRISE,
        "Hard or voluntary work is paid from the common purse.",
        "unpleasant_job",
    ),
}


INSTITUTIONS: dict[str, InstitutionDef] = {
    "settlement_office": InstitutionDef(
        "settlement_office",
        "Settlement Office",
        PrincipleCategory.COMMAND,
        "The Settlement Office now coordinates communal work.",
        "+10% work efficiency.",
        "−5 happiness when assigned outside preferred / strongest skill.",
    ),
    "common_provision": InstitutionDef(
        "common_provision",
        "Common Provision",
        PrincipleCategory.MUTUAL_AID,
        "Common Provision shares food and shelter as a public trust.",
        "Poor or missing rations cause 25% less happiness loss.",
        "All villagers share one ration setting; individual adjustment is disabled.",
    ),
    "labour_exchange": InstitutionDef(
        "labour_exchange",
        "Labour Exchange",
        PrincipleCategory.ENTERPRISE,
        "The Labour Exchange prices skill and contribution.",
        "+10% work efficiency when job matches strongest skill.",
        "Recruitment compensation for unmet requirements rises to 3 gold/season.",
    ),
    "covenant_of_the_land": InstitutionDef(
        "covenant_of_the_land",
        "Covenant of the Land",
        PrincipleCategory.STEWARDSHIP,
        "The Covenant of the Land binds production to ecological care.",
        "+10% ecological recovery near the settlement.",
        "Tree cutting and new field establishment take 10% longer.",
    ),
}


DECISION_EVENTS: dict[str, DecisionEvent] = {
    "work_organisation": DecisionEvent(
        "work_organisation",
        "sandbox_start",
        "How should work be organised?",
        "The settlement has survived its first hard seasons. "
        "Someone must decide how daily labour is arranged.",
        (
            DecisionOption(
                "assigned",
                "Assign labour from the centre",
                "assigned_labour",
                {"authority": VALUE_SHIFT_DEFAULT, "solidarity": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "work_efficiency_season", 0.10, "+10% work efficiency this season"
                    ),
                ),
                "We assigned workers according to settlement need.",
            ),
            DecisionOption(
                "voluntary",
                "Let villagers set their own priorities",
                "voluntary_priorities",
                {"authority": -VALUE_SHIFT_DEFAULT, "solidarity": VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect("happiness_all", 3, "All villagers +3 happiness"),
                ),
                "We let people choose their own work priorities.",
            ),
        ),
    ),
    "first_harvest": DecisionEvent(
        "first_harvest",
        "first_harvest",
        "Who owns the harvest?",
        "The first full harvest is in. Grain and roots wait in the storehouse.",
        (
            DecisionOption(
                "common",
                "Common harvest — food belongs to everyone",
                "common_harvest",
                {"solidarity": VALUE_SHIFT_DEFAULT, "authority": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect("happiness_all", 4, "All villagers +4 happiness"),
                ),
                "We shared the harvest as common food.",
            ),
            DecisionOption(
                "rewarded",
                "Rewarded labour — field workers keep a greater share",
                "rewarded_labour",
                {"solidarity": -VALUE_SHIFT_DEFAULT, "authority": VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "happiness_workers", 6, "Assigned field workers +6 happiness"
                    ),
                    ImmediateEffect("gold", 4, "+4 gold from sales of surplus shares"),
                ),
                "We rewarded those who worked the fields with a greater share.",
            ),
        ),
    ),
    "low_food": DecisionEvent(
        "low_food",
        "low_food",
        "How should rations be allocated?",
        "Stores are thin. The settlement must decide how food is portioned.",
        (
            DecisionOption(
                "equal",
                "Equal rations for all",
                "equal_rations",
                {"solidarity": VALUE_SHIFT_DEFAULT, "authority": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect("set_ration_all", 0, "All villagers set to Normal rations"),
                    ImmediateEffect("happiness_all", 2, "All villagers +2 happiness"),
                ),
                "We directed equal rations during the shortage.",
            ),
            DecisionOption(
                "directed",
                "Directed rations by need and role",
                "directed_rations",
                {"authority": VALUE_SHIFT_DEFAULT, "solidarity": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "set_ration_workers_double",
                        0,
                        "Workers on Double; others on Half",
                    ),
                ),
                "We directed rations according to settlement roles.",
            ),
        ),
    ),
    "empty_house": DecisionEvent(
        "empty_house",
        "empty_house",
        "Who may settle here?",
        "An empty bed waits. Word of the settlement has reached travellers.",
        (
            DecisionOption(
                "open",
                "Open door — welcome whoever arrives",
                "open_door",
                {"solidarity": VALUE_SHIFT_DEFAULT, "stewardship": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "set_policy_open", 0, "Recruitment policy → Open Admission"
                    ),
                ),
                "We opened the door to whoever arrives.",
                set_recruitment_policy=RecruitmentPolicy.OPEN_ADMISSION,
            ),
            DecisionOption(
                "need",
                "Admission by need and capacity",
                "admission_by_need",
                {"stewardship": VALUE_SHIFT_DEFAULT, "solidarity": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "set_policy_contract", 0, "Recruitment policy → Contract"
                    ),
                ),
                "We judged admission against need and the land's capacity.",
                set_recruitment_policy=RecruitmentPolicy.CONTRACT,
            ),
        ),
    ),
    "first_paid_recruit": DecisionEvent(
        "first_paid_recruit",
        "first_paid_recruit",
        "Is compensation individual?",
        "A skilled traveller will join only if unmet needs are paid in coin.",
        (
            DecisionOption(
                "private",
                "Private contract — pay unmet requirements individually",
                "private_contract",
                {"authority": VALUE_SHIFT_DEFAULT, "solidarity": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "set_policy_contract", 0, "Recruitment policy → Contract"
                    ),
                    ImmediateEffect("gold", -6, "−6 gold as a signing gesture"),
                ),
                "We treated compensation as a private bargain.",
                set_recruitment_policy=RecruitmentPolicy.CONTRACT,
            ),
            DecisionOption(
                "equal_prov",
                "Equal provision — same terms as everyone",
                "equal_provision",
                {"solidarity": VALUE_SHIFT_DEFAULT, "authority": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect("happiness_all", 3, "All villagers +3 happiness"),
                ),
                "We offered equal provision rather than private wages.",
            ),
        ),
    ),
    "unpleasant_job": DecisionEvent(
        "unpleasant_job",
        "unpleasant_job",
        "Who should clear the drainage ditch?",
        "A drainage ditch must be cleared before winter.",
        (
            DecisionOption(
                "everyone",
                "Everyone takes a turn",
                "shared_burdens",
                {"solidarity": VALUE_SHIFT_DEFAULT, "authority": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect("happiness_all", -2, "All villagers −2 happiness"),
                ),
                "We shared the ditch work so everyone took a turn.",
            ),
            DecisionOption(
                "assign",
                "Assign the fastest workers",
                "necessary_assignments",
                {"authority": VALUE_SHIFT_DEFAULT, "solidarity": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "work_efficiency_season",
                        0.20,
                        "Ditch / labour work +20% efficiency this season",
                    ),
                ),
                "We assigned the fastest workers to finish the ditch.",
            ),
            DecisionOption(
                "pay",
                "Pay volunteers",
                "compensated_labour",
                {"authority": -5, "solidarity": 5},
                (
                    ImmediateEffect("gold", -8, "−8 gold"),
                    ImmediateEffect(
                        "happiness_workers", 5, "Assigned villagers +5 happiness"
                    ),
                ),
                "We paid volunteers to clear the ditch.",
            ),
        ),
    ),
    "habitat_removal": DecisionEvent(
        "habitat_removal",
        "habitat_removal",
        "Can productive need override habitat?",
        "A thicket shelters wildlife where a new field would grow well.",
        (
            DecisionOption(
                "protect",
                "Protect the habitat",
                "protected_habitat",
                {"stewardship": VALUE_SHIFT_DEFAULT, "authority": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "ecology_boost", 0.05, "Nearby disturbance eases slightly"
                    ),
                ),
                "We protected habitat rather than clear it for a field.",
            ),
            DecisionOption(
                "use",
                "Clear land for use",
                "land_for_use",
                {"stewardship": -VALUE_SHIFT_DEFAULT, "authority": VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect("gold", 5, "+5 gold from cleared timber / forage"),
                    ImmediateEffect(
                        "ecology_harm", 0.08, "Local disturbance rises"
                    ),
                ),
                "We cleared land for productive use.",
            ),
        ),
    ),
    "skilled_joins": DecisionEvent(
        "skilled_joins",
        "skilled_joins",
        "Who decides within their profession?",
        "A skilled villager has settled in. How much autonomy do they keep?",
        (
            DecisionOption(
                "specialist",
                "Specialist reward — they decide within their craft",
                "specialist_reward",
                {"authority": -VALUE_SHIFT_DEFAULT, "solidarity": VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "happiness_skilled", 5, "Highest-skilled villagers +5 happiness"
                    ),
                ),
                "We let specialists decide within their profession.",
            ),
            DecisionOption(
                "central",
                "Central direction — the settlement decides",
                "central_direction",
                {"authority": VALUE_SHIFT_DEFAULT, "solidarity": -VALUE_SHIFT_DEFAULT},
                (
                    ImmediateEffect(
                        "work_efficiency_season", 0.10, "+10% work efficiency this season"
                    ),
                ),
                "We kept specialists under central direction.",
            ),
        ),
    ),
}

EVENT_ORDER: tuple[str, ...] = (
    "work_organisation",
    "first_harvest",
    "low_food",
    "empty_house",
    "first_paid_recruit",
    "unpleasant_job",
    "habitat_removal",
    "skilled_joins",
)


def principle_by_id(principle_id: str) -> Principle | None:
    return PRINCIPLES.get(principle_id)


def institution_by_id(institution_id: str) -> InstitutionDef | None:
    return INSTITUTIONS.get(institution_id)


def event_by_id(event_id: str) -> DecisionEvent | None:
    return DECISION_EVENTS.get(event_id)


def apply_value_changes(state: SettlementPoliticalState, changes: dict[str, int]) -> None:
    for key, delta in changes.items():
        if key == "authority":
            state.authority += int(delta)
        elif key == "solidarity":
            state.solidarity += int(delta)
        elif key == "stewardship":
            state.stewardship += int(delta)
    state.clamp_values()


def enact_principle(
    state: SettlementPoliticalState,
    principle_id: str,
    *,
    day: int,
    summary_line: str,
) -> PendingInstitutionReveal | None:
    """Record a principle and institutionalise if the category reaches 3."""
    principle = PRINCIPLES.get(principle_id)
    if principle is None:
        return None
    if principle_id not in state.enacted_principle_ids:
        state.enacted_principle_ids.append(principle_id)
    state.principle_source_lines[principle_id] = summary_line
    state.add_diary(
        day,
        "principle",
        f"Enacted {principle.name} ({CATEGORY_LABELS[principle.category]})",
        principle.description,
    )
    return maybe_form_institution(state, principle.category, day=day)


def maybe_form_institution(
    state: SettlementPoliticalState,
    category: PrincipleCategory,
    *,
    day: int,
) -> PendingInstitutionReveal | None:
    if state.has_category_institution(category):
        return None
    if state.principle_count(category) < INSTITUTION_PRINCIPLE_THRESHOLD:
        return None
    if len(state.institution_ids) >= 4:
        return None
    institution_id = CATEGORY_INSTITUTION_ID[category]
    institution = INSTITUTIONS[institution_id]
    matching = [
        pid
        for pid in state.enacted_principle_ids
        if PRINCIPLES[pid].category == category
    ][:INSTITUTION_PRINCIPLE_THRESHOLD]
    summary_lines = tuple(
        state.principle_source_lines.get(pid, PRINCIPLES[pid].name) for pid in matching
    )
    state.institution_ids.append(institution_id)
    state.add_diary(
        day,
        "institution",
        f"Institution formed: {institution.name}",
        "; ".join(summary_lines),
    )
    reveal = PendingInstitutionReveal(
        institution_id=institution_id,
        principle_ids=tuple(matching),
        summary_lines=summary_lines,
    )
    state.pending_reveal = reveal
    return reveal


def resolve_option(
    state: SettlementPoliticalState,
    event: DecisionEvent,
    option: DecisionOption,
    *,
    day: int,
) -> PendingInstitutionReveal | None:
    apply_value_changes(state, option.value_changes)
    if option.set_recruitment_policy is not None:
        state.recruitment_policy = option.set_recruitment_policy
    reveal = enact_principle(
        state, option.principle_id, day=day, summary_line=option.summary_line
    )
    if event.id not in state.fired_event_ids:
        state.fired_event_ids.append(event.id)
    state.decisions_resolved += 1
    state.active_event_id = None
    state.add_diary(day, "decision", f"{event.title} → {option.label}", option.summary_line)
    return reveal


def next_manual_event_id(state: SettlementPoliticalState) -> str | None:
    for event_id in EVENT_ORDER:
        if event_id not in state.fired_event_ids:
            return event_id
    return None


def season_pay_rate(state: SettlementPoliticalState | None) -> int:
    if state is not None and state.has_institution("labour_exchange"):
        return EXCHANGE_SEASON_PAY_COINS
    return CONTRACT_SEASON_PAY_DEFAULT


def work_efficiency_multiplier(
    state: SettlementPoliticalState | None,
    *,
    job_matches_strongest: bool = False,
) -> float:
    mult = 1.0
    if state is None:
        return mult
    if state.has_institution("settlement_office"):
        mult *= 1.0 + OFFICE_WORK_EFFICIENCY
    if state.has_institution("labour_exchange") and job_matches_strongest:
        mult *= 1.0 + EXCHANGE_MATCH_EFFICIENCY
    if state.seasonal_work_bonus:
        mult *= 1.0 + float(state.seasonal_work_bonus)
    return mult


def extractive_work_multiplier(state: SettlementPoliticalState | None) -> float:
    """>1 means work takes longer (Covenant)."""
    if state is not None and state.has_institution("covenant_of_the_land"):
        return 1.0 + COVENANT_EXTRACTIVE_SLOWDOWN
    return 1.0


def ecology_recovery_multiplier(state: SettlementPoliticalState | None) -> float:
    if state is not None and state.has_institution("covenant_of_the_land"):
        return 1.0 + COVENANT_ECOLOGY_BONUS
    return 1.0


def missing_ration_happiness_scale(state: SettlementPoliticalState | None) -> float:
    if state is not None and state.has_institution("common_provision"):
        return 1.0 - PROVISION_RATION_HAPPINESS_REDUCTION
    return 1.0


def generate_settlement_description(state: SettlementPoliticalState) -> str:
    names = [INSTITUTIONS[i].name for i in state.institution_ids if i in INSTITUTIONS]
    if not names:
        lean = []
        if state.authority >= 60:
            lean.append("more centrally directed")
        if state.solidarity >= 60:
            lean.append("inclined toward mutual aid")
        if state.stewardship >= 60:
            lean.append("careful with the land")
        if state.authority <= 40:
            lean.append("wary of central command")
        if not lean:
            return (
                "The settlement remains politically unsettled. "
                "Choices have not yet hardened into institutions."
            )
        return "The settlement became " + ", and ".join(lean) + "."

    office = "settlement_office" in state.institution_ids
    provision = "common_provision" in state.institution_ids
    exchange = "labour_exchange" in state.institution_ids
    covenant = "covenant_of_the_land" in state.institution_ids

    bits: list[str] = []
    if office and provision:
        bits.append(
            "a centrally coordinated commons. Food and shelter were shared, "
            "but work was increasingly organised through the Settlement Office"
        )
    elif office and exchange:
        bits.append(
            "a directed marketplace. Contracts and skilled pay sat beside "
            "central work assignments"
        )
    elif provision and covenant:
        bits.append(
            "a careful commons. Shared provision was bound to ecological limits"
        )
    elif exchange and covenant:
        bits.append(
            "an enterprising stewardship. Skill was rewarded, yet land use was constrained"
        )
    elif office:
        bits.append("increasingly organised through the Settlement Office")
    elif provision:
        bits.append("a commons of shared food and shelter")
    elif exchange:
        bits.append("oriented around contracts and skilled contribution")
    elif covenant:
        bits.append("bound by a Covenant of the Land")
    else:
        bits.append("shaped by " + ", ".join(names))

    return "The settlement became " + bits[0] + "."


def format_value_tendency(authority: int, solidarity: int, stewardship: int) -> str:
    parts = []
    for name, value in (
        ("Authority", authority),
        ("Solidarity", solidarity),
        ("Stewardship", stewardship),
    ):
        if value >= 65:
            parts.append(f"high {name}")
        elif value <= 35:
            parts.append(f"low {name}")
    return ", ".join(parts) if parts else "balanced tendencies"


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
