# RaceDay

A shared, map-based countdown for a running team. Connect Strava, see where everyone ran, who put in the work, and what the AI thinks each member will run on race day.

Check it out at [RaceDay](https://raceday.simongraeber.com)

---

## Concept

- **Public landing page** — explains the tool, plus imprint / privacy / terms.
- **Team page** — reachable only via `/t/{team-uuid}`. No team list, no search, no login for viewers. Unguessable link = the access control.
- **Heatmap** of all team runs.
- **Leaderboards** — weekly volume, streaks, elevation, "most consistent".
- **Race prediction** — predicted finish time per athlete, updated with every new run.
- **AI hype feed** — short, funny, motivating summaries you actually want to forward to friends and family.

---

## Strava API: what is and isn't possible

Evaluated against the current Strava API v3 docs.

| Want | Possible? |
| --- | --- |
| Read all activities of a club/group | **No.** Strava removed `/clubs/{id}/activities` and `/clubs/{id}/members` for third-party apps. Only `GET /clubs/{id}` (metadata) and `GET /athlete/clubs` remain. |
| Read an athlete's own activities | **Yes** — `GET /athlete/activities`, scope `activity:read`. |
| Route geometry for the map | **Yes** — `map.summary_polyline` on each activity, or `GET /activities/{id}/streams` for `latlng`. |
| Splits, pace, HR, elevation | **Yes** — `DetailedActivity`, `splits_metric`, streams. |
| Stay fresh automatically | **Yes** — webhooks on activity create/update. |

**Consequence for the architecture:** there is no group endpoint. Every team member authorizes RaceDay individually via OAuth; the backend stores their refresh token and aggregates the team view itself. A team is our own entity, not a Strava club.

**Strava terms to respect** (must be verified before going public):
- No use of Strava data to train AI/ML models. We only *send* data to an LLM at inference time for text generation — we never fine-tune on it.
- Restrictions apply to showing one athlete's data to another. Every member must explicitly opt in to being visible on their team page.
- Show "Powered by Strava" attribution and link back to the source activity.
- Deauthorization must be handled via webhook.

**Limits:**

| Tier | Athletes | Requests |
| --- | --- | --- |
| Single Player (default) | 1 | 200 / 15 min, 2,000 / day |
| Self-upgrade in API dashboard | 10 | 400 / 15 min, 4,000 / day |
| After Strava review | more | not guaranteed |

v1 targets a single team of ≤10 — no review needed. Creating a Strava app requires a Strava subscription.

There is no official Strava MCP server. A small internal MCP server wrapping our own aggregated data is optional later; not needed for v1.

---

## Features

**Home**
- Hero, short explanation, how it works in 3 steps, legal pages.

**Team page `/t/{uuid}`**
- Animated map of all team runs (heatmap + individual routes, hover to highlight).
- Countdown to race day.
- Race prediction table: predicted time, confidence band, trend arrow.
- Leaderboards: distance, elevation, consistency, longest run.
- AI recap of the week, per team and per athlete.
- Share card (image) for WhatsApp / Instagram.

---

## Login & onboarding

**Strava OAuth is the login.** "Connect with Strava" returns both the athlete's identity and data access in one step — no separate accounts, passwords, or emails.

- **Viewers** (friends, family) never log in. They just open the team link.
- **Members** log in once via Strava; we then set our own `httpOnly` session cookie so they can manage visibility or leave.
- Returning members use `approval_prompt=auto` and skip the Strava consent screen.

**Scope: `read,activity:read`** — not `read_all`. `activity:read` excludes private activities *and* privacy-zone data, which is what we want for a public map. We additionally trim the first/last ~200 m of every route.

### Create a team

1. Home → "Start a team" → Connect with Strava.
2. Enter race name, date, distance.
3. Get the team link `/t/{uuid}` → share it in the group chat.

### Join a team

```
Open team link
  → "Join the team" → our consent screen (what will be public)
  → Strava authorize (state = team uuid + CSRF nonce)
  → callback: exchange code, store encrypted refresh token
  → backfill last 12 months in background (animated progress)
  → optional: display name, goal time
  → land on the map, own routes draw in
```

### Keeping data fresh

- Backfill once on join, then **webhooks only** — no polling.
- Refresh tokens rotate on every refresh; always persist the newest one.
- Deauth webhook → remove the athlete's data.
- Members who won't connect: manual GPX upload or a "ghost" entry with only a goal time.

---

## Prediction approach

Two layers, kept deliberately simple:

1. **Deterministic baseline** — Riegel formula on the athlete's best recent efforts, adjusted by weekly volume trend and long-run distance. This is the number shown.
2. **LLM layer** — gets the computed stats as structured input and produces the *explanation*, the tone, and the motivation ("you need three more long runs to hold sub-1:50"). It never invents the time.

This keeps predictions defensible and cheap, and keeps the LLM doing what it's good at.

---

## Making it pop

- **Map first.** The map is the page, not a widget. Routes draw themselves in on load.
- **Generative UI.** The LLM returns a small typed JSON block (headline, tone, highlighted athlete, callout cards), and the frontend renders real components from it. The layout of the recap changes with the story — no chat window, no markdown blob.
- **Generated images.** Weekly team poster themed on the week's story, one-off artwork per badge type, a race-day hero that escalates toward the date.
  - Generated in a background job, cached, served static — never on page load.
  - No real faces or avatars in prompts.
  - No text in the image; names and times are overlaid in the frontend.
  - The poster doubles as the OG image, so the team link unfurls with fresh art in WhatsApp.
- **Motion.** Staggered reveals, animated counters, a countdown that gets visibly more urgent as 04.04. approaches.
- **Personality.** Auto-awarded badges with names people will screenshot ("Sunday Sandbagger", "Elevation Gremlin").

---

## Tech Stack

| Layer | Choice |
| --- | --- |
| Frontend | React 19, TypeScript, Vite |
| Styling | Tailwind CSS 4, Radix UI / shadcn-style components |
| Motion | Framer Motion |
| Map | MapLibre GL + deck.gl heatmap layer |
| Charts | Recharts |
| Backend | Python 3.12, FastAPI, async SQLAlchemy |
| Database | PostgreSQL |
| Integrations | Strava OAuth2 + webhooks, OpenAI image edits (avatars); Gemini planned for recaps |
| Deployment | Docker Compose, nginx, GitHub Actions |

Mirrors the stack and conventions of the SIU project.

---

## Data model (sketch)

```
Team (uuid, name, race_name, race_date, race_distance_m, created_by)
  └── Membership (team_id, athlete_id, visible, goal_seconds)
Athlete (strava_id, name, avatar, scope, refresh_token_enc, access_token_enc, expires_at)
  └── Avatar (athlete_id, uuid, generated_image)  -- optional, original photo discarded
  └── Activity (athlete_id, strava_id, start_date, distance, moving_time,
                elevation, summary_polyline)  -- start/end trimmed
Prediction (athlete_id, team_id, predicted_seconds, confidence, computed_at)
Recap (team_id, week, payload_json, image_url)
```

Teams are not publicly listed. The authenticated `/teams/mine` endpoint only lists the caller's teams.

---

## Environment

| Key | Purpose |
| --- | --- |
| `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` | OAuth app credentials |
| `STRAVA_WEBHOOK_VERIFY_TOKEN` | Webhook subscription handshake |
| `OPENAI_API_KEY` | Optional photo-to-cartoon avatar generation |
| `TOKEN_ENCRYPTION_KEY` | Encrypts Strava tokens at rest |
| `SESSION_SECRET` | Signs member session cookies |
| `DATABASE_URL` | Postgres connection |
| `APP_BASE_URL` | Used for OAuth redirect and share links |

---

## Quick start

```bash
cp .env.example .env   # fill in Strava credentials + generate the two secrets
docker compose up -d --build
```

App: http://localhost · API: http://localhost:8000/docs

Frontend dev with hot reload: `cd frontend && npm install && npm run dev` (set `APP_BASE_URL=http://localhost:5173`).

Webhook subscription (once, needs a public URL):

```bash
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -F client_id=$STRAVA_CLIENT_ID -F client_secret=$STRAVA_CLIENT_SECRET \
  -F callback_url=$APP_BASE_URL/api/v1/strava/webhook \
  -F verify_token=$STRAVA_WEBHOOK_VERIFY_TOKEN
```

Put the returned `id` into `STRAVA_WEBHOOK_SUBSCRIPTION_ID`.

## API

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/api/v1/auth/strava/login?intent=create\|join&team=` | — |
| GET | `/api/v1/auth/strava/callback` | OAuth state + nonce cookie |
| GET / DELETE | `/api/v1/auth/me` | session |
| POST | `/api/v1/auth/logout` | session |
| POST | `/api/v1/teams` | session |
| GET | `/api/v1/teams/mine` | session |
| GET | `/api/v1/teams/{uuid}` | public |
| PATCH / DELETE | `/api/v1/teams/{uuid}/me` | session + member |
| GET / POST / DELETE | `/api/v1/avatars/me` | session |
| GET | `/api/v1/teams/{uuid}/avatars/{avatar_uuid}` | visible member only |
| GET / POST | `/api/v1/strava/webhook` | verify token / subscription id |

## Status

- Done: landing, imprint, privacy, Strava login, team create/join/overview, avatars, backfill, webhooks, live race-day countdown, weekly team highlights, recent runs and training-based finish estimates.
- Next: route map, split-level fastest kilometre, AI recaps, team posters, terms page. Weekly comments currently use real stats and templates, not an LLM.
