import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.dialects import postgresql
from app.models import Athlete, Membership, Team
from app.services import enrich
from app.services.enrich import detail_values, trim_streams
from app.services.sync import can_share_route
from app.services.team_stats import Run, pace_seconds_km, predict_finish, race_efforts, stat_cards, summarize

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)  # a Wednesday


def run(
    distance: float, seconds: int, days_ago: float = 0, efforts: list[dict] | None = None,
    average_hr: float | None = None, max_hr: float | None = None,
) -> Run:
    return Run(
        NOW - timedelta(days=days_ago), distance, seconds, 40, 2, efforts or [],
        average_heartrate=average_hr, max_heartrate=max_hr,
    )


def team(race_date: date = date(2027, 4, 4)) -> Team:
    return Team(id=None, name="Crew", race_name="Half", race_date=race_date, race_distance_m=21097)


def member(athlete_id: int, first: str, goal: int | None = None) -> tuple:
    return (Athlete(id=athlete_id, firstname=first, lastname="X"), Membership(visible=True, goal_seconds=goal), None)


class TeamStatsTests(unittest.TestCase):
    def test_pace_uses_moving_time(self):
        self.assertEqual(pace_seconds_km(5000, 1500), 300)
        self.assertIsNone(pace_seconds_km(900, 250))

    def test_projection_damps_long_extrapolations(self):
        # 10 km in 50:00 with a matching endurance base.
        fit = predict_finish([(10000, 3000, 0)], 21097, weekly_km=45, longest_run_m=18000)
        self.assertGreater(fit, 6000)
        self.assertLess(fit, 6900)
        untrained = predict_finish([(10000, 3000, 0)], 21097, weekly_km=15, longest_run_m=8000)
        self.assertGreater(untrained, fit)
        self.assertIsNone(predict_finish([], 21097))
        self.assertIsNone(predict_finish([(2000, 500, 0)], 21097))

    def test_five_k_efforts_can_project_to_a_half_marathon(self):
        estimate = predict_finish([(5000, 1293, 29)], 21097, weekly_km=17, longest_run_m=15000)
        self.assertIsNotNone(estimate)
        self.assertGreaterEqual(estimate, 6000)
        self.assertLessEqual(estimate, 6500)

    def test_old_efforts_count_less(self):
        fresh = predict_finish([(10000, 3000, 7)], 21097, weekly_km=45, longest_run_m=18000)
        old = predict_finish([(10000, 3000, 80)], 21097, weekly_km=45, longest_run_m=18000)
        self.assertGreater(old, fresh)

    def test_single_lucky_effort_does_not_set_the_time(self):
        efforts = [(10000, 2400, 0), (10000, 3000, 0), (10000, 3060, 0)]
        self.assertEqual(
            predict_finish(efforts, 21097, weekly_km=45, longest_run_m=18000),
            predict_finish([(10000, 3000, 0)], 21097, weekly_km=45, longest_run_m=18000),
        )

    def test_race_efforts_include_best_efforts_and_skip_old_runs(self):
        efforts = race_efforts(
            [run(12000, 3900, 1, [{"distance": 10000, "elapsed_time": 3000}]), run(10000, 2000, 120)],
            NOW,
        )
        self.assertEqual([(m, s) for m, s, _ in efforts], [(12000, 3900), (10000, 3000)])
        self.assertEqual([round(age) for *_, age in efforts], [1, 1])

    def test_easy_run_heart_rate_allowance_is_capped_at_two_percent(self):
        runs = [run(10000, 3000, day, average_hr=135, max_hr=180) for day in range(3)]
        adjusted = predict_finish(race_efforts(runs, NOW), 21097, 45, 18000)
        baseline = predict_finish([(10000, 3000, day) for day in range(3)], 21097, 45, 18000)
        self.assertAlmostEqual(adjusted / baseline, 0.98, delta=0.0002)
        view = summarize(team(), [member(1, "Simon")], {1: runs}, NOW)
        self.assertTrue(view.members[0][1].has_heart_rate_data)
        self.assertLess(view.members[0][1].prediction_seconds,
                        predict_finish([(10000, 3000, day) for day in range(3)], 21097, 7.5, 10000))
        self.assertNotIn("average_heartrate", view.members[0][1].model_dump())
        self.assertNotIn("max_heartrate", view.facts[1])

    def test_heart_rate_allowance_scales_without_changing_hard_efforts(self):
        for average, expected in [(144, 2970), (153, 3000), (170, 3000)]:
            with self.subTest(average=average):
                runs = [run(10000, 3000, day, average_hr=average, max_hr=180) for day in range(3)]
                self.assertAlmostEqual(race_efforts(runs, NOW)[0][1], expected)

    def test_missing_sparse_stale_short_and_invalid_hr_leave_estimates_unchanged(self):
        cases = [
            [run(10000, 3000, day) for day in range(3)],
            [run(10000, 3000, day, average_hr=135, max_hr=180) for day in range(2)],
            [run(10000, 3000, average_hr=135, max_hr=180),
             run(10000, 3000, 85, average_hr=135, max_hr=180),
             run(10000, 3000, 86, average_hr=135, max_hr=180)],
            [run(10000, 3000), *[run(1000, 300, day, average_hr=135, max_hr=180) for day in range(3)]],
        ]
        for average, peak in [(None, 180), (150, None), (190, 180), (0, 180),
                              (150, 250), (float("nan"), 180), (150, float("inf"))]:
            cases.append([run(10000, 3000, day, average_hr=average, max_hr=peak) for day in range(3)])
        for runs in cases:
            with self.subTest(runs=runs):
                self.assertEqual(
                    race_efforts(runs, NOW),
                    [(r.distance_m, r.moving_time_s, (NOW - r.start).total_seconds() / 86400)
                     for r in runs if r.start >= NOW - timedelta(days=84)],
                )

    def test_full_run_hr_never_adjusts_best_effort_segments(self):
        runs = [run(10000, 3000, day, [{"distance": 5000, "elapsed_time": 1400}],
                    average_hr=135, max_hr=180) for day in range(3)]
        efforts = race_efforts(runs, NOW)
        self.assertEqual([seconds for meters, seconds, _ in efforts if meters == 5000], [1400] * 3)
        self.assertEqual([seconds for meters, seconds, _ in efforts if meters == 10000], [2940] * 3)

    def test_heart_rate_hint_uses_only_valid_recent_summaries(self):
        runs = {
            1: [run(10000, 3000, average_hr=150, max_hr=180)],
            2: [run(10000, 3000, 85, average_hr=150, max_hr=180)],
            3: [run(10000, 3000)],
            4: [run(10000, 3000, average_hr=190, max_hr=180)],
        }
        view = summarize(team(), [member(i, f"Runner{i}") for i in runs], runs, NOW)
        self.assertEqual([m.has_heart_rate_data for _, m in view.members], [True, False, False, False])

    def test_rolling_seven_day_cards(self):
        runs = {
            1: [run(8000, 2400, 1, [{"distance": 1000, "elapsed_time": 260}]), run(30000, 9000, 8)],
            2: [run(5000, 1400, 6.5, [{"distance": 1000, "elapsed_time": 245}]), run(20000, 6000, 20)],
            3: [],
        }
        view = summarize(team(), [member(1, "Simon", 6000), member(2, "Anna"), member(3, "Max")], runs, NOW)
        h = view.highlights
        cards = {c.key: c for c in h.cards}
        self.assertEqual((h.window_days, h.total_runs, h.total_km), (7, 2, 13.0))
        self.assertEqual((cards["fastest_km"].value, cards["fastest_km"].detail), ("4:05", "Anna X."))
        self.assertEqual((cards["longest"].value, cards["longest"].detail), ("8.0 km", "Simon X."))
        self.assertEqual(cards["kudos"].value, "4")
        self.assertEqual(cards["missing"].detail, "Max X.")
        self.assertEqual(view.facts[1]["goal_finish_s"], 6000)
        self.assertEqual(view.facts[2]["km_last_4_weeks"], 25.0)
        self.assertEqual(view.facts[1]["last_run_km"], 8.0)
        self.assertEqual(view.facts[1]["last_run_pace"], "5:00 /km")
        self.assertEqual(view.facts[1]["average_pace_last_7_days"], "5:00 /km")
        self.assertIsNone(view.facts[3]["last_run_km"])
        self.assertIsNone(view.facts[3]["average_pace_last_7_days"])
        self.assertEqual(view.members[1][1].best_km_seconds, 245)
        self.assertEqual(view.members[0][1].runs_7d, 1)

    def test_no_cards_without_recent_runs(self):
        view = summarize(team(), [member(1, "Simon")], {1: [run(10000, 3000, 10)]}, NOW)
        self.assertEqual(view.highlights.cards, [])

    def test_card_art_is_linked_and_missing_art_reported(self):
        runs = {1: [run(8000, 2400, 1)], 2: [run(5000, 1400, 2)]}
        art = {(1, "longest"): uuid.UUID("11111111-1111-4111-8111-111111111111")}
        view = summarize(team(), [member(1, "Simon"), member(2, "Anna")], runs, NOW, art)
        cards = {c.key: c for c in view.highlights.cards}
        self.assertTrue(cards["longest"].image_url.endswith("/cards/11111111-1111-4111-8111-111111111111"))
        self.assertIsNone(cards["time"].image_url)
        self.assertNotIn((1, "longest"), view.art_wanted)
        self.assertIn((1, "fastest_km" if "fastest_km" in cards else "volume"), view.art_wanted)

    def test_no_prediction_after_race_day(self):
        view = summarize(team(date(2026, 4, 4)), [member(1, "Simon")], {1: [run(10000, 3000, 1)]}, NOW)
        self.assertIsNone(view.members[0][1].prediction_seconds)

    def test_all_equal_winners_are_candidates_once_per_person(self):
        cards = {c.key: c for c in stat_cards({
            "Simon": [run(5000, 1500, 0), run(5000, 1500, 1), run(5000, 1500, 2)],
            "Jonathan": [run(5000, 1500, 0), run(5000, 1500, 1), run(5000, 1500, 2)],
            "Theo": [run(5000, 1500, 0)],
            "Inactive": [],
        }, 21097)}
        for key in ["longest", "endurance", "pace", "quick_escape", "latest"]:
            self.assertEqual([c.name for c in cards[key].candidates], ["Simon", "Jonathan", "Theo"])
        for key in ["most_runs", "consistency", "volume", "climber", "kudos", "steady_rhythm"]:
            self.assertEqual([c.name for c in cards[key].candidates], ["Simon", "Jonathan"])
        self.assertEqual(cards["consistency"].value, "3 of 7 days")

    def test_equal_displayed_distance_is_a_tie(self):
        cards = {c.key: c for c in stat_cards({
            "Simon": [run(5040, 1500)],
            "Jonathan": [run(5010, 1490)],
            "Theo": [run(4900, 1600)],
        }, 21097)}
        self.assertEqual(cards["longest"].value, "5.0 km")
        self.assertEqual([c.name for c in cards["longest"].candidates], ["Simon", "Jonathan"])

    def test_five_new_cards_use_qualifying_runs_and_history(self):
        runs = {
            1: [run(5000, 1500, 1), run(5000, 1600, 3), run(5000, 1500, 9)],
            2: [run(6000, 2100, 0), run(6000, 2112, 4), run(6000, 2100, 3)],
        }
        view = summarize(team(), [member(1, "Simon"), member(2, "Theo")], runs, NOW)
        cards = {c.key: c for c in view.highlights.cards}
        self.assertEqual((cards["steady_rhythm"].value, cards["steady_rhythm"].detail), ("2s spread", "Theo X."))
        self.assertEqual((cards["weekend"].value, cards["weekend"].detail), ("12.0 km", "Theo X."))
        self.assertEqual(cards["quick_escape"].label, "Shortest run")
        self.assertEqual((cards["quick_escape"].value, cards["quick_escape"].detail), ("25:00", "Simon X."))
        self.assertEqual(cards["comeback"].label, "Back on the road after")
        self.assertEqual((cards["comeback"].value, cards["comeback"].detail), ("5 days off", "Simon X."))
        self.assertEqual(cards["latest"].label, "Freshest run")
        self.assertEqual((cards["latest"].value, cards["latest"].detail), ("30 September", "Theo X."))

    def test_optional_cards_require_evidence(self):
        cards = {c.key: c for c in stat_cards({"Simon": [run(900, 200, 0)]}, 21097)}
        self.assertNotIn("steady_rhythm", cards)
        self.assertNotIn("weekend", cards)
        self.assertNotIn("quick_escape", cards)
        self.assertNotIn("comeback", cards)
        self.assertIn("latest", cards)

    def test_day_based_cards_use_utc_boundaries(self):
        saturday_local = Run(datetime(2026, 9, 26, 1, tzinfo=timezone(timedelta(hours=2))),
                             5000, 1500, 0, 0)
        friday_utc = Run(datetime(2026, 9, 25, 22, tzinfo=timezone.utc), 5000, 1500, 0, 0)
        cards = {c.key: c for c in stat_cards({"Simon": [saturday_local, friday_utc]}, 21097)}
        self.assertNotIn("weekend", cards)
        self.assertEqual(cards["consistency"].value, "1 of 7 days")
        self.assertEqual(cards["latest"].value, "25 September")

    def test_freshest_run_uses_readable_date_without_leading_zero(self):
        cards = {c.key: c for c in stat_cards({
            "Simon": [Run(datetime(2026, 10, 7, 12, tzinfo=timezone.utc), 5000, 1500, 0, 0)],
        }, 21097)}
        self.assertEqual(cards["latest"].label, "Freshest run")
        self.assertEqual(cards["latest"].value, "7 October")

    def test_comeback_does_not_invent_a_break_without_previous_runs(self):
        recent = {"Simon": [run(5000, 1500, 1)]}
        cards = {c.key: c for c in stat_cards(recent, 21097, recent)}
        self.assertNotIn("comeback", cards)

    def test_each_tied_candidate_gets_only_their_own_art(self):
        ids = [uuid.uuid4(), uuid.uuid4()]
        view = summarize(team(), [member(1, "Simon"), member(2, "Theo")],
                         {1: [run(5000, 1500)], 2: [run(5000, 1500)]}, NOW,
                         {(1, "most_runs"): ids[0], (2, "most_runs"): ids[1]})
        card = next(c for c in view.highlights.cards if c.key == "most_runs")
        self.assertEqual([c.image_url.rsplit("/", 1)[-1] for c in card.candidates], [str(i) for i in ids])
        self.assertEqual(card.image_url, card.candidates[0].image_url)
        self.assertIn((1, "consistency"), view.art_wanted)
        self.assertIn((2, "consistency"), view.art_wanted)


