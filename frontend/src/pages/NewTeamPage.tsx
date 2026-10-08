import { useEffect, useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import LoadingState from "@/components/LoadingState"
import PageTransition from "@/components/PageTransition"
import StravaConnectButton from "@/components/StravaConnectButton"
import { api, ApiError, stravaLoginUrl, type Me } from "@/lib/api"

const DISTANCES = [
  { label: "5 km", meters: 5000 },
  { label: "10 km", meters: 10000 },
  { label: "Half marathon", meters: 21097 },
  { label: "Marathon", meters: 42195 },
]

const inputClass =
  "h-10 w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

export default function NewTeamPage() {
  const navigate = useNavigate()
  const [me, setMe] = useState<Me | null | undefined>(undefined)
  const [name, setName] = useState("")
  const [raceName, setRaceName] = useState("")
  const [raceDate, setRaceDate] = useState("")
  const [distance, setDistance] = useState(21097)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null))
  }, [])

  if (me === undefined) return <LoadingState />

  if (me === null) {
    return (
      <PageTransition className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center">
        <h1 className="text-2xl font-bold">Connect Strava to create a team</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          Available average and maximum heart rate are used privately to refine your race estimate.
          Your team only sees whether recent heart-rate data is available, not the readings.
        </p>
        <StravaConnectButton href={stravaLoginUrl("create")} />
      </PageTransition>
    )
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const { id } = await api.createTeam({
        name: name.trim(),
        race_name: raceName.trim(),
        race_date: raceDate,
        race_distance_m: distance,
      })
      navigate(`/t/${id}`)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Your session expired." : "Could not create the team.")
      setSubmitting(false)
    }
  }

  return (
    <PageTransition className="mx-auto max-w-lg px-4 py-12">
      <h1 className="mb-2 text-3xl font-bold">
        Hi {me.name.split(" ")[0]}, <span className="gradient-text">let's set the goal</span>
      </h1>
      <p className="mb-8 text-muted-foreground">You'll get a private link to share with your team.</p>

      <Card>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-5">
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">Team name</span>
              <input className={inputClass} required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="Sunday Long Run Crew" />
            </label>
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">Race</span>
              <input className={inputClass} required maxLength={120} value={raceName} onChange={(e) => setRaceName(e.target.value)} placeholder="Munich Half Marathon" />
            </label>
            <div className="grid grid-cols-2 gap-4">
              <label className="block space-y-1.5">
                <span className="text-sm font-medium">Race date</span>
                <input className={inputClass} type="date" required value={raceDate} onChange={(e) => setRaceDate(e.target.value)} />
              </label>
              <label className="block space-y-1.5">
                <span className="text-sm font-medium">Distance</span>
                <select className={inputClass} value={distance} onChange={(e) => setDistance(Number(e.target.value))}>
                  {DISTANCES.map((d) => (
                    <option key={d.meters} value={d.meters}>{d.label}</option>
                  ))}
                </select>
              </label>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" size="lg" className="w-full" disabled={submitting}>
              {submitting ? "Creating…" : "Create team"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageTransition>
  )
}
