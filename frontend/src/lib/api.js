// One client for the FastAPI backend.
//
// Before this existed, three files each declared their own API_BASE_URL and
// each hand-rolled its own fetch, and the Supabase token was threaded through
// props down to a component that never accepted it. Centralising both fixes the
// duplicated constants and the prop mismatch in one place.
//
// Everything here returns the API's own response body. Where the backend has a
// deliberate shape (a source block, a confidence, an 'available: false'), that
// shape is passed through rather than flattened: the UI needs it to be honest
// about where a number came from.

const DEFAULT_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

/** Thrown for every failure, so callers have one thing to catch. */
export class ApiError extends Error {
  constructor(message, { status = 0, unreachable = false } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    /** True when the request never got a response, i.e. the API is down. */
    this.unreachable = unreachable
  }
}

// Set once when the session changes, rather than threaded through every
// component. Only authenticated endpoints read it, and the backend ignores it
// on the public ones.
let accessToken = null

export function setAccessToken(token) {
  accessToken = token || null
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`

  let response
  try {
    response = await fetch(`${DEFAULT_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    // Abort is a caller decision, not a failure to report.
    if (error?.name === 'AbortError') throw error
    // A rejected CORS preflight is indistinguishable from a dead server down here:
    // the browser reports both as a bare TypeError with no status and no body.
    // Naming the address that was tried, and the origin the API has to allow,
    // turns the usual "but the backend IS running" into one glance.
    const origin = typeof window === 'undefined' ? 'this origin' : window.location.origin
    throw new ApiError(
      `Cannot reach the Nuru API at ${DEFAULT_BASE_URL}. If it is running locally, check ` +
        `that it is up and that its CORS_ORIGINS includes ${origin}.`,
      { unreachable: true },
    )
  }

  if (response.status === 204) return null

  // A proxy or a crashed worker can return HTML where JSON is expected, so a
  // parse failure must not leak a SyntaxError to the UI.
  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    throw new ApiError(
      payload?.detail || `The API returned ${response.status}. Please try again.`,
      { status: response.status },
    )
  }

  return payload
}

function query(params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const api = {
  health: () => request('/api/health'),

  /** Weather, climate normal, region and soil for one coordinate. */
  fieldProfile: (latitude, longitude, options = {}) =>
    request(`/api/field-profile${query({ lat: latitude, lon: longitude })}`, options),

  soilProfile: (latitude, longitude, options = {}) =>
    request(`/api/soil-profile${query({ lat: latitude, lon: longitude })}`, options),

  /**
   * Crops scored against this field's measured conditions.
   * `includeAll` searches the whole catalogue, including species with no common
   * name yet, which is how a grower reaches the ~1,700 non-curated species.
   * `q` finds a plant the grower already has in mind: it searches common name,
   * scientific name and botanical family across the entire catalogue and ignores
   * the recommendation score floor, so the plant always comes back with its
   * score and cautions rather than silently vanishing.
   */
  crops: (latitude, longitude, { limit, category, includeAll, q, ...options } = {}) =>
    request(
      `/api/crops${query({
        lat: latitude,
        lon: longitude,
        limit,
        category: Array.isArray(category) ? category.join(',') : category,
        include_all: includeAll ? 'true' : undefined,
        q,
      })}`,
      options,
    ),

  marketPrices: ({ q, limit, includeUnsold, ...options } = {}) =>
    request(
      `/api/market-prices${query({
        q,
        limit,
        include_unsold: includeUnsold ? 'true' : undefined,
      })}`,
      options,
    ),

  soilScans: (options = {}) => request('/api/soil-scans', options),

  analysePhoto: ({ image, mimeType, location, weatherContext }, options = {}) =>
    request('/api/soil-analysis', {
      method: 'POST',
      body: { image, mimeType, location, weatherContext },
      ...options,
    }),

  askAdviser: ({ message, history, fieldContext }, options = {}) =>
    request('/api/farm-chat', {
      method: 'POST',
      body: { message, history, fieldContext },
      ...options,
    }),

  plants: (options = {}) => request('/api/plants', options),

  addPlant: ({ name, cropType, plantingDate }, options = {}) =>
    request('/api/plants', {
      method: 'POST',
      body: { name, crop_type: cropType, planting_date: plantingDate || null },
      ...options,
    }),

  waterPlant: (plantId, options = {}) =>
    request(`/api/plants/${plantId}/watered`, { method: 'POST', ...options }),

  removePlant: (plantId, options = {}) =>
    request(`/api/plants/${plantId}`, { method: 'DELETE', ...options }),
}
