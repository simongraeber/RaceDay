import { motion } from "framer-motion"
import { useSearchParams } from "react-router-dom"
import { Flag, Link2, Lock, Map as MapIcon, Share2, Timer, Trophy, Users } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import StravaConnectButton from "@/components/StravaConnectButton"
import { stravaLoginUrl } from "@/lib/api"
import { fadeUp, staggerContainer } from "@/lib/animations"

const STEPS: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: Flag, title: "Create a team", text: "Connect Strava, pick your race and the date." },
  { icon: Link2, title: "Share the link", text: "Drop the private team link in your group chat." },
  { icon: Users, title: "Everyone connects", text: "One tap with Strava. No accounts, no passwords." },
]

const FEATURES: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: MapIcon, title: "Every run on one map", text: "Watch your team's training light up the city." },
  { icon: Timer, title: "Race-day prediction", text: "What time is everyone on track for? Updated after every run." },
  { icon: Trophy, title: "Leaderboards & badges", text: "Most kilometres, longest run, most consistent — and a few less serious ones." },
  { icon: Share2, title: "For friends & family", text: "Send the link. They can follow along without signing up." },
]

const ERRORS: Record<string, string> = {
  access_denied: "Strava access was cancelled.",
  missing_scope: "RaceDay needs permission to read your activities.",
  login_failed: "Login failed. Please try again.",
}

export default function HomePage() {
  const [params] = useSearchParams()
  const error = ERRORS[params.get("error") ?? ""]

  return (
    <div>
      <motion.section className="hero" variants={staggerContainer} initial="hidden" animate="show">
        <motion.img src="/logo.svg" alt="RaceDay" className="mb-6 h-24 drop-shadow-lg" variants={fadeUp} />
        <motion.h1 className="gradient-text mb-3 text-4xl font-extrabold tracking-tight md:text-6xl" variants={fadeUp}>
          RaceDay
        </motion.h1>
        <motion.p className="mx-auto mb-8 max-w-xl text-lg text-[var(--text-secondary)]" variants={fadeUp}>
          Your team's road to race day — on one map. See where everyone ran, who put in the work,
          and who's really ready for the start line.
        </motion.p>
        <motion.div variants={fadeUp} className="flex flex-col items-center gap-3">
          <StravaConnectButton href={stravaLoginUrl("create")} />
          <span className="text-sm text-muted-foreground">to start a new team</span>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </motion.div>
      </motion.section>

      <section className="mx-auto max-w-5xl px-6 py-16">
        <h2 className="mb-10 text-center text-3xl font-bold">How it works</h2>
        <motion.div
          className="grid gap-6 md:grid-cols-3"
          variants={staggerContainer}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-60px" }}
        >
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <motion.div key={title} variants={fadeUp}>
              <Card className="h-full">
                <CardContent className="space-y-3 text-center">
                  <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
                    <Icon className="size-6" />
                  </div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Step {i + 1}</p>
                  <h3 className="text-lg font-bold">{title}</h3>
                  <p className="text-sm text-muted-foreground">{text}</p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </section>

      <section className="bg-muted px-6 py-16">
        <div className="mx-auto max-w-5xl">
          <h2 className="mb-10 text-center text-3xl font-bold">What you get</h2>
          <motion.div
            className="grid gap-6 sm:grid-cols-2"
            variants={staggerContainer}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-60px" }}
          >
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <motion.div key={title} variants={fadeUp} whileHover={{ y: -4 }}>
                <Card className="h-full">
                  <CardContent className="flex gap-4">
                    <Icon className="mt-1 size-6 shrink-0 text-primary" />
                    <div>
                      <h3 className="font-bold">{title}</h3>
                      <p className="text-sm text-muted-foreground">{text}</p>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      <section className="mx-auto max-w-3xl px-6 py-16">
        <Card className="relative overflow-hidden">
          <div className="absolute -left-10 -top-10 size-40 rounded-full bg-gradient-to-br from-[var(--glow-from)] to-[var(--glow-to)] blur-[40px]" />
          <CardContent className="relative flex gap-4">
            <Lock className="mt-1 size-6 shrink-0 text-primary" />
            <div className="space-y-2 text-sm text-muted-foreground">
              <h3 className="text-base font-bold text-foreground">Private by link</h3>
              <p>
                Teams are never listed or searchable. Only people with the link can see a team page.
              </p>
              <p>
                We only read activities you share with Everyone or Followers, never your privacy
                zones, and we cut the start and end off every route.
              </p>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
