import { Card, CardContent } from "@/components/ui/card"
import StravaConnectButton from "@/components/StravaConnectButton"
import { stravaLoginUrl } from "@/lib/api"

export default function JoinTeamCard({ teamId }: { teamId: string }) {
  return (
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
  )
}
