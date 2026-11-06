// Loads the field profile for a coordinate.
//
// Extracted from App.jsx, which had grown to hold session state, location state,
// scan state and chat state in one component. It also fixes a race there: two
// quick map taps could resolve out of order and leave the dashboard showing the
// earlier field.

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { isInSouthAfrica } from '../lib/geo'

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
        setTone('error')
        setStatus(
          error.code === 1
            ? 'Location permission was not granted. You can still search for a town or tap the map.'
            : 'Your location could not be determined. Try again outdoors, or search for your town instead.',
        )
      },
      // Coarse and cached: a field profile does not need metre accuracy, and a
      // cached fix returns almost instantly on a second visit.
      { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 },
    )
  }, [load])

  return { profile, status, tone, loading, load, locate }
}
