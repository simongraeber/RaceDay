import { formatDate, formatDuration, formatPace } from "@/lib/utils"
import type { Track } from "@/lib/api"

/**
 * One running avatar on the map. The image is a placeholder for a real sprite
 * animation later — swap the <img> here and the map keeps working.
 */
export default function RunnerSprite({ track }: { track: Track }) {
  return (
    <div className="runner-sprite group">
      <div className="runner-sprite-body">
        {track.avatar_url ? (
          <img src={track.avatar_url} alt={track.name} className="runner-sprite-img" draggable={false} />
        ) : (
          <span className="runner-sprite-initial">{track.name.charAt(0).toUpperCase()}</span>
        )}
      </div>
      <span className="runner-sprite-shadow" />
      <div className="runner-sprite-card">
        <p className="font-semibold">{track.name}</p>
        <p>{formatDate(track.date)} · {track.distance_km.toFixed(1)} km</p>
        <p>{formatPace(track.pace_seconds_km)} /km · {formatDuration(track.duration_s)}</p>
      </div>
    </div>
  )
}
