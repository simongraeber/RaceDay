import { Loader2 } from "lucide-react"

export default function LoadingState() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3">
      <Loader2 className="size-8 animate-spin text-primary" />
      <p className="text-sm text-muted-foreground">Loading…</p>
    </div>
  )
}
