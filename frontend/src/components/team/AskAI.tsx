import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  Clock, Crown, Flame, Footprints, Heart, Loader2, Mountain, Send, Sparkles, Star, Timer,
  TrendingUp, Trophy, Users, Zap, type LucideIcon,
} from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { api, ApiError, type AIComponent, type AskResponse } from "@/lib/api"
import { cn } from "@/lib/utils"

const ICON_MAP: Record<string, { icon: LucideIcon; color: string }> = {
  footprints: { icon: Footprints, color: "text-orange-500" },
  flame: { icon: Flame, color: "text-orange-500" },
  crown: { icon: Crown, color: "text-yellow-500" },
  trophy: { icon: Trophy, color: "text-green-500" },
  timer: { icon: Timer, color: "text-blue-500" },
  mountain: { icon: Mountain, color: "text-emerald-600" },
  zap: { icon: Zap, color: "text-purple-500" },
  users: { icon: Users, color: "text-blue-500" },
  "trending-up": { icon: TrendingUp, color: "text-green-500" },
  clock: { icon: Clock, color: "text-blue-500" },
  star: { icon: Star, color: "text-yellow-500" },
  heart: { icon: Heart, color: "text-pink-500" },
}

const EXAMPLE_QUESTIONS = [
  "Who ran the most kilometres this month?",
  "Who has the fastest 5k?",
  "Which weekday do we run most often?",
  "Who climbed the most this year?",
  "How did my pace change over the last weeks?",
]

const EASE = [0.25, 0.46, 0.45, 0.94] as const

function AvatarStack({ urls, name, size = "sm" }: { urls?: string[]; name: string; size?: "sm" | "md" }) {
  if (!urls?.length) return null
  const sizeClass = size === "md" ? "size-10" : "size-6"
  return (
    <span className="flex items-center">
      {urls.map((url, i) => (
        <img
          key={url}
          src={url}
          alt={name}
          loading="lazy"
          className={cn(sizeClass, i > 0 && (size === "md" ? "-ml-3" : "-ml-2"), "rounded-full bg-muted object-cover object-top ring-2 ring-background")}
        />
      ))}
    </span>
  )
}

