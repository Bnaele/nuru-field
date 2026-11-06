// WateringReminders — which tracked plants are due for water today.
//
// Reads the same server-backed list as MyPlants, passed down from FieldPage, so
// adding a plant in one card shows up in the other immediately. The previous
// version held its own localStorage copy, which meant the two cards disagreed
// until the page was reloaded.
//
// The two-day cadence is a rough default for vegetables, not a measured
// requirement, and the card says as much.

import { useState } from 'react'
import Icon from './Icon'
import { isDue, wateredLabel } from '../hooks/usePlants'

const DEFAULT_INTERVAL_DAYS = 2

export default function WateringReminders({ plants: store }) {
  const { plants, loading, error, waterPlant } = store
  const [busyId, setBusyId] = useState(null)
  const [actionError, setActionError] = useState('')

  const due = plants.filter((plant) => isDue(plant, DEFAULT_INTERVAL_DAYS))

  const handleWater = async (plant) => {
    setBusyId(plant.id)
    setActionError('')
    try {
      await waterPlant(plant.id)
    } catch (waterError) {
      setActionError(waterError.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="container">
      <div className="watering-card card">
        <div className="card-label">
          <span><Icon name="water" size={18} /> WATERING REMINDERS</span>
          {due.length > 0 && <span className="due-badge">{due.length} due</span>}
        </div>

        {(actionError || error) && (
          <p className="form-error" role="alert">{actionError || error}</p>
        )}

        {loading && <p className="watering-empty">Loading your plants…</p>}

        {!loading && plants.length === 0 && !error && (
          <p className="watering-empty">
            No plants yet. Add one above to start tracking waterings.
          </p>
        )}

        {!loading && plants.length > 0 && due.length === 0 && (
          <p className="watering-empty watering-good">
            <Icon name="check" size={16} /> Nothing is due today. Every plant was watered
            recently.
          </p>
        )}

        {due.length > 0 && (
          <ul className="watering-list">
            {due.map((plant) => (
              <li key={plant.id}>
                <div>
                  <strong>{plant.name}</strong>
                  <span>{wateredLabel(plant.last_watered_at)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleWater(plant)}
                  disabled={busyId === plant.id}
                >
                  <Icon name="water" size={15} />
                  {busyId === plant.id ? 'Saving…' : 'Water now'}
                </button>
              </li>
            ))}
          </ul>
        )}

        <p className="watering-note">
          Due after {DEFAULT_INTERVAL_DAYS} days without water — a general guide for
          vegetables, not a measured requirement for every crop.
        </p>
      </div>
    </div>
  )
}
