import { useId } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { ArrowUpRight, CalendarDays, HeartCrack, Timer, Zap } from "lucide-react"
import type { Member } from "@/lib/api"
import { formatDate, formatDuration, formatPace } from "@/lib/utils"

export default function RunnerCard({ member, index }: { member: Member; index: number }) {
  const reduceMotion = useReducedMotion()
  const heartRateHintId = useId()
  const textWidth = member.avatar_is_generated ? "max-w-[50%]" : "max-w-[65%]"

  return (
    <motion.article
      className={`runner-card runner-card--${index % 4}`}
      initial={reduceMotion ? false : { opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.45, delay: (index % 4) * 0.07 }}
    >
      <div className="relative z-10 flex h-full flex-col">
        <p className="text-xs font-bold uppercase opacity-70">Runner {String(index + 1).padStart(2, "0")}</p>
        <h3 className={`mt-1 break-words text-xl font-bold leading-tight sm:text-2xl ${textWidth}`}>{member.name}</h3>

        <div className={`mt-5 ${textWidth}`}>
          <div className="relative flex items-center gap-1.5 text-xs font-medium">
            <span className="opacity-75">Training-based finish</span>
            {!member.has_heart_rate_data && (
              <span className="group inline-flex">
                <button type="button" aria-label="No recent heart-rate data" aria-describedby={heartRateHintId}
                  className="rounded opacity-75 focus-visible:outline-2 focus-visible:outline-offset-2">
                  <HeartCrack className="size-3.5" aria-hidden="true" />
                </button>
                <span id={heartRateHintId} role="tooltip"
                  className="pointer-events-none absolute left-0 top-full z-20 mt-2 w-52 rounded-lg bg-card p-3 text-xs font-normal text-card-foreground shadow-lg opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                  No usable heart-rate data in the last 12 weeks. This estimate is less accurate without heart-rate data.
                </span>
              </span>
            )}
          </div>
          <p className="mt-1 text-3xl font-bold tabular-nums sm:text-4xl">
            {member.prediction_seconds ? formatDuration(member.prediction_seconds) : "—"}
          </p>
          <p className="mt-2 flex items-center gap-1 text-xs opacity-75">
            <ArrowUpRight className="size-3.5" />{member.km_7d.toFixed(1)} km last 7 days
          </p>
          {member.best_km_seconds && (
            <p className="mt-1 flex items-center gap-1 text-xs opacity-75">
              <Zap className="size-3.5" />Best km {formatPace(member.best_km_seconds)} (12 wks)
            </p>
          )}
        </div>

        {member.avatar_url ? (
          <img
            src={member.avatar_url}
            alt=""
            loading="lazy"
            className={`runner-avatar ${member.avatar_is_generated ? "runner-avatar--generated" : "runner-avatar--profile"}`}
          />
        ) : (
          <span className="runner-initial" aria-hidden="true">{member.name.charAt(0).toUpperCase()}</span>
        )}

        <div className="relative z-10 mt-auto border-t border-current/15 pt-3">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold"><CalendarDays className="size-3.5" /> Recent runs</p>
          {member.recent_runs.length ? (
            <ul className="space-y-1.5 text-xs">
              {member.recent_runs.map((run, runIndex) => (
                <li key={`${run.date}-${runIndex}`} className="flex flex-wrap items-center justify-between gap-x-3">
                  <span className="opacity-75">{formatDate(run.date)}</span>
                  <span className="font-semibold tabular-nums">{run.distance_km.toFixed(1)} km · {formatPace(run.pace_seconds_km)} /km</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-xs opacity-75">No runs recorded yet.</p>}
          {member.goal_seconds && (
            <p className="mt-3 flex items-center gap-1 text-xs opacity-75"><Timer className="size-3.5" /> Personal goal: {formatDuration(member.goal_seconds)}</p>
          )}
        </div>
      </div>
    </motion.article>
  )
}
