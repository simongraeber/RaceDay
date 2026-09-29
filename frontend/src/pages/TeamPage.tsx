import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useParams, useSearchParams } from "react-router-dom"
import { ArrowLeft, Check, Copy, Eye, EyeOff, LogOut, MapPinned, WandSparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import AvatarDialog from "@/components/AvatarDialog"
import { Card, CardContent } from "@/components/ui/card"
import LoadingState from "@/components/LoadingState"
import PageTransition from "@/components/PageTransition"
import RaceCountdown from "@/components/RaceCountdown"
import RunnerCard from "@/components/RunnerCard"
import StravaConnectButton from "@/components/StravaConnectButton"
import WeeklyHighlights from "@/components/WeeklyHighlights"
import NotFoundPage from "@/pages/NotFoundPage"
import { api, ApiError, stravaLoginUrl, type Team } from "@/lib/api"

export default function TeamPage() {
  const { teamId = "" } = useParams()
  const [params] = useSearchParams()
  const [team, setTeam] = useState<Team | null | undefined>(undefined)
  const [copied, setCopied] = useState(false)
  const [avatarOpen, setAvatarOpen] = useState(params.get("joined") === "1")

  const load = useCallback(() => {
    api.getTeam(teamId)
      .then(setTeam)
      .catch((err) => setTeam(err instanceof ApiError && [404, 422].includes(err.status) ? null : undefined))
  }, [teamId])

  useEffect(load, [load])

  if (team === null) return <NotFoundPage />
  if (team === undefined) return <LoadingState />

  const viewer = team.viewer

  async function copyLink() {
    await navigator.clipboard.writeText(window.location.origin + window.location.pathname)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function toggleVisible() {
    if (!viewer) return
    await api.updateMembership(teamId, { visible: !viewer.visible })
    load()
  }

  async function leave() {
    if (!confirm("Leave this team?")) return
    await api.leaveTeam(teamId)
    load()
  }

  return (
    <PageTransition>
      <header className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-5 py-5">
        <div className="min-w-0">
          {viewer && <Link to="/teams" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary"><ArrowLeft className="size-3.5" /> My teams</Link>}
          <h1 className="break-words text-2xl font-bold text-foreground">{team.name}</h1>
          <p className="text-xs text-muted-foreground">{(team.race_distance_m / 1000).toFixed(1)} km · {team.members.length} runners</p>
        </div>
        <Button variant="outline" size="sm" onClick={copyLink}>
          {copied ? <Check /> : <Copy />}
          {copied ? "Copied" : "Copy team link"}
        </Button>
      </header>
      <RaceCountdown date={team.race_date} race={team.race_name} />

      <div className="mx-auto max-w-5xl space-y-12 px-5 py-10">
        {params.get("joined") && (
          <Card className="border-primary/40 bg-secondary">
            <CardContent className="text-sm text-secondary-foreground">
              You're in! We're importing your runs from the last 12 months — this can take a minute.
            </CardContent>
          </Card>
        )}

        <WeeklyHighlights highlights={team.highlights} teamName={team.name} />

        <section aria-labelledby="runners-heading">
          <div className="mb-5 flex items-end justify-between gap-4">
            <div>
              <p className="mb-1 text-xs font-bold uppercase text-primary">Meet the crew</p>
              <h2 id="runners-heading" className="text-2xl font-bold">On the start line</h2>
            </div>
            <span className="text-xs text-muted-foreground">Training estimates, not guarantees</span>
          </div>
          {team.members.length === 0 ? (
            <p className="border-y border-border py-10 text-center text-muted-foreground">No one here yet. Share the team link to get started.</p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {team.members.map((m, i) => (
                <RunnerCard key={`${m.name}-${i}`} member={m} index={i} />
              ))}
            </div>
          )}
        </section>

        <section aria-labelledby="training-map-heading" className="border-t border-border pt-6">
          <h2 id="training-map-heading" className="mb-4 text-lg font-semibold">Training map</h2>
          <div className="flex h-44 items-center justify-center gap-3 border border-dashed border-border text-sm text-muted-foreground">
            <MapPinned className="size-5" /> Routes coming soon
          </div>
        </section>

        {viewer ? (
          <>
            <Card>
              <CardContent className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  {viewer.avatar_url && <img src={viewer.avatar_url} alt="Your avatar" className="size-12 rounded-full object-cover" />}
                  <div>
                    <p className="font-semibold">Your runner</p>
                    <p className="text-sm text-muted-foreground">{viewer.visible ? "Visible on this team page" : "Hidden from this team page"}</p>
                  </div>
                </div>
                <Button variant="outline" size="sm" onClick={() => setAvatarOpen(true)}>
                  <WandSparkles /> {viewer.has_avatar ? "Edit avatar" : "Make avatar"}
                </Button>
              </CardContent>
            </Card>
            <AvatarDialog open={avatarOpen} onOpenChange={setAvatarOpen} hasAvatar={viewer.has_avatar} onChange={load} />
            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-4">
              <p className="text-sm text-muted-foreground">
                {viewer.visible ? "You're visible on this team page." : "You're hidden from this team page."}
              </p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={toggleVisible}>
                  {viewer.visible ? <EyeOff /> : <Eye />}
                  {viewer.visible ? "Hide me" : "Show me"}
                </Button>
                <Button variant="ghost" size="sm" onClick={leave}>
                  <LogOut />
                  Leave
                </Button>
              </div>
            </div>
          </>
        ) : (
          <Card className="relative overflow-hidden">
            <div className="absolute -right-10 -top-10 size-40 rounded-full bg-gradient-to-br from-[var(--glow-from)] to-[var(--glow-to)] blur-[40px]" />
            <CardContent className="relative space-y-4 text-center">
              <h2 className="text-xl font-bold">Running this race too?</h2>
              <p className="mx-auto max-w-md text-sm text-muted-foreground">
                Joining shares your first name, last initial, profile picture, and your public runs
                from the last 12 months with anyone who has this link. Start and end of every route
                are cut off. You can hide yourself or leave any time.
              </p>
              <StravaConnectButton href={stravaLoginUrl("join", teamId)} />
            </CardContent>
          </Card>
        )}

        <p className="text-center text-xs text-muted-foreground">Powered by Strava</p>
      </div>
    </PageTransition>
  )
}
