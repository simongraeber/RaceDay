import { useState } from "react"
import { motion, useReducedMotion } from "framer-motion"
import {
  Activity, CalendarCheck, Clock3, Flag, Flame, Footprints, Gauge, Ghost, Heart, Hourglass,
  Medal, Mountain, MountainSnow, Route, Ruler, Trophy, Zap,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { Highlights } from "@/lib/api"

const ICONS: Record<string, LucideIcon> = {
  clock: Clock3,
  footprints: Footprints,
  hourglass: Hourglass,
  zap: Zap,
  gauge: Gauge,
  trophy: Trophy,
  calendar: CalendarCheck,
  flame: Flame,
  mountain: Mountain,
  "mountain-snow": MountainSnow,
  heart: Heart,
  medal: Medal,
  ruler: Ruler,
  flag: Flag,
  ghost: Ghost,
}
const SHOWN = 8

function shuffled<T>(items: T[]): T[] {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

export default function WeeklyHighlights({ highlights, teamName }: { highlights: Highlights; teamName: string }) {
  const reduceMotion = useReducedMotion()
  // A fresh random pick of categories and colours on every visit, artwork cards never miss out
  const [cards] = useState(() => {
    const pool = shuffled(highlights.cards)
    return shuffled([...pool.filter((c) => c.image_url), ...pool.filter((c) => !c.image_url)].slice(0, SHOWN))
  })
  const [offset] = useState(() => Math.floor(Math.random() * 4))
  const items = [
    {
      key: "together",
      icon: Route,
      label: `Together, last ${highlights.window_days} days`,
      value: `${highlights.total_km.toFixed(1)} km`,
      detail: `${highlights.total_runs} runs logged`,
      image_url: highlights.together_image_url,
    },
    ...cards.map((c) => ({ ...c, icon: ICONS[c.icon] ?? Activity })),
  ]
  const runs = highlights.total_runs
  const message = runs === 0
    ? "Quiet week. The next run starts the story."
    : runs === 1
      ? "One run down. Who's joining in?"
      : `${teamName} logged ${runs} runs together. That's worth showing up for.`

  return (
    <section aria-labelledby="weekly-heading">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="mb-1 text-xs font-bold uppercase text-primary">The weekly pulse</p>
          <h2 id="weekly-heading" className="text-2xl font-bold">This week, together</h2>
        </div>
        <span className="text-xs text-muted-foreground">Last {highlights.window_days} days · swipe for more</span>
      </div>
      <div className="week-row">
        {items.map(({ key, label, value, detail, icon: Icon, image_url }, index) => (
          <motion.div
            key={key}
            className={`week-tile week-tile--${(offset + index) % 4}`}
            initial={reduceMotion ? false : { opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: index * 0.05, duration: 0.4 }}
          >
            {image_url && <img src={image_url} alt="" loading="lazy" className="week-tile-art" />}
            <Icon className="relative size-5 opacity-65" aria-hidden="true" />
            <div className="relative mt-auto min-w-0">
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
