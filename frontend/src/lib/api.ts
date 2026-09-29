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
  runs: number
  total_km: number
  last_4_weeks_km: number
  longest_km: number
  week_km: number
  week_runs: number
  prediction_seconds: number | null
  recent_runs: { date: string; distance_km: number; pace_seconds_km: number | null }[]
}

export interface Highlights {
  week_start: string
  week_km: number
  week_time_s: number
  week_runs: number
  longest_run_km: number
  longest_runner: string | null
  fastest_pace_seconds_km: number | null
  fastest_runner: string | null
  most_runs: number
  most_runs_runner: string | null
}

export interface Viewer {
  visible: boolean
  goal_seconds: number | null
  avatar_url: string | null
  has_avatar: boolean
}

export interface Team {
  name: string
  race_name: string
  race_date: string
  race_distance_m: number
  members: Member[]
  highlights: Highlights
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
  createTeam: (body: TeamCreate) =>
    request<{ id: string }>("/teams", { method: "POST", body: JSON.stringify(body) }),
  updateMembership: (id: string, body: Partial<Viewer>) =>
    request<Viewer>(`/teams/${encodeURIComponent(id)}/me`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  leaveTeam: (id: string) =>
    request<void>(`/teams/${encodeURIComponent(id)}/me`, { method: "DELETE" }),
}

export function stravaLoginUrl(intent: "create" | "join", teamId?: string): string {
  const params = new URLSearchParams({ intent })
  if (teamId) params.set("team", teamId)
  return `${BASE}/auth/strava/login?${params}`
}
