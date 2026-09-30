import { motion, useReducedMotion } from "framer-motion"
import { Megaphone } from "lucide-react"
import type { Coach } from "@/lib/api"

export default function CoachCard({ coach }: { coach: Coach }) {
  const reduceMotion = useReducedMotion()
  if (!coach.notes.length) return null

  return (
    <section aria-labelledby="coach-heading" className="coach-card">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 id="coach-heading" className="flex items-center gap-2 text-lg font-bold">
          <Megaphone className="size-5 -rotate-12 text-primary" /> The Unfiltered Coach
        </h2>
        <span className="text-xs opacity-70">
          {coach.source === "ai" ? "AI roast · refreshed a few times a day" : "Coach's notes"}
        </span>
      </div>
      <ul className="space-y-3">
        {coach.notes.map((note, index) => (
          <motion.li
            key={`${note.name}-${index}`}
            className="coach-note"
            initial={reduceMotion ? false : { opacity: 0, x: index % 2 ? 12 : -12 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ delay: index * 0.08, duration: 0.35 }}
          >
            <span className="text-xs font-bold uppercase opacity-70">{note.name}</span>
            <p className="mt-0.5 text-sm leading-snug">“{note.text}”</p>
          </motion.li>
        ))}
      </ul>
    </section>
  )
}
