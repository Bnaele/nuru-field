// Loads the field profile for a coordinate.
//
// Extracted from App.jsx, which had grown to hold session state, location state,
// scan state and chat state in one component. It also fixes a race there: two
// quick map taps could resolve out of order and leave the dashboard showing the
// earlier field.

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { isInSouthAfrica } from '../lib/geo'

// The field someone picked is theirs to keep. Without this, every reload and
// every visit dropped them back to "Connect your location", and a browser that
// cannot produce a GPS fix (Chrome on a desktop with no location provider is the
// common case) had no way back to the field they were looking at yesterday.
const STORAGE_KEY = 'nuru:field'

function readSavedField() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || 'null')
    if (Number.isFinite(saved?.latitude) && Number.isFinite(saved?.longitude)) {
      return saved
    }
  } catch {
    // Private mode, corrupt JSON, disabled storage — none of which is worth
    // failing a page load over.
  }
  return null
}

function saveField(latitude, longitude) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ latitude, longitude }))
  } catch {
    // Storage is a convenience here, not a requirement.
  }
}

export function useFieldProfile() {
  const [profile, setProfile] = useState(null)
  const [status, setStatus] = useState('')
  const [tone, setTone] = useState('idle') // idle | pending | success | error
  const [loading, setLoading] = useState(false)

  const requestRef = useRef(0)
  const abortRef = useRef(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  const load = useCallback(async (latitude, longitude) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const request = ++requestRef.current

    setLoading(true)
    setTone('pending')
    setStatus('Reading live weather, soil and season for this point…')

    try {
      const data = await api.fieldProfile(latitude, longitude, { signal: controller.signal })
      if (request !== requestRef.current) return
      setProfile(data)
      saveField(latitude, longitude)

      // The backend answers anywhere on Earth. Saying so is more useful than
      // pretending a coordinate in Portugal is a South African smallholding.
      if (!isInSouthAfrica(latitude, longitude)) {
        setTone('error')
        setStatus(
          `That point is outside South Africa. Nuru's crops, prices and guidance are South African, so treat anything below as general only.`,
        )
        return
      }

      setTone('success')
      setStatus(`Field profile ready for ${data.location.label}.`)
    } catch (error) {
      if (error?.name === 'AbortError') return
      if (request !== requestRef.current) return
      setTone('error')
      setStatus(error.message)
    } finally {
      if (request === requestRef.current) setLoading(false)
    }
  }, [])

  // Restore the last field as soon as the hook mounts, so the dashboard opens on
  // the grower's own land instead of an empty prompt they have to re-answer.
  useEffect(() => {
    const saved = readSavedField()
    if (saved) load(saved.latitude, saved.longitude)
  }, [load])

  const locate = useCallback(() => {
    if (!navigator.geolocation) {
      setTone('error')
      setStatus('This browser cannot provide a location. Search for a town or tap the map instead.')
      return
    }

    setTone('pending')
    setStatus('Waiting for permission to read your location…')

    navigator.geolocation.getCurrentPosition(
      (position) => {
        load(position.coords.latitude, position.coords.longitude)
      },
      (error) => {
        // A saved field is very often the right answer here: desktop browsers
        // route geolocation through a network provider that can be blocked or
        // unconfigured, so the request fails even though the person's field has
        // not moved. Say what happened without discarding what we already have.
        const hasSavedField = Boolean(profile)
        const suffix = hasSavedField
          ? ' Your last saved field is still loaded.'
          : ' Search for your town or tap the map instead.'

        setTone('error')
        if (error.code === 1) {
          setStatus(`Location permission is blocked for this site. Allow it in your browser settings.${suffix}`)
        } else if (error.code === 2) {
          setStatus(`This device could not work out where it is — its location service is not responding.${suffix}`)
        } else {
          setStatus(`Reading your location took too long. Try again in a moment.${suffix}`)
        }
      },
      // Coarse and cached: a field profile does not need metre accuracy, and a
      // cached fix returns almost instantly on a second visit.
      { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 },
    )
  }, [load, profile])

  return { profile, status, tone, loading, load, locate }
}
