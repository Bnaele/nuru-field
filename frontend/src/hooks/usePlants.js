// Plants and watering, stored on the server.
//
// These used to live in localStorage under a shared key, with MyPlants and
// WateringReminders each holding their own useState copy of it. Writes in one
// component never reached the other, because the browser only fires `storage`
// events for *other* tabs — so adding a plant left the reminders card stale
// until a remount. Everything was also lost on a browser clear or a new phone.
//
// One hook, called once, owns the list. Both components receive it as props.

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

export function usePlants() {
  const [plants, setPlants] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // Guards against a slow first load resolving after a newer one, which would
  // show stale rows.
  const requestRef = useRef(0)

  const load = useCallback(
    async (signal) => {
      const request = ++requestRef.current
      setLoading(true)
      setError('')
      try {
        const rows = await api.plants({ signal })
        if (request === requestRef.current) setPlants(rows || [])
      } catch (apiError) {
        if (apiError?.name === 'AbortError') return
        if (request === requestRef.current) setError(apiError.message)
      } finally {
        if (request === requestRef.current) setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  // Mutations throw so the calling component can show the message next to the
  // control that failed, rather than a page-wide banner.
  const addPlant = useCallback(async (input) => {
    const created = await api.addPlant(input)
    setPlants((current) => [created, ...current])
    return created
  }, [])

  const waterPlant = useCallback(async (plantId) => {
    const result = await api.waterPlant(plantId)
    setPlants((current) =>
      current.map((plant) =>
        plant.id === plantId
          ? { ...plant, last_watered_at: result?.watered_at || new Date().toISOString() }
          : plant,
      ),
    )
  }, [])

  const removePlant = useCallback(async (plantId) => {
    await api.removePlant(plantId)
    setPlants((current) => current.filter((plant) => plant.id !== plantId))
  }, [])

  const reload = useCallback(() => load(), [load])

  return { plants, loading, error, addPlant, waterPlant, removePlant, reload }
}

const DAY_MS = 24 * 60 * 60 * 1000

/**
 * Today as YYYY-MM-DD in the grower's own timezone.
 *
 * `new Date().toISOString().slice(0, 10)` is the UTC date. South Africa runs on
 * UTC+2, so between midnight and 02:00 it returns yesterday: the "planted" field
 * defaulted to the wrong day and its `max` refused the current one.
 */
export function localDateString(when = new Date()) {
  const shifted = new Date(when.getTime() - when.getTimezoneOffset() * 60 * 1000)
  return shifted.toISOString().slice(0, 10)
}

/**
 * Milliseconds for a stored date, read as local midnight when it has no time.
 *
 * `new Date('2026-11-06')` is UTC midnight, which is 02:00 on the same day in
 * South Africa. Counting "days since planting" from 02:00 makes a plant added
 * in the evening look a day older than it is for the first two hours of the
 * night.
 */
function parseWhen(value) {
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (dateOnly) {
    return new Date(+dateOnly[1], +dateOnly[2] - 1, +dateOnly[3]).getTime()
  }
  return new Date(value).getTime()
}

/** A plant is due when it has never been watered or the last watering is old. */
export function isDue(plant, intervalDays) {
  if (!plant.last_watered_at) return true
  const last = new Date(plant.last_watered_at).getTime()
  if (Number.isNaN(last)) return true
  return Date.now() - last > intervalDays * DAY_MS
}

/** "3 weeks" style age from the planting date, used for the plant list. */
export function stageFromDate(plantingDate) {
  if (!plantingDate) return 'no planting date'
  const planted = parseWhen(plantingDate)
  if (Number.isNaN(planted)) return 'no planting date'

  const days = Math.floor((Date.now() - planted) / DAY_MS)
  if (days < 0) return 'planned for later'
  if (days < 7) return `planted ${days === 0 ? 'today' : `${days}d ago`}`
  const weeks = Math.floor(days / 7)
  if (weeks < 6) return `growing, ${weeks}w`
  if (weeks < 12) return `established, ${weeks}w`
  return `mature, ${weeks}w`
}

/** Human description of the last watering, for the reminders list. */
export function wateredLabel(lastWateredAt) {
  if (!lastWateredAt) return 'Never watered yet'
  const last = new Date(lastWateredAt).getTime()
  if (Number.isNaN(last)) return 'Never watered yet'

  const days = Math.floor((Date.now() - last) / DAY_MS)
  if (days <= 0) return 'Watered today'
  if (days === 1) return 'Watered yesterday'
  return `Last watered ${days} days ago`
}
