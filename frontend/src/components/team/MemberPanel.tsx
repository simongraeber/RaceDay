import { useState } from "react"
import { Eye, EyeOff, LogOut, RefreshCw, WandSparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import AvatarDialog from "@/components/team/AvatarDialog"
import { api, stravaLoginUrl, type Viewer } from "@/lib/api"

interface Props {
  teamId: string
  viewer: Viewer
  openAvatar: boolean
  onChange: () => void
}

export default function MemberPanel({ teamId, viewer, openAvatar, onChange }: Props) {
  const [avatarOpen, setAvatarOpen] = useState(openAvatar)

  async function toggleVisible() {
    await api.updateMembership(teamId, { visible: !viewer.visible })
    onChange()
  }

  async function leave() {
    if (!confirm("Leave this team?")) return
    await api.leaveTeam(teamId)
    onChange()
  }

  return (
    <section aria-label="Your membership" className="space-y-4">
      {viewer.needs_reconnect && (
        <Card className="border-primary/40 bg-secondary">
          <CardContent className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-sm text-secondary-foreground">
              Runs you keep private or share only with followers are missing. Reconnect Strava to count them too.
            </p>
            <Button size="sm" asChild>
              <a href={stravaLoginUrl("join", teamId)}><RefreshCw /> Reconnect Strava</a>
            </Button>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {viewer.avatar_url && <img src={viewer.avatar_url} alt="Your avatar" className="size-12 rounded-full object-cover" />}
            <div>
              <p className="font-semibold">Your runner</p>
              <p className="text-sm text-muted-foreground">{viewer.visible ? "Visible on this team page" : "Hidden from this team page"}</p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => setAvatarOpen(true)}>
            <WandSparkles /> {viewer.has_avatar ? "Edit avatar" : "Make avatar"}
          </Button>
        </CardContent>
      </Card>
      <AvatarDialog open={avatarOpen} onOpenChange={setAvatarOpen} hasAvatar={viewer.has_avatar} onChange={onChange} />
      <div className="flex justify-end gap-2 border-t border-border pt-4">
        <Button variant="outline" size="sm" onClick={toggleVisible}>
          {viewer.visible ? <EyeOff /> : <Eye />}
          {viewer.visible ? "Hide me" : "Show me"}
        </Button>
        <Button variant="ghost" size="sm" onClick={leave}>
          <LogOut /> Leave
        </Button>
      </div>
    </section>
  )
}
