const BASE = "/api/v1"

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: init.body ? { "Content-Type": "application/json" } : undefined,
  })
  if (!res.ok) throw new ApiError(res.status, await res.text())
  return res.status === 204 ? (undefined as T) : res.json()
}

export interface Me {
  name: string
  avatar_url: string | null
  teams: string[]
}

export interface MyTeam {
  id: string
  name: string
  race_name: string
  race_date: string
  race_distance_m: number
}

export interface Member {
  name: string
  avatar_url: string | null
  avatar_is_generated: boolean
  goal_seconds: number | null
  km_7d: number
  runs_7d: number
  last_4_weeks_km: number
  prediction_seconds: number | null
  best_km_seconds: number | null
  recent_runs: { date: string; distance_km: number; pace_seconds_km: number | null }[]
}

export interface StatCard {
  key: string
  icon: string
  label: string
  value: string
  detail: string
  image_url: string | null
}

export interface Highlights {
  window_days: number
  total_km: number
  total_runs: number
  cards: StatCard[]
  together_image_url: string | null
}

type Images = { image_urls?: string[] }

export type AIComponent =
  | { type: "ranked-list"; icon: string; title: string; items: ({ label: string; value: string } & Images)[] }
  | ({ type: "stat-highlight"; icon: string; label: string; value: string; subtitle?: string } & Images)
  | { type: "comparison"; title: string; sides: ({ name: string; stats: { label: string; value: string }[] } & Images)[] }
  | { type: "bar-chart"; title: string; bars: ({ label: string; value: number } & Images)[] }
  | { type: "table"; title: string; columns: string[]; rows: Record<string, string | number>[] }
  | { type: "callout"; emoji: string; text: string }
  | { type: "head-to-head"; player_a: { name: string } & Images; player_b: { name: string } & Images; stats: { label: string; a: string; b: string }[] }

export interface AskResponse {
  components: AIComponent[]
  remaining: number
}

export interface Track {
  name: string
  avatar_url: string | null
  avatar_is_generated: boolean
  rig_url: string | null
  date: string
  distance_km: number
  duration_s: number
  pace_seconds_km: number | null
  group: number
  path: [number, number][]
}

export interface TeamMap {
  days: number
  generated_at: string
  heat: [number, number][][]
  tracks: Track[]
}

export interface Coach {
  source: "ai" | "coach"
  generated_at: string | null
  notes: { name: string; text: string }[]
}

export interface Viewer {
  visible: boolean
  goal_seconds: number | null
  avatar_url: string | null
  has_avatar: boolean
  needs_reconnect: boolean
}

export interface Team {
  name: string
  race_name: string
  race_date: string
  race_distance_m: number
  members: Member[]
  highlights: Highlights
  coach: Coach
  viewer: Viewer | null
}

export interface TeamCreate {
  name: string
  race_name: string
  race_date: string
  race_distance_m: number
}

export const api = {
  me: () => request<Me>("/auth/me"),
  myTeams: () => request<MyTeam[]>("/teams/mine"),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  deleteAccount: () => request<void>("/auth/me", { method: "DELETE" }),
  generateAvatar: async (photo: File, description: string) => {
    const body = new FormData()
    body.append("photo", photo)
    body.append("description", description)
    const res = await fetch(`${BASE}/avatars/me`, { method: "POST", body })
    if (!res.ok) throw new ApiError(res.status, await res.text())
    return res.json() as Promise<{ url: string }>
  },
  deleteAvatar: () => request<void>("/avatars/me", { method: "DELETE" }),
  getTeam: (id: string) => request<Team>(`/teams/${encodeURIComponent(id)}`),
  teamMap: (id: string) => request<TeamMap>(`/teams/${encodeURIComponent(id)}/map`),
  createTeam: (body: TeamCreate) =>
    request<{ id: string }>("/teams", { method: "POST", body: JSON.stringify(body) }),
  updateMembership: (id: string, body: Partial<Viewer>) =>
    request<Viewer>(`/teams/${encodeURIComponent(id)}/me`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  leaveTeam: (id: string) =>
    request<void>(`/teams/${encodeURIComponent(id)}/me`, { method: "DELETE" }),
  ask: (id: string, question: string) =>
    request<AskResponse>(`/teams/${encodeURIComponent(id)}/ask`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
}

export function stravaLoginUrl(intent: "create" | "join", teamId?: string): string {
  const params = new URLSearchParams({ intent })
  if (teamId) params.set("team", teamId)
  return `${BASE}/auth/strava/login?${params}`
}
