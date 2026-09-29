import { motion, useReducedMotion } from "framer-motion"
import { Activity, Clock3, Footprints, Heart, Mountain, Route, Trophy, Zap } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { Highlights } from "@/lib/api"
import { formatDuration, formatPace } from "@/lib/utils"

interface Tile {
  label: string
  value: string
  detail: string
  icon: LucideIcon
}

function tiles(h: Highlights): Tile[] {
  const fastest = h.fastest_km_seconds !== null
    ? { label: "Fastest kilometre", value: `${formatPace(h.fastest_km_seconds)}`, detail: h.fastest_km_runner ?? "" }
    : { label: "Quickest run pace", value: h.fastest_pace_seconds_km === null ? "—" : `${formatPace(h.fastest_pace_seconds_km)} /km`, detail: h.fastest_runner ?? "Waiting for a fast one" }
  return [
    { label: "Time on feet", value: h.week_time_s ? formatDuration(h.week_time_s) : "—", detail: "All runners combined", icon: Clock3 },
    { label: "Longest run", value: h.longest_run_km ? `${h.longest_run_km.toFixed(1)} km` : "—", detail: h.longest_runner ?? "The road is waiting", icon: Footprints },
    { ...fastest, icon: Zap },
    { label: "Most outings", value: h.most_runs ? `${h.most_runs} runs` : "—", detail: h.most_runs_runner ?? "First run earns the lead", icon: Trophy },
    { label: "Climbed", value: `${h.week_elevation_m} m`, detail: "Elevation gained together", icon: Mountain },
    { label: "Kudos", value: String(h.week_kudos), detail: "Collected on Strava", icon: Heart },
  ]
}

export default function WeeklyHighlights({ highlights, teamName }: { highlights: Highlights; teamName: string }) {
  const reduceMotion = useReducedMotion()
  const week = Math.floor(Date.parse(`${highlights.week_start}T00:00:00Z`) / 604_800_000)
  const small = tiles(highlights)
  // Rotate order and colours weekly so the page feels fresh without being random per visit
  const rotated = [...small.slice(week % small.length), ...small.slice(0, week % small.length)]
  const items: Tile[] = [
    { label: "Together this week", value: `${highlights.week_km.toFixed(1)} km`, detail: `${highlights.week_runs} runs logged`, icon: Route },
    ...rotated,
  ]
  const message = highlights.week_runs === 0
    ? "The next run starts the story."
    : highlights.week_runs === 1
      ? "One run down. Who's joining in?"
      : `${teamName} logged ${highlights.week_runs} runs together. That's a week worth showing up for.`

  return (
    <section aria-labelledby="weekly-heading">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="mb-1 text-xs font-bold uppercase text-primary">The weekly pulse</p>
          <h2 id="weekly-heading" className="text-2xl font-bold">This week, together</h2>
        </div>
        <span className="text-xs text-muted-foreground">Monday through today · UTC</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {items.map(({ label, value, detail, icon: Icon }, index) => (
          <motion.div
            key={label}
            className={`week-tile week-tile--${(week + index) % 4} ${index === 0 ? "col-span-2" : ""}`}
            initial={reduceMotion ? false : { opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: index * 0.05, duration: 0.4 }}
          >
            <Icon className="size-5 opacity-65" aria-hidden="true" />
            <div className="mt-auto min-w-0">
              <p className="text-xs font-medium opacity-75">{label}</p>
              <p className="mt-1 text-xl font-bold tabular-nums sm:text-2xl">{value}</p>
              <p className="mt-1 truncate text-xs opacity-75" title={detail}>{detail}</p>
            </div>
          </motion.div>
        ))}
      </div>
      <p className="mt-4 flex items-center gap-2 text-sm text-muted-foreground"><Activity className="size-4 text-primary" />{message}</p>
    </section>
  )
}
