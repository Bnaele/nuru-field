// MyPlants — add, view and remove tracked plants.
//
// Plants now live in Postgres, keyed to the signed-in user. They used to live in
// localStorage, so clearing the browser or opening a different device lost every
// plant and every watering reminder with it.
//
// The crop field is free text with suggestions rather than a fixed dropdown: the
// crop catalogue covers 2,066 species, and a 26-item list would have made most
// of them impossible to record.

import { useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon'
import { localDateString, stageFromDate } from '../hooks/usePlants'
import { slugify } from '../lib/slug'

const SUGGESTIONS = [
  'Maize', 'Wheat', 'Sorghum', 'Sunflower', 'Spinach', 'Cabbage', 'Carrot',
  'Tomato', 'Onion', 'Potato', 'Dry beans', 'Peas', 'Pumpkin', 'Butternut',
  'Grape', 'Citrus', 'Mango', 'Avocado', 'Marula', 'Olive', 'Strawberry',
  'Peach', 'Chilli', 'Herb', 'Fodder',
]

// Local date, not the UTC one: see localDateString. Both the default value and
// the picker's `max` read from here, so they always agree with the grower's own
// calendar.
const today = () => localDateString()

export default function MyPlants({ plants: store }) {
  const { plants, loading, error, addPlant, removePlant } = store

  const [name, setName] = useState('')
  const [cropType, setCropType] = useState('')
  const [plantingDate, setPlantingDate] = useState(today())
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState('')

  const handleAdd = async (event) => {
    event.preventDefault()
    if (!name.trim() || busy) return

    setBusy(true)
    setFormError('')
    try {
      await addPlant({
        name: name.trim(),
        cropType: cropType.trim(),
        plantingDate,
      })
      // Keep the date: someone adding several beds usually planted them together.
      setName('')
      setCropType('')
    } catch (addError) {
      setFormError(addError.message)
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async (plant) => {
    setFormError('')
    try {
      await removePlant(plant.id)
    } catch (removeError) {
      setFormError(removeError.message)
    }
  }

  return (
    <div className="container">
      <div className="my-plants card">
        <div className="card-label">
          <span><Icon name="leaf" size={18} /> MY PLANTS</span>
          {plants.length > 0 && <span className="plant-count">{plants.length}</span>}
        </div>

        <form className="plant-add-form" onSubmit={handleAdd}>
          <div className="plant-add-row">
            <label>
              <span>Label</span>
              <input
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Back garden bed 1"
                maxLength={60}
                required
              />
            </label>
            <label>
              <span>Crop</span>
              <input
                type="text"
                value={cropType}
                onChange={(event) => setCropType(event.target.value)}
                placeholder="Any crop, e.g. Tomato"
                maxLength={60}
                list="crop-suggestions"
              />
              <datalist id="crop-suggestions">
                {SUGGESTIONS.map((crop) => <option key={crop} value={crop} />)}
              </datalist>
            </label>
            <label>
              <span>Planted</span>
              <input
                type="date"
                value={plantingDate}
                max={today()}
                onChange={(event) => setPlantingDate(event.target.value)}
              />
            </label>
            <button type="submit" className="plant-add-button" disabled={busy}>
              <Icon name="leaf" size={16} /> {busy ? 'Adding…' : 'Add plant'}
            </button>
          </div>
        </form>

        {(formError || error) && (
          <p className="form-error" role="alert">{formError || error}</p>
        )}

        {loading && <p className="plant-empty">Loading your plants…</p>}

        {!loading && plants.length === 0 && !error && (
          <p className="plant-empty">
            No plants yet. Add your first one above and it will appear in the watering
            reminders below.
          </p>
        )}

        {plants.length > 0 && (
          <ul className="plant-list">
            {plants.map((plant) => (
              <li key={plant.id}>
                <div className="plant-info">
                  <strong>{plant.name}</strong>
                  <span className="plant-meta">
                    {plant.crop_type ? (
                      // The crop a grower typed is the best handle on its guide:
                      // the backend resolves both common and local names.
                      <Link to={`/crop/${slugify(plant.crop_type)}`} className="plant-crop-link">
                        {plant.crop_type}
                        <Icon name="arrow" size={12} />
                      </Link>
                    ) : (
                      'crop not set'
                    )}{' '}
                    · {stageFromDate(plant.planting_date)}
                  </span>
                </div>
                <button
                  className="plant-delete"
                  type="button"
                  onClick={() => handleRemove(plant)}
                  aria-label={`Delete ${plant.name}`}
                  title="Remove plant"
                >
                  <Icon name="close" size={15} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
