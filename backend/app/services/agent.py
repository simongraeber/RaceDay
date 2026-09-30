"""Ask-the-data agent.

The model's SQL never touches PostgreSQL: every question gets a throwaway in-memory
SQLite database holding only this team's visible runners, pseudonymised as R1, R2, ...
The connection is read-only, only SELECT is authorised and runtime is capped.
"""

import asyncio
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Activity, ActivityDetail, Team
from app.services.coach import _output_text
from app.services.team_stats import load_team_view

MAX_ROWS = 50
TIMEOUT_S = 3.0
COMPONENT_TYPES = {"ranked-list", "stat-highlight", "comparison", "bar-chart", "table", "callout", "head-to-head"}
ALIAS = re.compile(r"\bR\d+\b")

SCHEMA_DESCRIPTION = """\
SQLite database with the running team's training data (only this team, last 12 months):

runners: runner (text, id like 'R1'), goal_seconds (int, target race finish time, null if unset)
runs: id (int), runner (text, FK runners.runner), start_time (text 'YYYY-MM-DD HH:MM:SS' UTC), \
day (text 'YYYY-MM-DD'), sport_type (text: Run/TrailRun/VirtualRun), distance_km (real), \
moving_time_s (int), elapsed_time_s (int), pace_s_per_km (real, lower = faster), \
elevation_gain_m (real), kudos (int), pr_count (int, Strava personal records set in that run)
best_efforts: run_id (int, FK runs.id), runner (text), effort (text, e.g. '400m', '1k', '1 mile', \
'5k', '10k', 'Half-Marathon'), distance_m (real), elapsed_time_s (int), pr_rank (int 1-3 or null)
splits: run_id (int, FK runs.id), runner (text), km (int, 1 = first kilometre), distance_m (real), \
moving_time_s (int), elevation_difference_m (real)
race: name (text), race_day (text 'YYYY-MM-DD'), distance_km (real)

Notes:
- Runners are ONLY referred to by their id (R1, R2, ...). Never invent names.
- best_efforts and splits exist only for runs whose details were already imported.
- Format paces as m:ss per km and durations as h:mm:ss where helpful.\
"""

SQL_INSTRUCTIONS = """\
Write ONE SQLite SELECT query (WITH ... SELECT is fine) that answers the question.
Rules:
- Output ONLY the SQL. No markdown fences, no explanation, no semicolons.
- Read-only: never INSERT/UPDATE/DELETE/CREATE/DROP/ATTACH/PRAGMA.
- Return at most 50 rows. Use descriptive column aliases.
- Always include the runner column for per-runner results.
- Use the current date given above for time filters, e.g. day >= date('now', '-7 days').\
"""

COMPONENT_SPEC = """\
COMPONENT TYPES — pick the best fit:
1. ranked-list: {"type":"ranked-list","icon":"<icon>","title":"...","items":[{"label":"R1","value":"42.1 km"}]}
2. stat-highlight: {"type":"stat-highlight","icon":"<icon>","label":"...","value":"...","subtitle":"..."}
   For a single runner, set "runner":"R1" to show their avatar.
3. comparison: {"type":"comparison","title":"...","sides":[{"name":"R1","stats":[{"label":"...","value":"..."}]}]}
4. bar-chart: {"type":"bar-chart","title":"...","bars":[{"label":"R1","value":12.5}]}  (value MUST be a number)
5. table: {"type":"table","title":"...","columns":["Day","Distance"],"rows":[{"Day":"...","Distance":"..."}]}
6. callout: {"type":"callout","emoji":"🔥","text":"..."}
7. head-to-head: {"type":"head-to-head","player_a":{"name":"R1"},"player_b":{"name":"R2"},\
"stats":[{"label":"...","a":"...","b":"..."}]}
ICONS: footprints, flame, crown, trophy, timer, mountain, zap, users, trending-up, clock, star, heart
Use the runner id (e.g. "R1") as label/name whenever an item is a runner; it is replaced by the real name.
Use 1-3 components. Be fun and motivating, but only state facts from the query results.\
"""

ANSWER_INSTRUCTIONS = f"""\
Given a question and query results, respond with ONLY a JSON object.
Option A (results answer it): {{"action":"answer","components":[...]}}
Option B (you need different data): {{"action":"query","sql":"SELECT ..."}} (same SQL rules)
{COMPONENT_SPEC}
Empty results: {{"action":"answer","components":[{{"type":"callout","emoji":"🤷","text":"No data found for that."}}]}}\
"""

FINAL_INSTRUCTIONS = f"""\
Given a question and query results, respond with ONLY a JSON object: {{"action":"answer","components":[...]}}
{COMPONENT_SPEC}
Empty results: {{"action":"answer","components":[{{"type":"callout","emoji":"🤷","text":"No data found for that."}}]}}\
"""

