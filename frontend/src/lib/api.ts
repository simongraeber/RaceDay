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

export interface Member {
  name: string
  avatar_url: string | null
  goal_seconds: number | null
  runs: number
  total_km: number
  last_4_weeks_km: number
  longest_km: number
}

export interface Viewer {
  visible: boolean
  goal_seconds: number | null
}

export interface Team {
  name: string
  race_name: string
  race_date: string
  race_distance_m: number
  members: Member[]
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
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  deleteAccount: () => request<void>("/auth/me", { method: "DELETE" }),
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
