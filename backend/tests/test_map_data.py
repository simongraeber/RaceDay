import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.models import Athlete
from app.services.map_data import _Run, build, group_runs, thin

NOW = datetime(2026, 9, 29, 9, tzinfo=timezone.utc)
TEAM = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def path(lat: float, lng: float, points: int = 10) -> list[tuple[float, float]]:
    return [(lat + i * 0.001, lng + i * 0.001) for i in range(points)]


class MapDataTests(unittest.TestCase):
    def test_thin_keeps_ends(self):
        points = list(range(100))
        thinned = thin(points, 10)
        self.assertEqual((len(thinned), thinned[0], thinned[-1]), (10, 0, 99))
        self.assertEqual(thin([1, 2], 10), [1, 2])

    def test_runs_started_together_share_a_group(self):
        runs = [
            _Run(1, NOW, 10000, 3000, path(48.1, 11.5)),
            _Run(2, NOW - timedelta(minutes=5), 10000, 3100, path(48.1001, 11.5001)),
            _Run(3, NOW - timedelta(minutes=5), 10000, 3100, path(49.0, 11.5)),
            _Run(4, NOW - timedelta(hours=5), 10000, 3100, path(48.1, 11.5)),
        ]
        groups = group_runs(runs)
        self.assertEqual(groups[1], groups[0])
        self.assertNotEqual(groups[2], groups[0])
        self.assertNotEqual(groups[3], groups[0])

    def test_build_uses_newest_run_per_runner(self):
        rows = [(Athlete(id=1, firstname="Simon", lastname="G"), None)]
        runs = [
            _Run(1, NOW, 8000, 2400, path(48.1, 11.5)),
            _Run(1, NOW - timedelta(days=2), 12000, 3600, path(48.2, 11.6)),
        ]
        view = build(TEAM, rows, runs, NOW)
        self.assertEqual(len(view.heat), 2)
        self.assertEqual(len(view.tracks), 1)
        track = view.tracks[0]
        self.assertEqual((track.name, track.distance_km, track.pace_seconds_km), ("Simon G.", 8.0, 300))
        self.assertFalse(track.avatar_is_generated)

    def test_generated_avatar_is_team_scoped(self):
        avatar_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
        rows = [(Athlete(id=1, firstname="Simon", lastname="G"), avatar_id)]
        view = build(TEAM, rows, [_Run(1, NOW, 8000, 2400, path(48.1, 11.5))], NOW)
        self.assertEqual(view.tracks[0].avatar_url, f"/api/v1/teams/{TEAM}/avatars/{avatar_id}")


if __name__ == "__main__":
    unittest.main()
