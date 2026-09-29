import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { ArrowRight, LogOut, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import LoadingState from "@/components/LoadingState"
import PageTransition from "@/components/PageTransition"
import StravaConnectButton from "@/components/StravaConnectButton"
import { api, stravaLoginUrl, type Me, type MyTeam } from "@/lib/api"
import { daysUntil, formatDate } from "@/lib/utils"

export default function TeamsPage() {
  const navigate = useNavigate()
  const [me, setMe] = useState<Me | null | undefined>(undefined)
  const [teams, setTeams] = useState<MyTeam[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState(false)
  const [logoutError, setLogoutError] = useState(false)

  useEffect(() => {
    api.me().then(async (member) => {
      setMe(member)
      try {
        setTeams(await api.myTeams())
      } catch {
        setListError(true)
      }
    }).catch(() => setMe(null)).finally(() => setLoading(false))
  }, [])

  if (loading || me === undefined) return <LoadingState />
  if (me === null) {
    return (
      <PageTransition className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center gap-4 px-4 text-center">
        <h1 className="text-2xl font-bold">Connect to see your teams</h1>
        <StravaConnectButton href={stravaLoginUrl("create")} />
      </PageTransition>
    )
  }

  async function logout() {
    try {
      await api.logout()
      navigate("/")
    } catch {
      setLogoutError(true)
    }
  }

  return (
    <PageTransition className="mx-auto max-w-2xl px-4 py-12">
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          {me.avatar_url && <img src={me.avatar_url} alt="" className="size-11 rounded-full object-cover" />}
          <div>
            <p className="mb-1 text-sm text-muted-foreground">Hi {me.name}</p>
            <h1 className="text-3xl font-bold">Your teams</h1>
          </div>
        </div>
        <Button asChild><Link to="/new"><Plus /> New team</Link></Button>
      </div>

      {listError ? (
        <p role="alert" className="border-y border-border py-10 text-center text-destructive">
          Could not load your teams. Please refresh the page.
        </p>
      ) : teams.length ? (
        <div className="divide-y divide-border border-y border-border">
          {teams.map((team) => (
            <Link key={team.id} to={`/t/${team.id}`} className="flex items-center justify-between gap-4 px-2 py-5 text-foreground transition-colors hover:bg-muted">
              <div className="min-w-0">
                <h2 className="truncate font-semibold">{team.name}</h2>
                <p className="text-sm text-muted-foreground">{team.race_name} · {formatDate(team.race_date)}</p>
              </div>
              <div className="flex shrink-0 items-center gap-3 text-sm text-muted-foreground">
                <span>{daysUntil(team.race_date) > 0 ? `${daysUntil(team.race_date)} days` : "Race finished"}</span>
                <ArrowRight className="size-4" />
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="border-y border-border py-10 text-center text-muted-foreground">
          No teams yet. Start one and share its link with your running crew.
        </div>
      )}
      {logoutError && <p className="mt-4 text-sm text-destructive">Could not sign out. Try again.</p>}
      <Button variant="ghost" size="sm" className="mt-6" onClick={logout}><LogOut /> Sign out</Button>
    </PageTransition>
  )
}