class EnrichTests(unittest.TestCase):
    def test_only_runs_shared_with_everyone_are_public(self):
        self.assertTrue(can_share_route({"visibility": "everyone"}))
        self.assertTrue(can_share_route({}))
        self.assertTrue(can_share_route({"visibility": "followers_only"}))
        self.assertTrue(can_share_route({"visibility": "followers_only", "private": True}))
        self.assertFalse(can_share_route({"visibility": "only_me"}))
        self.assertFalse(can_share_route({"visibility": "everyone", "private": True}))

    def test_streams_are_trimmed_and_downsampled(self):
        distance = list(range(0, 2001, 10))
        raw = {
            "distance": {"data": distance},
            "latlng": {"data": [[48.0, 11.0 + d / 1e5] for d in distance]},
            "time": {"data": distance},
            "heartrate": {"data": [150] * len(distance)},
        }
        streams = trim_streams(raw, meters=200, max_points=50)
        self.assertGreaterEqual(streams["distance"][0], 200)
        self.assertLessEqual(streams["distance"][-1], 1800)
        self.assertLessEqual(len(streams["latlng"]), 50)
        self.assertNotIn("heartrate", streams)
        self.assertIsNone(trim_streams({"distance": {"data": [0, 100]}}, meters=200))

    def test_detail_values_keep_only_whitelisted_fields(self):
        values = detail_values(
            {"best_efforts": [{"name": "1k", "distance": 1000, "elapsed_time": 250, "athlete": {"id": 1}}],
             "average_heartrate": 150, "max_heartrate": 180, "kudos_count": 3},
            None,
        )
        self.assertEqual(values["best_efforts"], [{"name": "1k", "distance": 1000, "elapsed_time": 250, "moving_time": None, "pr_rank": None}])
        self.assertEqual(values["kudos_count"], 3)
        self.assertEqual((values["average_heartrate"], values["max_heartrate"]), (150, 180))
        self.assertTrue(values["heart_rate_checked"])
        self.assertEqual(detail_values(None, None)["best_efforts"], None)

    def test_invalid_or_missing_heart_rate_is_not_stored(self):
        for detail in ({}, {"average_heartrate": 150}, {"average_heartrate": 190, "max_heartrate": 180},
                       {"average_heartrate": "150", "max_heartrate": 180}):
            with self.subTest(detail=detail):
                values = detail_values(detail, None)
                self.assertIsNone(values["average_heartrate"])
                self.assertIsNone(values["max_heartrate"])
                self.assertTrue(values["heart_rate_checked"])


class EnrichBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_existing_details_are_rechecked_and_keep_other_fields(self):
        for detail in ({"average_heartrate": 150, "max_heartrate": 180, "visibility": "only_me"}, None):
            with self.subTest(detail=detail):
                db = AsyncMock()
                pending = MagicMock()
                pending.all.return_value = [(101, 1)]
                db.execute.side_effect = [pending, None]
                session = MagicMock()
                session.return_value.__aenter__ = AsyncMock(return_value=db)
                session.return_value.__aexit__ = AsyncMock(return_value=False)
                with (patch.object(enrich, "async_session", session),
                      patch.object(enrich.strava, "read_budget_ok", return_value=True),
                      patch.object(enrich.strava, "get_access_token", AsyncMock(return_value="test-token")),
                      patch.object(enrich.strava, "get_activity", AsyncMock(return_value=detail)),
                      patch.object(enrich.strava, "get_activity_streams", AsyncMock()) as streams,
                      patch.object(enrich.team_cache, "clear") as clear):
                    self.assertEqual(await enrich.enrich_batch(), 1)
                    streams.assert_not_awaited()
                    clear.assert_called_once()
                select_stmt = db.execute.call_args_list[0].args[0]
                query = str(select_stmt.compile(dialect=postgresql.dialect()))
                self.assertIn("activity_details.heart_rate_checked IS false", query)
                self.assertIn("activities.start_date >=", query)
                insert_stmt = db.execute.call_args_list[1].args[0]
                compiled = insert_stmt.compile(dialect=postgresql.dialect())
                updates = str(compiled).split("DO UPDATE SET")[1]
                self.assertIn("heart_rate_checked = excluded.heart_rate_checked", updates)
                self.assertNotIn("best_efforts", updates)
                self.assertNotIn("streams", updates)
                self.assertEqual(compiled.params["average_heartrate"], 150 if detail else None)
                self.assertTrue(compiled.params["heart_rate_checked"])
                db.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
