// FieldMap — interactive map for picking a field location, with autocomplete search.
//
// Why Leaflet: free, no API key, and the tiles come from OSM.
//
// Design:
//   - The map is pinned to South Africa: it opens centred on the country and
//     cannot be panned away, because every other screen assumes a South African
//     field (crop catalogue, prices, adviser context).
//   - Clicking anywhere drops a marker and fires onPick(lat, lon).
//   - The search box hits Nominatim (OpenStreetMap's free geocoder) as the user
//     types, filtered to South Africa, with a 500 ms debounce to stay inside the
//     1 req/sec usage policy.
//   - The parent (FieldPage) passes onPick, so picking a spot reloads the
//     dashboard for that location.

import { useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, Marker, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIconUrl from 'leaflet/dist/images/marker-icon.png'
import markerIconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import markerShadowUrl from 'leaflet/dist/images/marker-shadow.png'
import Icon from './Icon'
import { formatCoords, isInSouthAfrica, normalizeCoords, SA_BOUNDS } from '../lib/geo'

// Leaflet's default marker icon resolves its PNG URLs relative to its own CSS at
// runtime, which breaks under a bundler. The old code papered over that by
// pointing at unpkg.com, so the marker silently disappeared whenever the CDN was
// blocked or offline. Importing the images lets the bundler emit them as local
// assets and hand back real URLs. Sizes and anchors are copied from Leaflet's
// own default icon so the pin still sits on its point.
const markerIcon = L.icon({
  iconUrl: markerIconUrl,
  iconRetinaUrl: markerIconRetinaUrl,
  shadowUrl: markerShadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  tooltipAnchor: [16, -28],
  shadowSize: [41, 41],
})

// Bounds handed to Leaflet, with a little slack so the coast and the borders are
// still reachable by panning.
const MAP_BOUNDS = [
  [SA_BOUNDS.minLat - 1, SA_BOUNDS.minLon - 1],
  [SA_BOUNDS.maxLat + 1, SA_BOUNDS.maxLon + 1],
]

const NOMINATIM = 'https://nominatim.openstreetmap.org/search'

function nominatimUrl(text, limit) {
  // countrycodes=za keeps the search honest: this app has no data for a farm in
  // Brazil, so offering one as a result would only lead to an empty dashboard.
  const params = new URLSearchParams({
    q: text,
    format: 'json',
    limit: String(limit),
    countrycodes: 'za',
    addressdetails: '0',
  })
  return `${NOMINATIM}?${params.toString()}`
}

// Attaches the click handler to the Leaflet map instance.
function ClickPicker({ onPick }) {
  useMapEvents({
    click(event) {
      const [latitude, longitude] = normalizeCoords(event.latlng.lat, event.latlng.lng)
      onPick(latitude, longitude)
    },
  })
  return null
}

// Imperative handle on the Leaflet map so the parent can recenter it from
// outside (after a search result).
function MapController({ controllerRef }) {
  const map = useMap()
  controllerRef.current = map
  return null
}

export default function FieldMap({ onPick }) {
  const [marker, setMarker] = useState(null)
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [searching, setSearching] = useState(false)
  const mapRef = useRef(null)
  const debounceRef = useRef(null)
  const abortRef = useRef(null)
  const blurRef = useRef(null)

  useEffect(() => () => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (blurRef.current) clearTimeout(blurRef.current)
    if (abortRef.current) abortRef.current.abort()
  }, [])

  const handlePick = (latitude, longitude) => {
    // A click is clamped by the map bounds, but a stale GPS fix or a pasted
    // coordinate can still land outside the country. Say so instead of quietly
    // loading a dashboard whose crops and prices do not apply.
    if (!isInSouthAfrica(latitude, longitude)) {
      setSearchError(
        'That point is outside South Africa. Nuru is built on South African crop, price and weather data, so pick a spot inside the country.',
      )
      return
    }

    setSearchError('')
    setMarker([latitude, longitude])
    onPick(latitude, longitude)
  }

  // Debounced autocomplete. Each keystroke cancels the previous request, so a
  // slow early query cannot overwrite the suggestions of a later, faster one.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)

    const trimmed = query.trim()
    if (trimmed.length < 3) {
      setSuggestions([])
      setShowSuggestions(false)
      return undefined
    }

    debounceRef.current = setTimeout(async () => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      try {
        const response = await fetch(nominatimUrl(trimmed, 5), { signal: controller.signal })
        if (!response.ok) throw new Error(`Nominatim responded ${response.status}`)
        const results = await response.json()
        setSuggestions(results)
        setShowSuggestions(results.length > 0)
        if (!results.length) {
          setSearchError(`Nothing in South Africa matches "${trimmed}". Try a town or province.`)
        }
      } catch (error) {
        if (error.name === 'AbortError') return
        // Autocomplete failing is not worth an error banner on every keystroke;
        // submitting the form reports the same problem properly.
        setSuggestions([])
      }
    }, 500)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query])

  const jumpTo = (place) => {
    const latitude = Number.parseFloat(place.lat)
    const longitude = Number.parseFloat(place.lon)
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return

    mapRef.current?.setView([latitude, longitude], 10)
    handlePick(latitude, longitude)

    setQuery(place.display_name.split(',').slice(0, 3).join(','))
    setSuggestions([])
    setShowSuggestions(false)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const text = query.trim()
    if (!text) return

    setShowSuggestions(false)
    setSearchError('')
    setSearching(true)

    try {
      const response = await fetch(nominatimUrl(text, 1))
      if (!response.ok) throw new Error('Search is unavailable right now. Try tapping the map instead.')
      const results = await response.json()

      if (!results.length) {
        setSearchError(`No place in South Africa matches "${text}". Try a town or province name.`)
        return
      }

      jumpTo(results[0])
    } catch (error) {
      setSearchError(error.message || 'Search failed. Please try again.')
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="container">
      <div className="field-map card">
        <div className="card-label">
          <span><Icon name="location" size={18} /> PICK YOUR INDAWO</span>
        </div>
        <p className="map-lede">
          Start typing a South African town, pick from the list, or tap the map.
          Nuru will fetch the weather and recommend crops for that spot.
        </p>

        <form className="map-search" onSubmit={handleSubmit}>
          <Icon name="location" size={16} />
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
            onBlur={() => {
              // Delay the close so the click on a suggestion lands first.
              blurRef.current = setTimeout(() => setShowSuggestions(false), 200)
            }}
            placeholder="Search for a town or place…"
            aria-label="Search for a location in South Africa"
            autoComplete="off"
          />
          <button type="submit" disabled={!query.trim() || searching}>
            {searching ? 'Searching…' : 'Search'}
          </button>

          {showSuggestions && suggestions.length > 0 && (
            <ul className="map-suggestions">
              {suggestions.map((place) => (
                <li key={place.place_id}>
                  <button
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => jumpTo(place)}
                  >
                    <Icon name="location" size={13} />
                    <span>{place.display_name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </form>

        {searchError && <p className="map-search-error" role="status">{searchError}</p>}

        <MapContainer
          center={[-28.5, 24.5]}
          zoom={5}
          minZoom={5}
          maxBounds={MAP_BOUNDS}
          maxBoundsViscosity={0.9}
          style={{ height: '360px', width: '100%', borderRadius: '14px' }}
          scrollWheelZoom={true}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          />
          <ClickPicker onPick={handlePick} />
          <MapController controllerRef={mapRef} />
          {marker && <Marker position={marker} icon={markerIcon} />}
        </MapContainer>

        {marker && (
          <p className="map-status">
            <Icon name="check" size={16} />
            Selected: {formatCoords(marker[0], marker[1])}
          </p>
        )}
      </div>
    </div>
  )
}
