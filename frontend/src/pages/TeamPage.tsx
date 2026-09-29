import { useCallback, useEffect, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { ArrowLeft, Check, Copy, MapPinned } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import LoadingState from "@/components/LoadingState"
import PageTransition from "@/components/PageTransition"
import AskAI from "@/components/team/AskAI"
import CoachCard from "@/components/team/CoachCard"
import JoinTeamCard from "@/components/team/JoinTeamCard"
import MemberPanel from "@/components/team/MemberPanel"
import RaceCountdown from "@/components/team/RaceCountdown"
import RunnerCard from "@/components/team/RunnerCard"
import WeeklyHighlights from "@/components/team/WeeklyHighlights"
import NotFoundPage from "@/pages/NotFoundPage"
import { api, ApiError, type Team } from "@/lib/api"

export default function TeamPage() {
  const { teamId = "" } = useParams()
  const [params] = useSearchParams()
  const joined = params.get("joined") === "1"
  const [team, setTeam] = useState<Team | null | undefined>(undefined)
  const [copied, setCopied] = useState(false)

  const load = useCallback(() => {
    api.getTeam(teamId)
      .then(setTeam)
      .catch((err) => setTeam(err instanceof ApiError && [404, 422].includes(err.status) ? null : undefined))
  }, [teamId])

  useEffect(load, [load])

  if (team === null) return <NotFoundPage />
  if (team === undefined) return <LoadingState />

  async function copyLink() {
    await navigator.clipboard.writeText(window.location.origin + window.location.pathname)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <PageTransition>
      <header className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-5 py-5">
        <div className="min-w-0">
          {team.viewer && (
            <Link to="/teams" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary">
              <ArrowLeft className="size-3.5" /> My teams
            </Link>
          )}
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
        {joined && (
          <Card className="border-primary/40 bg-secondary">
            <CardContent className="text-sm text-secondary-foreground">
              You're in! We're importing your runs from the last 12 months — this can take a minute.
            </CardContent>
          </Card>
        )}

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
              {team.members.map((member, index) => (
                <RunnerCard key={`${member.name}-${index}`} member={member} index={index} />
              ))}
            </div>
          )}
        </section>

        <CoachCard coach={team.coach} />

        <section aria-labelledby="training-map-heading" className="border-t border-border pt-6">
          <h2 id="training-map-heading" className="mb-4 text-lg font-semibold">Training map</h2>
          <div className="flex h-44 items-center justify-center gap-3 border border-dashed border-border text-sm text-muted-foreground">
            <MapPinned className="size-5" /> Routes coming soon
          </div>
        </section>

        <WeeklyHighlights highlights={team.highlights} teamName={team.name} />

        {team.viewer && <AskAI teamId={teamId} />}

        {team.viewer ? (
          <MemberPanel teamId={teamId} viewer={team.viewer} openAvatar={joined} onChange={load} />
        ) : (
          <JoinTeamCard teamId={teamId} />
        )}

        <p className="text-center text-xs text-muted-foreground">Powered by Strava</p>
      </div>
    </PageTransition>
  )
}
