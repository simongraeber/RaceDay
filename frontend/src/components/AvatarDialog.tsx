import { useEffect, useState, type FormEvent } from "react"
import * as Dialog from "@radix-ui/react-dialog"
import { ImagePlus, Loader2, Trash2, WandSparkles, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { api, ApiError } from "@/lib/api"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  hasAvatar: boolean
  onChange: () => void
}

export default function AvatarDialog({ open, onOpenChange, hasAvatar, onChange }: Props) {
  const [photo, setPhoto] = useState<File | null>(null)
  const [preview, setPreview] = useState("")
  const [description, setDescription] = useState("")
  const [consent, setConsent] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!photo) {
      setPreview("")
      return
    }
    const url = URL.createObjectURL(photo)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [photo])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!photo || !consent) return
    setWorking(true)
    setError("")
    try {
      await api.generateAvatar(photo, description)
      onChange()
      onOpenChange(false)
      setPhoto(null)
      setDescription("")
      setConsent(false)
    } catch (cause) {
      const code = cause instanceof ApiError ? cause.status : 0
      setError(code === 401 ? "Your session expired. Connect with Strava again."
        : code === 503 ? "Avatar generation is not configured yet."
        : code === 429 ? "Please wait five minutes before trying again."
        : code === 413 ? "Choose a photo under 5 MB."
        : code === 422 ? "Please choose a valid PNG, JPEG or WebP photo."
        : "Could not generate your avatar. Please try again.")
    } finally {
      setWorking(false)
    }
  }

  async function remove() {
    if (!window.confirm("Remove your generated avatar?")) return
    setWorking(true)
    setError("")
    try {
      await api.deleteAvatar()
      onChange()
      onOpenChange(false)
    } catch {
      setError("Could not remove your avatar. Please try again.")
    } finally {
      setWorking(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!working) onOpenChange(next) }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[min(95vw,580px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-border bg-background p-5 shadow-xl sm:p-7">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-xl font-bold">Your running avatar</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                Turn a photo into a 3D runner for your team page.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild><Button variant="ghost" size="sm" aria-label="Close" title="Close"><X /></Button></Dialog.Close>
          </div>

          <form onSubmit={submit} className="mt-6 space-y-5">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="mb-2 text-sm font-medium">Your photo</p>
                <label className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-2 overflow-hidden rounded-md border border-dashed border-border bg-muted text-sm text-muted-foreground hover:border-primary">
                  {preview ? <img src={preview} alt="Your chosen photo" className="h-full w-full object-cover" /> : <><ImagePlus className="size-7" /> Choose photo</>}
                  <input className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => {
                    const selected = event.target.files?.[0] ?? null
                    setPhoto(selected)
                    setPreview("")
                    setError(selected && selected.size > 5 * 1024 * 1024 ? "Choose a photo under 5 MB." : "")
                  }} />
                </label>
              </div>
              <div>
                <p className="mb-2 text-sm font-medium">Character style</p>
                <img src="/api/v1/avatars/style" alt="3D cartoon character reference" className="aspect-square w-full rounded-md border border-border bg-muted object-contain" />
              </div>
            </div>

            <label className="block space-y-2 text-sm font-medium">
              <span>Details to add <span className="font-normal text-muted-foreground">(optional)</span></span>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                maxLength={300}
                rows={2}
                placeholder="e.g. bright orange running shoes, blue headband"
                className="w-full resize-none rounded-md border border-input bg-background p-3 font-normal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>

            <label className="flex items-start gap-3 text-sm text-muted-foreground">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-1 accent-primary" />
              <span>I agree to send my photo and prompt to OpenAI to make this avatar. The original photo is not stored by RaceDay. My generated avatar is visible to anyone with my team link while I am visible.</span>
            </label>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

            <div className="flex flex-wrap items-center justify-between gap-3">
              {hasAvatar ? (
                <Button type="button" variant="ghost" size="sm" disabled={working} onClick={remove}>
                  <Trash2 /> Remove avatar
                </Button>
              ) : <span />}
              <Button type="submit" disabled={!photo || photo.size > 5 * 1024 * 1024 || !consent || working}>
                {working ? <Loader2 className="animate-spin" /> : <WandSparkles />}
                {working ? "Creating avatar…" : "Generate avatar"}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}