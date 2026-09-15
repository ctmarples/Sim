"""Unit tests for the sociopolitical sandbox prototype."""

from __future__ import annotations

import unittest

from entities import Villager, WorkPriority
from sociopolitical import (
    CATEGORY_INSTITUTION_ID,
    DECISION_EVENTS,
    EVENT_ORDER,
    INSTITUTIONS,
    PRINCIPLES,
    PrincipleCategory,
    RecruitmentPolicy,
    SettlementPoliticalState,
    enact_principle,
    event_by_id,
    generate_settlement_description,
    maybe_form_institution,
    missing_ration_happiness_scale,
    next_manual_event_id,
    resolve_option,
    season_pay_rate,
    work_efficiency_multiplier,
)


class SociopoliticalDataTests(unittest.TestCase):
    def test_catalogues_cover_the_first_test(self) -> None:
        self.assertEqual(len(EVENT_ORDER), 8)
        self.assertEqual(len(INSTITUTIONS), 4)
        self.assertGreaterEqual(len(PRINCIPLES), 12)
        for event_id in EVENT_ORDER:
            event = event_by_id(event_id)
            self.assertIsNotNone(event)
            self.assertGreaterEqual(len(event.options), 2)
            for option in event.options:
                self.assertIn(option.principle_id, PRINCIPLES)

    def test_values_shift_by_ten_and_clamp(self) -> None:
        state = SettlementPoliticalState()
        event = event_by_id("work_organisation")
        option = event.options[0]
        resolve_option(state, event, option, day=1)
        self.assertEqual(state.authority, 60)
        self.assertEqual(state.solidarity, 40)
        state.authority = 95
        resolve_option(state, event, option, day=2)
        self.assertEqual(state.authority, 100)

    def test_decisions_trade_off_values(self) -> None:
        for event in DECISION_EVENTS.values():
            for option in event.options:
                changes = option.value_changes
                if not changes:
                    continue
                ups = [v for v in changes.values() if v > 0]
                downs = [v for v in changes.values() if v < 0]
                self.assertTrue(
                    ups and downs,
                    f"{event.id}/{option.id} should raise one value and lower another",
                )

    def test_institution_forms_after_three_principles(self) -> None:
        state = SettlementPoliticalState()
        ids = ("assigned_labour", "directed_rations", "necessary_assignments")
        reveal = None
        for pid in ids:
            reveal = enact_principle(state, pid, day=1, summary_line=f"We chose {pid}.")
        self.assertIsNotNone(reveal)
        self.assertEqual(reveal.institution_id, "settlement_office")
        self.assertIn("settlement_office", state.institution_ids)
        self.assertEqual(state.principle_count(PrincipleCategory.COMMAND), 3)
        # No second formation.
        self.assertIsNone(
            maybe_form_institution(state, PrincipleCategory.COMMAND, day=2)
        )

    def test_institution_modifiers(self) -> None:
        state = SettlementPoliticalState()
        self.assertEqual(season_pay_rate(state), 2)
        self.assertEqual(work_efficiency_multiplier(state), 1.0)
        state.institution_ids.append("labour_exchange")
        self.assertEqual(season_pay_rate(state), 3)
        self.assertAlmostEqual(
            work_efficiency_multiplier(state, job_matches_strongest=True), 1.1
        )
        state.institution_ids.append("settlement_office")
        self.assertAlmostEqual(
            work_efficiency_multiplier(state, job_matches_strongest=True), 1.1 * 1.1
        )
        state.institution_ids.append("common_provision")
        self.assertAlmostEqual(missing_ration_happiness_scale(state), 0.75)

    def test_description_mentions_formed_institutions(self) -> None:
        state = SettlementPoliticalState()
        state.institution_ids = ["settlement_office", "common_provision"]
        text = generate_settlement_description(state)
        self.assertIn("Settlement Office", text)
        self.assertTrue(text.startswith("The settlement became"))

    def test_round_trip_serialization(self) -> None:
        state = SettlementPoliticalState(test_active=True, authority=70)
        state.enacted_principle_ids = ["common_harvest"]
        state.institution_ids = ["common_provision"]
        state.recruitment_policy = RecruitmentPolicy.OPEN_ADMISSION
        restored = SettlementPoliticalState.from_dict(state.to_dict())
        self.assertTrue(restored.test_active)
        self.assertEqual(restored.authority, 70)
        self.assertEqual(restored.enacted_principle_ids, ["common_harvest"])
        self.assertEqual(restored.institution_ids, ["common_provision"])
        self.assertEqual(restored.recruitment_policy, RecruitmentPolicy.OPEN_ADMISSION)

    def test_next_manual_event_skips_fired(self) -> None:
        state = SettlementPoliticalState()
        self.assertEqual(next_manual_event_id(state), EVENT_ORDER[0])
        state.fired_event_ids.append(EVENT_ORDER[0])
        self.assertEqual(next_manual_event_id(state), EVENT_ORDER[1])

    def test_category_institution_map(self) -> None:
        self.assertEqual(
            CATEGORY_INSTITUTION_ID[PrincipleCategory.STEWARDSHIP],
            "covenant_of_the_land",
        )

    def test_assigned_workplace_defaults_prefer_job_over_haul(self) -> None:
        """Mirrors SP test bootstrap: set building_id then default priorities."""
        villager = Villager(id=1, x=0, y=0, building_id=42)
        # Unassigned defaults alone leave only Transport after Build is filtered.
        self.assertNotIn(WorkPriority.WORKPLACE, villager.active_priorities(None))
        villager.set_default_priorities()
        prios = villager.active_priorities(None)
        self.assertEqual(prios[0], WorkPriority.WORKPLACE)
        self.assertIn(WorkPriority.TRANSPORT, prios)

    def test_mason_does_not_fall_back_to_village_haul(self) -> None:
        """Quiet mason ticks must not pull Collect Rocks workers into village haul."""
        from unittest.mock import Mock

        from entities import Building, BuildingKind, VillagerState
        from game import Game

        mason = Building(1, BuildingKind.MASON, 0, 0)
        mill = Building(2, BuildingKind.MILL, 1, 1)
        villager = Villager(id=1, x=0, y=0, building_id=mason.id)
        villager.state = VillagerState.IDLE
        game = Game.__new__(Game)
        game.buildings = {mason.id: mason, mill.id: mill}
        game._is_general_hauler = Mock(return_value=False)
        game._assigned_transport_has_work = Mock(return_value=False)
        game._transport_has_work = Mock(return_value=True)
        game._update_hauler = Mock()
        game._update_assigned_transport = Mock()

        self.assertTrue(game._workplace_blocks_village_haul(mason))
        self.assertFalse(game._workplace_blocks_village_haul(mill))

        building = game.buildings.get(villager.building_id)
        self.assertIsNotNone(building)
        assert building is not None
        if game._assigned_transport_has_work(villager, building):
            game._update_assigned_transport(villager, building)
        elif (
            not game._workplace_blocks_village_haul(building)
            and game._transport_has_work(villager)
        ):
            game._update_hauler(villager)

        game._update_hauler.assert_not_called()
        game._update_assigned_transport.assert_not_called()

if __name__ == "__main__":
    unittest.main()
