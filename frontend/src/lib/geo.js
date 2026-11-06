// Geographic helpers and the South Africa bounds the app is built around.
//
// Nuru Field targets South Africa. The data sources work worldwide, but the crop
// catalogue, the price source and the guidance are all South African, so a
// coordinate outside the country is almost always a mis-tap or a stale GPS fix
// rather than a real field. It is worth flagging instead of silently returning
// advice about a farm in Norway.

export const SA_BOUNDS = {
  // Mainland rectangle, deliberately generous: it exists to catch a coordinate
  // that is nowhere near South Africa, not to redraw the border.
  minLat: -35.0,
  maxLat: -22.1,
  minLon: 16.4,
  maxLon: 33.0,
}

/** True if the coordinate falls inside the South African bounding box. */
export function isInSouthAfrica(latitude, longitude) {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return false
  return (
    latitude >= SA_BOUNDS.minLat &&
    latitude <= SA_BOUNDS.maxLat &&
    longitude >= SA_BOUNDS.minLon &&
    longitude <= SA_BOUNDS.maxLon
  )
}

// Leaflet hands back wrapped longitudes when the map is panned past the
// antimeridian, so a click can arrive as 190 rather than -170. Latitude clips.
export function normalizeCoords(latitude, longitude) {
  const wrapped = (((longitude + 180) % 360) + 360) % 360 - 180
  const clamped = Math.max(-90, Math.min(90, latitude))
  return [clamped, wrapped]
}

/** Four decimal places is about 11 m, which is more than a field needs. */
export function formatCoords(latitude, longitude) {
  return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`
}
