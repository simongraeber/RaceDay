import { useCallback, useEffect, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { motion } from "framer-motion"
import { Check, Copy, Eye, EyeOff, LogOut, MapPinned, WandSparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import AvatarDialog from "@/components/AvatarDialog"
import { Card, CardContent } from "@/components/ui/card"
import LoadingState from "@/components/LoadingState"
import PageTransition from "@/components/PageTransition"
import StravaConnectButton from "@/components/StravaConnectButton"
import NotFoundPage from "@/pages/NotFoundPage"
import { api, ApiError, stravaLoginUrl, type Team } from "@/lib/api"
import { fadeUp, staggerContainer } from "@/lib/animations"
import { daysUntil, formatDate, formatDuration } from "@/lib/utils"

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

  const days = daysUntil(team.race_date)
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
      <section className="hero">
        <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">{team.race_name}</p>
        <h1 className="gradient-text mb-4 text-4xl font-extrabold tracking-tight md:text-5xl">{team.name}</h1>
        <p className="text-6xl font-black tabular-nums md:text-7xl">{Math.max(days, 0)}</p>
        <p className="mb-6 text-muted-foreground">
          {days > 0 ? "days to go" : days === 0 ? "It's race day!" : "Race day is over"} · {formatDate(team.race_date)} ·{" "}
          {(team.race_distance_m / 1000).toFixed(1)} km
        </p>
        <Button variant="outline" size="sm" onClick={copyLink}>
          {copied ? <Check /> : <Copy />}
          {copied ? "Copied" : "Copy team link"}
        </Button>
      </section>

      <div className="mx-auto max-w-4xl space-y-8 px-4 py-10">
        {params.get("joined") && (
          <Card className="border-primary/40 bg-secondary">
            <CardContent className="text-sm text-secondary-foreground">
              You're in! We're importing your runs from the last 12 months — this can take a minute.
            </CardContent>
          </Card>
        )}

        <Card className="flex h-64 items-center justify-center border-dashed">
          <div className="text-center text-muted-foreground">
            <MapPinned className="mx-auto mb-2 size-10" />
            <p>The team map is coming soon.</p>
          </div>
        </Card>

        <div>
          <h2 className="mb-4 text-2xl font-bold">Team ({team.members.length})</h2>
          {team.members.length === 0 ? (
            <p className="text-muted-foreground">No one here yet.</p>
          ) : (
            <motion.div className="grid gap-4 sm:grid-cols-2" variants={staggerContainer} initial="hidden" animate="show">
              {team.members.map((m, i) => (
                <motion.div key={i} variants={fadeUp}>
                  <Card>
                    <CardContent className="flex items-center gap-4">
                      {m.avatar_url ? (
                        <img src={m.avatar_url} alt="" className="size-12 rounded-full object-cover" />
                      ) : (
                        <div className="flex size-12 items-center justify-center rounded-full bg-secondary font-bold text-secondary-foreground">
                          {m.name[0]}
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold">{m.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {m.total_km} km · {m.runs} runs · {m.last_4_weeks_km} km last 4 weeks
                        </p>
                        {m.goal_seconds && (
                          <p className="text-xs text-muted-foreground">Goal: {formatDuration(m.goal_seconds)}</p>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </motion.div>
          )}
        </div>

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
