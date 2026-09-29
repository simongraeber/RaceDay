import RiggedRunner from "@/components/team/RiggedRunner"
import { formatDate, formatDuration, formatPace } from "@/lib/utils"
import type { Track } from "@/lib/api"

const HEIGHT = 64

/** One running avatar on the map: the rigged character sheet, or the plain avatar as fallback. */
export default function RunnerSprite({ track }: { track: Track }) {
  return (
    <div className="runner-sprite" style={{ height: HEIGHT, width: HEIGHT * 0.7 }}>
      <div className="runner-sprite-body">
        {track.rig_url ? (
          <RiggedRunner sheet={track.rig_url} height={HEIGHT} />
        ) : track.avatar_url ? (
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