INTRO = (
    "You are the stats assistant of RaceDay, a countdown page where a running team trains for a race together. "
    "Only answer questions about this team's running data; politely decline anything else with a callout.\n\n"
)


class AgentError(Exception):
    pass


@dataclass
class Sandbox:
    db: sqlite3.Connection
    runners: dict[str, tuple[str, str | None]]  # alias -> (display name, avatar url)
    asker: str | None
    context: str


def _authorize(action, arg1, *_):
    if action == sqlite3.SQLITE_READ and (arg1 or "").lower().startswith("sqlite_"):
        return sqlite3.SQLITE_DENY
    allowed = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE)
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def build_db(team: dict, runners: list[dict], runs: list[dict]) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.executescript(
        """
        CREATE TABLE runners (runner TEXT PRIMARY KEY, goal_seconds INTEGER);
        CREATE TABLE runs (id INTEGER PRIMARY KEY, runner TEXT, start_time TEXT, day TEXT, sport_type TEXT,
            distance_km REAL, moving_time_s INTEGER, elapsed_time_s INTEGER, pace_s_per_km REAL,
            elevation_gain_m REAL, kudos INTEGER, pr_count INTEGER);
        CREATE TABLE best_efforts (run_id INTEGER, runner TEXT, effort TEXT COLLATE NOCASE, distance_m REAL,
            elapsed_time_s INTEGER, pr_rank INTEGER);
        CREATE TABLE splits (run_id INTEGER, runner TEXT, km INTEGER, distance_m REAL, moving_time_s INTEGER,
            elevation_difference_m REAL);
        CREATE TABLE race (name TEXT, race_day TEXT, distance_km REAL);
        """
    )
    db.execute("INSERT INTO race VALUES (?, ?, ?)", (team["name"], team["day"], team["distance_km"]))
    db.executemany("INSERT INTO runners VALUES (:runner, :goal_seconds)", runners)
    for i, r in enumerate(runs, start=1):
        km = r["distance_m"] / 1000
        db.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                i, r["runner"], r["start"].strftime("%Y-%m-%d %H:%M:%S"), r["start"].date().isoformat(),
                r["sport_type"], round(km, 3), r["moving_time_s"], r["elapsed_time_s"],
                round(r["moving_time_s"] / km, 1) if km > 0 else None, r["elevation_gain_m"],
                r["kudos"], r["pr_count"],
            ),
        )
        db.executemany(
            "INSERT INTO best_efforts VALUES (?,?,?,?,?,?)",
            [
                (i, r["runner"], e.get("name"), e.get("distance"), e.get("elapsed_time"), e.get("pr_rank"))
                for e in r["best_efforts"]
            ],
        )
        db.executemany(
            "INSERT INTO splits VALUES (?,?,?,?,?,?)",
            [
                (i, r["runner"], s.get("split"), s.get("distance"), s.get("moving_time"),
                 s.get("elevation_difference"))
                for s in r["splits"]
            ],
        )
    db.commit()
    db.execute("PRAGMA query_only = ON")
    db.set_authorizer(_authorize)
    return db


def run_sql(db: sqlite3.Connection, sql: str) -> tuple[list[str], list[list]]:
    sql = sql.strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", sql) or ";" in sql:
        raise ValueError("Only a single SELECT statement is allowed")
    deadline = time.monotonic() + TIMEOUT_S
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    try:
        cursor = db.execute(sql)
        return [c[0] for c in cursor.description or []], [list(r) for r in cursor.fetchmany(MAX_ROWS)]
    except sqlite3.Error as exc:
        raise ValueError(str(exc)) from exc
    finally:
        db.set_progress_handler(None, 0)


async def load_sandbox(db: AsyncSession, team: Team, asker_id: int) -> Sandbox:
    view = await load_team_view(db, team)
    aliases = {athlete_id: f"R{i}" for i, (athlete_id, _) in enumerate(view.members, start=1)}
    rows = (
        await db.execute(
            select(
                Activity.athlete_id, Activity.start_date, Activity.sport_type, Activity.distance_m,
                Activity.moving_time_s, Activity.elapsed_time_s, Activity.elevation_gain_m,
                ActivityDetail.kudos_count, ActivityDetail.pr_count, ActivityDetail.best_efforts,
                ActivityDetail.splits,
            )
            .outerjoin(ActivityDetail, ActivityDetail.activity_id == Activity.id)
            .where(Activity.athlete_id.in_(aliases))
            .order_by(Activity.start_date)
        )
    ).all()
    runs = [
        {
            "runner": aliases[r[0]], "start": r[1], "sport_type": r[2], "distance_m": r[3],
            "moving_time_s": r[4], "elapsed_time_s": r[5], "elevation_gain_m": r[6], "kudos": r[7] or 0,
            "pr_count": r[8] or 0, "best_efforts": r[9] or [], "splits": r[10] or [],
        }
        for r in rows
    ]
    runners = [{"runner": aliases[a], "goal_seconds": m.goal_seconds} for a, m in view.members]
    race = {"name": team.race_name, "day": team.race_date.isoformat(), "distance_km": team.race_distance_m / 1000}
    sqlite_db = await asyncio.to_thread(build_db, race, runners, runs)
    asker = aliases.get(asker_id)
    context = (
        f"Runners: {', '.join(aliases.values()) or '(none)'}\n"
        f"The person asking is: {asker or 'a team member who is hidden from the stats'}\n"
        f"Race: {team.race_name} on {team.race_date.isoformat()} ({team.race_distance_m / 1000:g} km)\n"
        f"Current date/time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
    )
    return Sandbox(sqlite_db, {aliases[a]: (m.name, m.avatar_url) for a, m in view.members}, asker, context)