function RankedListCard({ icon, title, items }: Extract<AIComponent, { type: "ranked-list" }>) {
  const { icon: Icon, color } = ICON_MAP[icon] ?? ICON_MAP.star
  return (
    <Card className="rounded-2xl bg-background">
      <CardContent className="pt-5 pb-4">
        <div className="mb-3 flex items-center gap-2">
          <Icon className={`size-5 shrink-0 ${color}`} />
          <span className="text-sm font-semibold">{title}</span>
        </div>
        <div className="space-y-1.5">
          {items.map((item, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2">
                <span className="w-5 shrink-0 text-right text-xs font-medium text-muted-foreground">{i + 1}.</span>
                <AvatarStack urls={item.image_urls} name={item.label} />
                <span className="font-medium">{item.label}</span>
              </span>
              <span className="font-mono text-xs text-muted-foreground">{item.value}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function StatHighlightCard({ icon, label, value, subtitle, image_urls }: Extract<AIComponent, { type: "stat-highlight" }>) {
  const { icon: Icon, color } = ICON_MAP[icon] ?? ICON_MAP.star
  return (
    <Card className="rounded-2xl bg-background">
      <CardContent className="flex items-center gap-4 pt-5 pb-4">
        {image_urls?.length ? (
          <AvatarStack urls={image_urls} name={label} size="md" />
        ) : (
          <div className="rounded-xl bg-muted p-2.5">
            <Icon className={`size-6 ${color}`} />
          </div>
        )}
        <div>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="text-2xl font-bold tracking-tight">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

function ComparisonCard({ title, sides }: Extract<AIComponent, { type: "comparison" }>) {
  return (
    <Card className="rounded-2xl bg-background">
      <CardContent className="pt-5 pb-4">
        <p className="mb-3 text-center text-sm font-semibold">{title}</p>
        <div className="grid grid-cols-2 gap-4">
          {sides.map((side, i) => (
            <div key={i} className="space-y-2 text-center">
              <div className="flex justify-center"><AvatarStack urls={side.image_urls} name={side.name} size="md" /></div>
              <p className="text-sm font-semibold">{side.name}</p>
              {side.stats.map((s) => (
                <div key={s.label} className="text-xs">
                  <span className="text-muted-foreground">{s.label}: </span>
                  <span className="font-mono font-medium">{s.value}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function BarChartCard({ title, bars }: Extract<AIComponent, { type: "bar-chart" }>) {
  const max = Math.max(...bars.map((b) => b.value), 1)
  return (
    <Card className="rounded-2xl bg-background">
      <CardContent className="pt-5 pb-4">
        <p className="mb-3 text-sm font-semibold">{title}</p>
        <div className="space-y-2">
          {bars.map((bar, i) => (
            <div key={i} className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5">
                  <AvatarStack urls={bar.image_urls} name={bar.label} />
                  <span className="font-medium">{bar.label}</span>
                </span>
                <span className="font-mono text-muted-foreground">{bar.value}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary/60" style={{ width: `${(bar.value / max) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function TableCard({ title, columns, rows }: Extract<AIComponent, { type: "table" }>) {
  return (
    <Card className="rounded-2xl bg-background">
      <CardContent className="pt-5 pb-4">
        <p className="mb-3 text-sm font-semibold">{title}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                {columns.map((col) => (
                  <th key={col} className="px-2 py-1.5 text-left font-medium text-muted-foreground">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0">
                  {columns.map((col) => <td key={col} className="px-2 py-1.5">{row[col] ?? ""}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

function CalloutCard({ emoji, text }: Extract<AIComponent, { type: "callout" }>) {
  return (
    <Card className="flex items-start gap-2 rounded-2xl bg-background px-4 py-3">
      <span className="text-lg">{emoji}</span>
      <p className="text-sm leading-relaxed text-foreground">{text}</p>
    </Card>
  )
}

function HeadToHeadCard({ player_a, player_b, stats }: Extract<AIComponent, { type: "head-to-head" }>) {
  return (
    <Card className="rounded-2xl bg-background">
      <CardContent className="pt-5 pb-4">
        <div className="mb-4 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
          {[player_a, player_b].map((p, i) => (
            <div key={i} className={cn("text-center", i === 1 && "order-3")}>
              <div className="mb-1 flex justify-center"><AvatarStack urls={p.image_urls} name={p.name} size="md" /></div>
              <p className="text-sm font-semibold">{p.name}</p>
            </div>
          ))}
          <span className="order-2 text-xs font-bold text-muted-foreground">VS</span>
        </div>
        <div className="space-y-1.5">
          {stats.map((s) => (
            <div key={s.label} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-xs">
              <span className="text-right font-mono font-medium">{s.a}</span>
              <span className="min-w-[60px] text-center text-muted-foreground">{s.label}</span>
              <span className="text-left font-mono font-medium">{s.b}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function AIShimmerBorder({ active = false, borderWidth = 2, children }: { active?: boolean; borderWidth?: number; children: React.ReactNode }) {
  return (
    <div className="relative">
      <div
        className="ai-shimmer-track ai-shimmer-glow pointer-events-none absolute inset-0 transition-opacity duration-700"
        style={{ opacity: active ? 0.45 : 0, "--shimmer-radius": "0.75rem" } as React.CSSProperties}
      >
        <div className="ai-shimmer ai-shimmer-spin" />
      </div>
      <div
        className="relative bg-background ring-offset-background transition-[border-color] duration-500 focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2"
        style={{
          borderRadius: "0.7rem",
          margin: `${borderWidth}px`,
          border: "1px solid",
          borderColor: active ? "transparent" : "var(--input)",
        }}
      >
        {children}
      </div>
    </div>
  )
}

function AIComponentRenderer({ component }: { component: AIComponent }) {
  switch (component.type) {
    case "ranked-list": return <RankedListCard {...component} />
    case "stat-highlight": return <StatHighlightCard {...component} />
    case "comparison": return <ComparisonCard {...component} />
    case "bar-chart": return <BarChartCard {...component} />
    case "table": return <TableCard {...component} />
    case "callout": return <CalloutCard {...component} />
    case "head-to-head": return <HeadToHeadCard {...component} />
    default: return null
  }
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const detail = JSON.parse(err.message).detail
      if (typeof detail === "string") return detail
    } catch { /* not JSON */ }
  }
  return "Something went wrong. Please try again."
}

export default function AskAI({ teamId }: { teamId: string }) {
  const [question, setQuestion] = useState("")
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AskResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resultKey, setResultKey] = useState(0)

  const handleAsk = async (q?: string) => {
    const text = (q ?? question).trim()
    if (text.length < 3 || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    setResultKey((k) => k + 1)
    try {
      setResult(await api.ask(teamId, text))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section aria-labelledby="ask-heading">
      <div className="mb-5">
        <p className="mb-1 text-xs font-bold uppercase text-primary">Team analyst</p>
        <h2 id="ask-heading" className="flex items-center gap-2 text-2xl font-bold">
          <Sparkles className="size-5 text-purple-500" /> Ask AI
        </h2>
      </div>
      <Card className="overflow-visible">
        <CardContent className="space-y-4">
          <AIShimmerBorder active={loading}>
            <form onSubmit={(e) => { e.preventDefault(); handleAsk() }} className="flex gap-2 p-0">
              <Input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask anything about your team's runs…"
                disabled={loading}
                maxLength={500}
                aria-label="Question"
                className="border-0 focus-visible:ring-0 focus-visible:ring-offset-0"
              />
              <Button type="submit" disabled={loading || question.trim().length < 3} size="icon" className="shrink-0" aria-label="Send question">
                {loading ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
              </Button>
            </form>
          </AIShimmerBorder>

          {!result && !error && !loading && (
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => { setQuestion(q); handleAsk(q) }}
                  className="cursor-pointer rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  {q}
                </button>
              ))}
            </div>
          )}

          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive"
              >
                {error}
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence mode="wait">
            {result && (
              <motion.div
                key={resultKey}
                initial={{ opacity: 0, y: 16, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.97, transition: { duration: 0.2 } }}
                transition={{ duration: 0.35, ease: EASE }}
                className="space-y-3"
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  {result.components.map((comp, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 12, scale: 0.97 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ delay: i * 0.08, duration: 0.35, ease: EASE }}
                      className={["table", "head-to-head", "comparison", "bar-chart"].includes(comp.type) || result.components.length === 1 ? "sm:col-span-2" : ""}
                    >
                      <AIComponentRenderer component={comp} />
                    </motion.div>
                  ))}
                </div>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: result.components.length * 0.08 + 0.15, duration: 0.3 }}
                  className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-muted-foreground"
                >
                  <span className="whitespace-nowrap">AI can make mistakes — verify important stats.</span>
                  <span className="whitespace-nowrap">
                    {result.remaining} question{result.remaining !== 1 ? "s" : ""} remaining this hour
                  </span>
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </CardContent>
      </Card>
    </section>
  )
}
