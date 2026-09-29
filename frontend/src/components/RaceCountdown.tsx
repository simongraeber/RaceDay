import { useEffect, useState } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { Flag } from "lucide-react"
import { formatDate } from "@/lib/utils"

function timeLeft(date: string) {
  return Math.max(0, new Date(`${date}T00:00:00`).getTime() - Date.now())
}

export default function RaceCountdown({ date, race }: { date: string; race: string }) {
  const [remaining, setRemaining] = useState(() => timeLeft(date))
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    setRemaining(timeLeft(date))
    const interval = window.setInterval(() => setRemaining(timeLeft(date)), 1000)
    return () => window.clearInterval(interval)
  }, [date])

  const current = new Date()
  const today = `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, "0")}-${String(current.getDate()).padStart(2, "0")}` === date
  const units = [
    { label: "Days", value: Math.floor(remaining / 86_400_000), width: "3ch" },
    { label: "Hours", value: Math.floor(remaining / 3_600_000) % 24, width: "2ch" },
    { label: "Minutes", value: Math.floor(remaining / 60_000) % 60, width: "2ch" },
    { label: "Seconds", value: Math.floor(remaining / 1000) % 60, width: "2ch" },
  ]

  return (
    <section className="race-clock" aria-label={`Countdown to ${race}`}>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-5 py-9 sm:flex-row sm:items-center sm:justify-between sm:py-11">
        <div className="max-w-md">
          <span className="mb-3 inline-flex items-center gap-2 text-xs font-bold uppercase text-primary">
            <Flag className="size-4" /> Race day
          </span>
          <h2 className="text-2xl font-bold leading-tight text-foreground sm:text-3xl">{race}</h2>
          <p className="mt-2 text-sm text-muted-foreground">{formatDate(date)}</p>
        </div>
        {remaining > 0 ? (
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">Until race day begins</p>
            <div className="flex items-start gap-3 sm:gap-5" role="timer" aria-label={`${units[0].value} days, ${units[1].value} hours, ${units[2].value} minutes, ${units[3].value} seconds`}>
              {units.map(({ label, value, width }) => (
                <div key={label} className="flex flex-col items-start">
                  <div className="relative overflow-hidden text-3xl font-bold tabular-nums text-foreground sm:text-4xl" style={{ width }}>
                    <motion.span
                      key={`${label}-${value}`}
                      className="block"
                      initial={reduceMotion ? false : { opacity: 0.5, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      {label === "Days" ? value : String(value).padStart(2, "0")}
                    </motion.span>
                  </div>
                  <span className="mt-1 text-xs text-muted-foreground">{label}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-lg font-semibold text-primary">{today ? "Race day is here. Go get it!" : "That one is in the books."}</p>
        )}
      </div>
    </section>
  )
}