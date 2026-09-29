import { useEffect, useRef, useState } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MapPinned } from "lucide-react"
import RunnerSprite from "@/components/team/RunnerSprite"
import { api, type TeamMap, type Track } from "@/lib/api"
import { loadMapkit } from "@/lib/mapkit"

// Everyone runs 30x real time so a Sunday long run fits into a minute
const SPEED = 30
const FRAME_MS = 40

function legLengths(path: [number, number][]): number[] {
  const lengths = [0]
  for (let i = 1; i < path.length; i++) {
    const [lat1, lng1] = path[i - 1]
    const [lat2, lng2] = path[i]
    const dx = (lng2 - lng1) * Math.cos((lat1 * Math.PI) / 180)
    const dy = lat2 - lat1
    lengths.push(lengths[i - 1] + Math.hypot(dx, dy))
  }
  return lengths
}

function pointAt(path: [number, number][], lengths: number[], progress: number): [number, number, boolean] {
  const target = lengths[lengths.length - 1] * progress
  let i = 1
  while (i < lengths.length - 1 && lengths[i] < target) i++
  const span = lengths[i] - lengths[i - 1] || 1
  const t = (target - lengths[i - 1]) / span
  const [lat1, lng1] = path[i - 1]
  const [lat2, lng2] = path[i]
  // The character art faces west, so mirror it when the runner heads east
  return [lat1 + (lat2 - lat1) * t, lng1 + (lng2 - lng1) * t, lng2 > lng1]
}

export default function TrainingMap({ teamId }: { teamId: string }) {
  const container = useRef<HTMLDivElement>(null)
  const [data, setData] = useState<TeamMap | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    api.teamMap(teamId).then(setData).catch(() => setFailed(true))
  }, [teamId])

  useEffect(() => {
    if (!data || !container.current || data.heat.length === 0) return
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    const roots: Root[] = []
    let cancelled = false
    let frame = 0
    let map: any = null
    let onError: (() => void) | null = null
    let kit: any = null

    loadMapkit()
      .then((mapkit) => {
        if (cancelled || !container.current) return
        // A token for another domain only fails once MapKit tries to draw
        kit = mapkit
        onError = () => setFailed(true)
        mapkit.addEventListener("error", onError)
        map = new mapkit.Map(container.current, {
          showsCompass: mapkit.FeatureVisibility.Hidden,
          showsZoomControl: true,
          showsMapTypeControl: false,
          isRotationEnabled: false,
          colorScheme: window.matchMedia("(prefers-color-scheme: dark)").matches
            ? mapkit.Map.ColorSchemes.Dark
            : mapkit.Map.ColorSchemes.Light,
        })

        const heat = data.heat.map(
          (path) =>
            new mapkit.PolylineOverlay(
              path.map(([lat, lng]) => new mapkit.Coordinate(lat, lng)),
              {
                style: new mapkit.Style({
                  lineWidth: 6,
                  lineJoin: "round",
                  lineCap: "round",
                  strokeColor: "#f97316",
                  strokeOpacity: 0.16,
                }),
              },
            ),
        )
        map.addOverlays(heat)
        map.showItems(heat, { animate: false, padding: new mapkit.Padding(32, 32, 32, 32) })

        // Runs done together share a group, so they keep the same clock and stay side by side
        const groupDuration = new Map<number, number>()
        data.tracks.forEach((t) => {
          groupDuration.set(t.group, Math.min(groupDuration.get(t.group) ?? Infinity, t.duration_s))
        })
        const groupIndex = new Map<number, number>()

        const sprites = data.tracks.map((track: Track) => {
          const element = document.createElement("div")
          const root = createRoot(element)
          root.render(<RunnerSprite track={track} />)
          roots.push(root)
          const seen = groupIndex.get(track.group) ?? 0
          groupIndex.set(track.group, seen + 1)
          const annotation = new mapkit.Annotation(
            new mapkit.Coordinate(track.path[0][0], track.path[0][1]),
            () => element,
            { anchorOffset: new DOMPoint(seen * 18, -32) },
          )
          return {
            track,
            element,
            annotation,
            lengths: legLengths(track.path),
            duration: Math.max(4, (groupDuration.get(track.group) ?? track.duration_s) / SPEED) * 1000,
          }
        })
        map.addAnnotations(sprites.map((s) => s.annotation))
        if (reduceMotion) return

        const start = performance.now()
        let last = 0
        const step = (now: number) => {
          frame = requestAnimationFrame(step)
          if (now - last < FRAME_MS) return
          last = now
          for (const sprite of sprites) {
            const progress = ((now - start) % sprite.duration) / sprite.duration
            const [lat, lng, mirrored] = pointAt(sprite.track.path, sprite.lengths, progress)
            sprite.annotation.coordinate = new mapkit.Coordinate(lat, lng)
            sprite.element.firstElementChild?.classList.toggle("is-mirrored", mirrored)
          }
        }
        frame = requestAnimationFrame(step)
      })
      .catch(() => setFailed(true))

    return () => {
      cancelled = true
      cancelAnimationFrame(frame)
      if (onError) kit?.removeEventListener("error", onError)
      roots.forEach((root) => queueMicrotask(() => root.unmount()))
      map?.destroy()
    }
  }, [data])

  if (failed || (data && data.heat.length === 0)) {
    return (
      <div className="flex h-44 items-center justify-center gap-3 border border-dashed border-border text-sm text-muted-foreground">
        <MapPinned className="size-5" />
        {failed ? "Map unavailable right now" : "No routes yet — the first run draws the map"}
      </div>
    )
  }

  return (
    <div className="training-map">
      <div ref={container} className="training-map-canvas" aria-label="Team training map" />
      {!data && <div className="training-map-loading">Loading routes…</div>}
    </div>
  )
}
