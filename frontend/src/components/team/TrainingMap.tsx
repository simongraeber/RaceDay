import { useEffect, useRef, useState } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MapPinned } from "lucide-react"
import RunnerSprite from "@/components/team/RunnerSprite"
import { api, type MapRoute, type TeamMap, type Track } from "@/lib/api"
import { loadMapkit } from "@/lib/mapkit"

// Everyone runs 30x real time so a Sunday long run fits into a minute
const SPEED = 30
const FRAME_MS = 40
// Home turf: the map opens here unless the team's routes are somewhere else entirely
const HOME = { north: 48.28162846561217, west: 11.472049612467698, south: 48.054257854159516, east: 11.730924273482833 }

function chooseRoute(routes: MapRoute[], previousIndex = -1): { route: MapRoute; index: number } {
  const options = routes.map((route, index) => ({ route, index })).filter(({ index }) => index !== previousIndex)
  const choices = options.length ? options : routes.map((route, index) => ({ route, index }))
  return choices[Math.floor(Math.random() * choices.length)]
}

function routeDuration(route: MapRoute): number {
  return Math.max(4, route.duration_s / SPEED) * 1000
}

type MovingSprite = {
  track: Track
  routes: MapRoute[]
  routeIndex: number
  route: MapRoute
  element: HTMLDivElement
  root: Root
  annotation: any
  lengths: number[]
  duration: number
  startedAt: number
}

function homeShare(paths: [number, number][][]): number {
  const points = paths.flat()
  const local = points.filter(
    ([lat, lng]) => lat <= HOME.north && lat >= HOME.south && lng >= HOME.west && lng <= HOME.east,
  )
  return points.length ? local.length / points.length : 0
}

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
        // Holiday runs abroad must not zoom the map out to the whole globe
        const atHome = homeShare(data.heat) >= 0.1
        map = new mapkit.Map(container.current, {
          region: atHome
            ? new mapkit.BoundingRegion(HOME.north, HOME.east, HOME.south, HOME.west).toCoordinateRegion()
            : undefined,
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
        if (!atHome) {
          map.showItems(heat, { animate: false, padding: new mapkit.Padding(32, 32, 32, 32) })
        }

        const sprites: MovingSprite[] = data.tracks.map((track: Track) => {
          const routes = track.routes?.length ? track.routes : [track]
          const selection = chooseRoute(routes)
          const element = document.createElement("div")
          const root = createRoot(element)
          root.render(<RunnerSprite track={{ ...track, ...selection.route }} />)
          roots.push(root)
          const annotation = new mapkit.Annotation(
            new mapkit.Coordinate(selection.route.path[0][0], selection.route.path[0][1]),
            () => element,
            { anchorOffset: new DOMPoint(0, -32) },
          )
          return {
            track,
            routes,
            routeIndex: selection.index,
            route: selection.route,
            element,
            root,
            annotation,
            lengths: legLengths(selection.route.path),
            duration: routeDuration(selection.route),
            startedAt: performance.now(),
          }
        })

        const updateGroupOffsets = () => {
          const groupIndex = new Map<number, number>()
          for (const sprite of sprites) {
            const seen = groupIndex.get(sprite.route.group) ?? 0
            groupIndex.set(sprite.route.group, seen + 1)
            sprite.annotation.anchorOffset = new DOMPoint(seen * 18, -32)
          }
        }

        updateGroupOffsets()
        map.addAnnotations(sprites.map((s) => s.annotation))
        if (reduceMotion) return

        let last = 0
        const step = (now: number) => {
          frame = requestAnimationFrame(step)
          if (now - last < FRAME_MS) return
          last = now
          let groupChanged = false
          for (const sprite of sprites) {
            if (now - sprite.startedAt >= sprite.duration) {
              const selection = chooseRoute(sprite.routes, sprite.routeIndex)
              sprite.routeIndex = selection.index
              sprite.route = selection.route
              sprite.lengths = legLengths(selection.route.path)
              sprite.duration = routeDuration(selection.route)
              sprite.startedAt = now
              sprite.annotation.coordinate = new mapkit.Coordinate(selection.route.path[0][0], selection.route.path[0][1])
              sprite.root.render(<RunnerSprite track={{ ...sprite.track, ...selection.route }} />)
              groupChanged = true
            }
            const progress = Math.min(1, (now - sprite.startedAt) / sprite.duration)
            const [lat, lng, mirrored] = pointAt(sprite.route.path, sprite.lengths, progress)
            sprite.annotation.coordinate = new mapkit.Coordinate(lat, lng)
            sprite.element.firstElementChild?.classList.toggle("is-mirrored", mirrored)
          }
          if (groupChanged) updateGroupOffsets()
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
