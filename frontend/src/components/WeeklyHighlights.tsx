import { motion, useReducedMotion } from "framer-motion"
import { Activity, Clock3, Footprints, Gauge, Route, Trophy } from "lucide-react"
import type { Highlights } from "@/lib/api"
import { formatDuration } from "@/lib/utils"

function formatPace(seconds: number | null) {
  if (seconds === null) return "—"
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
}

export default function WeeklyHighlights({ highlights, teamName }: { highlights: Highlights; teamName: string }) {
  const reduceMotion = useReducedMotion()
  const accent = Math.floor(Date.parse(`${highlights.week_start}T00:00:00Z`) / 604_800_000) % 4
  const items = [
    { label: "Together this week", value: `${highlights.week_km.toFixed(1)} km`, detail: `${highlights.week_runs} runs logged`, icon: Route },
    { label: "Time on feet", value: highlights.week_time_s ? formatDuration(highlights.week_time_s) : "—", detail: "All runners combined", icon: Clock3 },
    { label: "Longest run", value: highlights.longest_run_km ? `${highlights.longest_run_km.toFixed(1)} km` : "—", detail: highlights.longest_runner ?? "The road is waiting", icon: Footprints },
    { label: "Quickest run pace", value: highlights.fastest_pace_seconds_km === null ? "—" : `${formatPace(highlights.fastest_pace_seconds_km)} /km`, detail: highlights.fastest_runner ?? "Based on average run pace", icon: Gauge },
    { label: "Most outings", value: highlights.most_runs ? `${highlights.most_runs} runs` : "—", detail: highlights.most_runs_runner ?? "First run earns the lead", icon: Trophy },
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
      <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        {items.map(({ label, value, detail, icon: Icon }, index) => (
          <motion.div
            key={label}
            className={`week-tile week-tile--${(accent + index) % 4} ${index === 0 ? "col-span-2 md:col-span-2" : "md:col-span-1"}`}
            initial={reduceMotion ? false : { opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: index * 0.06, duration: 0.4 }}
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