/**
 * Rigged runner: the generated character sheet sliced into body parts and animated.
 * Boxes and mounting points are fixed pixel coordinates in the 682x1024 sheet.
 */

const SHEET = { w: 682, h: 1024 }

type Box = { x: number; y: number; w: number; h: number; pivot: [number, number] }

const HEAD: Box = { x: 0, y: 0, w: 351, h: 391, pivot: [177, 271] }
const TORSO: Box = { x: 0, y: 413, w: 322, h: 611, pivot: [177, 878] }
const TORSO_HEAD: [number, number] = [164, 463]
const TORSO_ARM: [number, number] = [203, 544]
const UPPER_ARM: Box = { x: 503, y: 0, w: 178.5, h: 256, pivot: [562, 48] }
const UPPER_ARM_ELBOW: [number, number] = [599, 193]
const LOWER_ARM_FRONT: Box = { x: 511, y: 281.5, w: 168, h: 309, pivot: [592, 326.5] }
const LOWER_ARM_BACK: Box = { x: 341, y: 136, w: 159, h: 291, pivot: [425, 171] }
const UPPER_LEG: Box = { x: 321, y: 498, w: 176, h: 302, pivot: [405, 547] }
const UPPER_LEG_KNEE: [number, number] = [417, 729]
const LOWER_LEG: Box = { x: 461, y: 698, w: 220, h: 326, pivot: [596.2, 741] }

// Hip (torso leg mount) to crown, and hip to sole — used to size and place the sprite box
const ABOVE_HIP = TORSO.pivot[1] - TORSO_HEAD[1] + HEAD.pivot[1]
const BELOW_HIP = UPPER_LEG_KNEE[1] - UPPER_LEG.pivot[1] + (LOWER_LEG.y + LOWER_LEG.h - LOWER_LEG.pivot[1])
export const RIG_HEIGHT = ABOVE_HIP + BELOW_HIP

function part(box: Box, sheet: string): React.CSSProperties {
  return {
    width: box.w,
    height: box.h,
    left: box.x - box.pivot[0],
    top: box.y - box.pivot[1],
    backgroundImage: `url(${sheet})`,
    backgroundPosition: `${-box.x}px ${-box.y}px`,
    backgroundSize: `${SHEET.w}px ${SHEET.h}px`,
  }
}

function joint(parent: Box, mount: [number, number]): React.CSSProperties {
  return { left: mount[0] - parent.pivot[0], top: mount[1] - parent.pivot[1] }
}

function Arm({ sheet, side }: { sheet: string; side: "front" | "back" }) {
  return (
    <div className={`rig-joint rig-shoulder rig-arm--${side}`} style={joint(TORSO, TORSO_ARM)}>
      <div className="rig-joint rig-elbow" style={joint(UPPER_ARM, UPPER_ARM_ELBOW)}>
        <div className="rig-part" style={part(side === "front" ? LOWER_ARM_FRONT : LOWER_ARM_BACK, sheet)} />
      </div>
      <div className="rig-part rig-upper" style={part(UPPER_ARM, sheet)} />
    </div>
  )
}

function Leg({ sheet, side }: { sheet: string; side: "front" | "back" }) {
  return (
    <div className={`rig-joint rig-hip rig-leg--${side}`} style={joint(TORSO, TORSO.pivot)}>
      <div className="rig-joint rig-knee" style={joint(UPPER_LEG, UPPER_LEG_KNEE)}>
        <div className="rig-part" style={part(LOWER_LEG, sheet)} />
      </div>
      <div className="rig-part rig-upper" style={part(UPPER_LEG, sheet)} />
    </div>
  )
}

export default function RiggedRunner({ sheet, height }: { sheet: string; height: number }) {
  const scale = height / RIG_HEIGHT
  return (
    <div className="rig" style={{ width: height * 0.7, height }}>
      <div className="rig-root" style={{ top: ABOVE_HIP * scale, transform: `scale(${scale})` }}>
        <div className="rig-bob">
          <Arm sheet={sheet} side="back" />
          <Leg sheet={sheet} side="back" />
          <div className="rig-part rig-torso" style={part(TORSO, sheet)} />
          <Leg sheet={sheet} side="front" />
          <Arm sheet={sheet} side="front" />
          <div className="rig-joint rig-head" style={joint(TORSO, TORSO_HEAD)}>
            <div className="rig-part" style={part(HEAD, sheet)} />
          </div>
        </div>
      </div>
    </div>
  )
}