def pseudonymize(question: str, runners: dict[str, tuple[str, str | None]]) -> str:
    """Swap runner names in the question for their ids before it leaves the server."""
    names = []
    for alias, (name, _) in runners.items():
        names.append((name, alias))
        names.append((name.split(" ")[0], alias))
    for name, alias in sorted(names, key=lambda n: -len(n[0])):
        if len(name) >= 2:
            question = re.sub(rf"(?i)(?<!\w){re.escape(name)}(?!\w)", alias, question)
    return question


def personalize(components: list, runners: dict[str, tuple[str, str | None]]) -> list:
    """Drop model-supplied URLs, attach our avatar URLs and swap ids back to names."""

    def visit(node):
        if isinstance(node, dict):
            alias = next((node[k] for k in ("runner", "label", "name") if node.get(k) in runners), None)
            node = {k: visit(v) for k, v in node.items() if k != "image_urls"}
            if alias and runners[alias][1]:
                node["image_urls"] = [runners[alias][1]]
            node.pop("runner", None)
            return node
        if isinstance(node, list):
            return [visit(v) for v in node]
        if isinstance(node, str):
            return ALIAS.sub(lambda m: runners[m[0]][0] if m[0] in runners else "someone", node)
        return node

    return [visit(c) for c in components if isinstance(c, dict) and c.get("type") in COMPONENT_TYPES][:3]


def format_results(columns: list[str], rows: list[list]) -> str:
    out = f"Columns: {columns}\n" + "".join(f"{row}\n" for row in rows[:30])
    if len(rows) > 30:
        out += f"... and {len(rows) - 30} more rows\n"
    return out if rows else out + "(no rows returned)\n"


def strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return text.strip()


async def complete(client: httpx.AsyncClient, instructions: str, prompt: str, json_output: bool) -> str:
    body = {
        "model": settings.openai_text_model,
        "instructions": instructions,
        "input": prompt,
        "max_output_tokens": 4000,
        "reasoning": {"effort": "low"},
    }
    if json_output:
        body["input"] = f"{prompt}\n\nRespond with a JSON object."
        body["text"] = {"format": {"type": "json_object"}}
    resp = await client.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json=body,
    )
    resp.raise_for_status()
    return strip_fences(_output_text(resp.json()))


async def answer(sandbox: Sandbox, question: str) -> list[dict]:
    q = pseudonymize(question, sandbox.runners)
    sql_prompt = f"{SCHEMA_DESCRIPTION}\n\n{sandbox.context}\n\n{SQL_INSTRUCTIONS}"
    answer_prompt = f"{INTRO}{SCHEMA_DESCRIPTION}\n\n{sandbox.context}\n\n"

    async def query(sql: str) -> str:
        return format_results(*await asyncio.to_thread(run_sql, sandbox.db, sql))

    async with httpx.AsyncClient(timeout=90) as client:
        sql = await complete(client, sql_prompt, q, json_output=False)
        try:
            results = await query(sql)
        except ValueError as exc:
            retry = f"Question: {q}\n\nYour previous query failed:\n{sql}\n\nError: {exc}\n\nWrite a corrected query."
            sql = await complete(client, sql_prompt, retry, json_output=False)
            try:
                results = await query(sql)
            except ValueError as exc:
                raise AgentError("Sorry, I couldn't find an answer to that. Try rephrasing it.") from exc

        data = json.loads(await complete(
            client, answer_prompt + ANSWER_INSTRUCTIONS, f"Question: {q}\n\nQuery results:\n{results}", True
        ))
        if data.get("action") == "query" and data.get("sql"):
            try:
                results = f"First query results:\n{results}\nSecond query results:\n{await query(data['sql'])}"
            except ValueError:
                pass
            data = json.loads(await complete(
                client, answer_prompt + FINAL_INSTRUCTIONS, f"Question: {q}\n\nQuery results:\n{results}", True
            ))

    components = personalize(data.get("components") or [], sandbox.runners)
    if not components:
        raise AgentError("I found some data but couldn't make sense of it. Try rephrasing your question.")
    return components
