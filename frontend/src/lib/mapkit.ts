/** MapKit JS loader — the token comes from our backend, never from the bundle. */

type MapKit = any

declare global {
  interface Window {
    mapkit?: MapKit
  }
}

const SCRIPT = "https://cdn.apple-mapkit.com/mk/5.x.x/mapkit.js"

let loader: Promise<MapKit> | null = null

async function fetchToken(): Promise<string> {
  const res = await fetch("/api/v1/maps/token")
  if (!res.ok) throw new Error("Maps are not configured")
  return (await res.json()).token as string
}

export function loadMapkit(): Promise<MapKit> {
  loader ??= new Promise<MapKit>((resolve, reject) => {
    const script = document.createElement("script")
    script.src = SCRIPT
    script.crossOrigin = "anonymous"
    script.onerror = () => reject(new Error("Could not load Apple Maps"))
    script.onload = () => {
      const mapkit = window.mapkit
      mapkit.init({
        authorizationCallback: (done: (token: string) => void) => {
          fetchToken().then(done).catch(reject)
        },
      })
      resolve(mapkit)
    }
    document.head.appendChild(script)
  }).catch((err) => {
    loader = null
    throw err
  })
  return loader
}
