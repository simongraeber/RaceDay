import unittest
from datetime import date, datetime, timedelta, timezone

from app.models import Athlete, Membership, Team
from app.services.enrich import detail_values, trim_streams
from app.services.sync import is_public
from app.services.team_stats import Run, pace_seconds_km, predict_finish, race_efforts, summarize

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)  # a Wednesday


def run(distance: float, seconds: int, days_ago: float = 0, efforts: list[dict] | None = None) -> Run:
    return Run(NOW - timedelta(days=days_ago), distance, seconds, 40, 2, efforts or [])


def team(race_date: date = date(2027, 4, 4)) -> Team:
    return Team(id=None, name="Crew", race_name="Half", race_date=race_date, race_distance_m=21097)


def member(athlete_id: int, first: str, goal: int | None = None) -> tuple:
    return (Athlete(id=athlete_id, firstname=first, lastname="X"), Membership(visible=True, goal_seconds=goal), None)


class TeamStatsTests(unittest.TestCase):
    def test_pace_uses_moving_time(self):
        self.assertEqual(pace_seconds_km(5000, 1500), 300)
        self.assertIsNone(pace_seconds_km(900, 250))

    def test_projection_damps_long_extrapolations(self):
        # 10 km in 50:00 with a matching endurance base: slower than plain Riegel's 1:50:19
        fit = predict_finish([(10000, 3000, 0)], 21097, weekly_km=45, longest_run_m=18000)
        self.assertEqual(fit, 6781)
        # Same speed, but the longest run is 8 km and volume is low
        untrained = predict_finish([(10000, 3000, 0)], 21097, weekly_km=15, longest_run_m=8000)
        self.assertGreater(untrained, fit * 1.05)
        self.assertIsNone(predict_finish([], 21097))
        self.assertIsNone(predict_finish([(2000, 500, 0)], 21097))

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
        self.assertEqual(view.members[1][1].best_km_seconds, 245)
        self.assertEqual(view.members[0][1].runs_7d, 1)

    def test_no_cards_without_recent_runs(self):
        view = summarize(team(), [member(1, "Simon")], {1: [run(10000, 3000, 10)]}, NOW)
        self.assertEqual(view.highlights.cards, [])

    def test_no_prediction_after_race_day(self):
        view = summarize(team(date(2026, 4, 4)), [member(1, "Simon")], {1: [run(10000, 3000, 1)]}, NOW)
        self.assertIsNone(view.members[0][1].prediction_seconds)


class EnrichTests(unittest.TestCase):
    def test_only_runs_shared_with_everyone_are_public(self):
        self.assertTrue(is_public({"visibility": "everyone"}))
        self.assertTrue(is_public({}))
        self.assertFalse(is_public({"visibility": "followers_only"}))
        self.assertFalse(is_public({"visibility": "only_me"}))
        self.assertFalse(is_public({"visibility": "everyone", "private": True}))

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
             "average_heartrate": 150, "kudos_count": 3},
            None,
        )
        self.assertEqual(values["best_efforts"], [{"name": "1k", "distance": 1000, "elapsed_time": 250, "moving_time": None, "pr_rank": None}])
        self.assertEqual(values["kudos_count"], 3)
        self.assertNotIn("average_heartrate", values)
        self.assertEqual(detail_values(None, None)["best_efforts"], None)


if __name__ == "__main__":
    unittest.main()
