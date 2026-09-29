import unittest
from datetime import datetime, timedelta, timezone

from app.api.v1.teams import pace_seconds_km, predict_finish
from app.models import Activity


def run(distance: float, seconds: int, days_ago: int = 0) -> Activity:
    return Activity(
        id=days_ago + 1,
        athlete_id=1,
        name="Training run",
        sport_type="Run",
        start_date=datetime.now(timezone.utc) - timedelta(days=days_ago),
        distance_m=distance,
        moving_time_s=seconds,
        elapsed_time_s=seconds,
        elevation_gain_m=0,
    )


class TeamStatsTests(unittest.TestCase):
    def test_average_pace_uses_moving_time(self):
        self.assertEqual(pace_seconds_km(run(5000, 1500)), 300)
        self.assertIsNone(pace_seconds_km(run(900, 250)))

    def test_projection_uses_recent_qualifying_effort(self):
        since = datetime.now(timezone.utc) - timedelta(days=84)
        recent = run(10000, 3000)
        self.assertEqual(predict_finish([recent], 21097, since), 6619)
        self.assertEqual(predict_finish([recent, run(10000, 2100, 100)], 21097, since), 6619)

    def test_no_projection_from_short_or_missing_runs(self):
        since = datetime.now(timezone.utc) - timedelta(days=84)
        self.assertIsNone(predict_finish([], 21097, since))
        self.assertIsNone(predict_finish([run(2000, 500)], 21097, since))


if __name__ == "__main__":
    unittest.main()