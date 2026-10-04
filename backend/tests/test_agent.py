import asyncio
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.agent import (
    SQL_INSTRUCTIONS, Sandbox, answer, build_db, format_results, load_sandbox, personalize, pseudonymize, run_sql,
)


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
    runners = [
        {"runner": "R1", "goal_seconds": 6000, "prediction_seconds": 7265},
        {"runner": "R2", "goal_seconds": None, "prediction_seconds": None},
    ]
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

    def test_race_times_are_formatted_without_changing_query_calculations(self):
        columns, rows = run_sql(
            sandbox(),
            "SELECT runner, prediction_seconds, goal_seconds, "
            "prediction_seconds - goal_seconds AS gap_seconds FROM runners ORDER BY prediction_seconds DESC",
        )
        self.assertEqual(rows, [["R1", 7265, 6000, 1265], ["R2", None, None, None]])
        result = format_results(columns, rows)
        self.assertIn("['R1', '2:01:05', '1:40:00', '0:21:05']", result)
        self.assertIn("['R2', None, None, None]", result)
        self.assertNotIn("7265", result)
        self.assertIn("ending in '_seconds'", SQL_INSTRUCTIONS)

    def test_duration_formatting_handles_zero_rounding_and_long_races(self):
        result = format_results(
            ["prediction_seconds", "goal_finish_s", "duration", "pace_s_per_km", "total_km"],
            [[0, 3661.6, 90061, 245, 12.5], [None, None, -120, None, 0]],
        )
        self.assertIn("['0:00:00', '1:01:02', '25:01:01', '4:05 /km', 12.5]", result)
        self.assertIn("[None, None, '-0:02:00', None, 0]", result)

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

    def test_malformed_components_are_dropped_before_rendering(self):
        runners = {"R1": ("Simon G.", None)}
        components = personalize([
            {"type": "ranked-list", "icon": "trophy", "title": "Missing items"},
            {"type": "bar-chart", "title": "Wrong value", "bars": [{"label": "R1", "value": "ten"}]},
            {"type": "callout", "emoji": "!", "text": "Valid R1 result"},
        ], runners)
        self.assertEqual(components, [{"type": "callout", "emoji": "!", "text": "Valid Simon G. result"}])

    def test_answer_uses_query_results_and_restores_runner_names(self):
        prompts = []

        async def complete(_client, _instructions, prompt, json_output):
            prompts.append((prompt, json_output))
            if not json_output:
                return "SELECT runner, SUM(distance_km) AS total_km FROM runs GROUP BY runner ORDER BY total_km DESC"
            self.assertIn("['R1', 10.0]", prompt)
            self.assertIn("['R2', 5.0]", prompt)
            return json.dumps({"action": "answer", "components": [{
                "type": "ranked-list", "icon": "trophy", "title": "Distance leaders",
                "items": [{"label": "R1", "value": "10 km"}, {"label": "R2", "value": "5 km"}],
            }]})

        runners = {"R1": ("Simon G.", None), "R2": ("Anna X.", None)}
        box = Sandbox(sandbox(), runners, "R1", "Current date/time (UTC): 2026-10-01 12:00")
        with patch("app.services.agent.complete", side_effect=complete):
            components = asyncio.run(answer(box, "Who ran the most?"))

        self.assertEqual([item["label"] for item in components[0]["items"]], ["Simon G.", "Anna X."])
        self.assertNotIn("Simon", prompts[0][0])

    def test_sandbox_query_only_loads_the_last_year(self):
        class FakeDb:
            statement = None

            async def execute(self, statement):
                self.statement = statement
                return SimpleNamespace(all=lambda: [])

        member = SimpleNamespace(name="Simon G.", avatar_url=None, goal_seconds=5400, prediction_seconds=7265)
        view = SimpleNamespace(members=[(1, member)])
        team = SimpleNamespace(race_name="Half", race_date=date(2027, 4, 4), race_distance_m=21097)
        db = FakeDb()
        with patch("app.services.agent.load_team_view", new=AsyncMock(return_value=view)):
            box = asyncio.run(load_sandbox(db, team, 1))

        cutoff = next(value for value in db.statement.compile().params.values() if isinstance(value, datetime))
        self.assertLess(abs((datetime.now(timezone.utc) - cutoff) - timedelta(days=365)), timedelta(seconds=2))
        box.db.close()


if __name__ == "__main__":
    unittest.main()
