import unittest
from datetime import datetime, timezone

from app.services.agent import SQL_INSTRUCTIONS, build_db, format_results, personalize, pseudonymize, run_sql


def sandbox():
    start = datetime(2026, 9, 1, 7, tzinfo=timezone.utc)
    runs = [
        {"runner": "R1", "start": start, "sport_type": "Run", "distance_m": 10000, "moving_time_s": 3000,
         "elapsed_time_s": 3100, "elevation_gain_m": 50, "kudos": 3, "pr_count": 1,
         "best_efforts": [{"name": "1k", "distance": 1000, "elapsed_time": 270, "pr_rank": 1}],
         "splits": [{"split": 1, "distance": 1000, "moving_time": 300, "elevation_difference": 2}]},
        {"runner": "R2", "start": start, "sport_type": "Run", "distance_m": 5000, "moving_time_s": 1400,
         "elapsed_time_s": 1400, "elevation_gain_m": 0, "kudos": 0, "pr_count": 0,
         "best_efforts": [{"name": "5K", "distance": 5000, "elapsed_time": 1400, "pr_rank": 1}], "splits": []},
    ]
    runners = [{"runner": "R1", "goal_seconds": 6000}, {"runner": "R2", "goal_seconds": None}]
    return build_db({"name": "HM", "day": "2027-04-04", "distance_km": 21.1}, runners, runs)


class SandboxTests(unittest.TestCase):
    def test_select_works(self):
        cols, rows = run_sql(sandbox(), "SELECT runner, SUM(distance_km) AS km FROM runs GROUP BY runner ORDER BY km DESC;")
        self.assertEqual(cols, ["runner", "km"])
        self.assertEqual(rows, [["R1", 10.0], ["R2", 5.0]])
        _, rows = run_sql(sandbox(), "WITH x AS (SELECT effort FROM best_efforts WHERE effort = '1k') SELECT * FROM x")
        self.assertEqual(rows, [["1k"]])

    def test_best_effort_lookup_ignores_strava_effort_name_case(self):
        _, rows = run_sql(
            sandbox(),
            "SELECT runner, MIN(elapsed_time_s) AS best_5k FROM best_efforts "
            "WHERE effort = '5k' GROUP BY runner ORDER BY best_5k",
        )
        self.assertEqual(rows, [["R2", 1400]])

    def test_query_results_format_pace_as_minute_per_kilometre(self):
        result = format_results(["runner", "average_pace_s_per_km"], [["R1", 245]])
        self.assertIn("average_pace", result)
        self.assertIn("4:05 /km", result)
        self.assertNotIn("245", result)
        self.assertIn("include the word 'pace' in its result-column alias", SQL_INSTRUCTIONS)

    def test_writes_and_escapes_are_rejected(self):
        db = sandbox()
        for sql in [
            "DELETE FROM runs",
            "SELECT 1; DELETE FROM runs",
            "WITH x AS (SELECT 1) DELETE FROM runs",
            "ATTACH DATABASE '/tmp/x.db' AS x",
            "PRAGMA writable_schema = ON",
            "SELECT * FROM sqlite_master",
            "SELECT load_extension('x')",
        ]:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                run_sql(db, sql)
        self.assertEqual(run_sql(db, "SELECT COUNT(*) FROM runs")[1], [[2]])

    def test_runaway_queries_are_stopped(self):
        sql = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT COUNT(*) FROM n"
        with self.assertRaises(ValueError):
            run_sql(sandbox(), sql)

    def test_names_stay_on_the_server(self):
        runners = {"R1": ("Simon G.", "/api/v1/avatars/1"), "R2": ("Anna X.", None)}
        self.assertEqual(pseudonymize("Is simon faster than Anna X.?", runners), "Is R1 faster than R2?")
        components = personalize(
            [
                {"type": "ranked-list", "icon": "trophy", "title": "R1 leads",
                 "items": [{"label": "R1", "value": "10 km", "image_urls": ["https://evil.example"]}]},
                {"type": "script", "text": "x"},
            ],
            runners,
        )
        self.assertEqual(components, [{
            "type": "ranked-list", "icon": "trophy", "title": "Simon G. leads",
            "items": [{"label": "Simon G.", "value": "10 km", "image_urls": ["/api/v1/avatars/1"]}],
        }])


if __name__ == "__main__":
    unittest.main()
