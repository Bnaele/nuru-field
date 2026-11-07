// CropRecommendations — crops whose ECOCROP envelope fits this field.
//
// Rewritten against the real /api/crops response. The old version expected
// `{ status, crops }` and deduplicated rows because the backend used to return
// each crop twice; both are gone, and it now shows the score, the confidence and
// the reason behind each match, which is the whole point of the endpoint.
//
// The catalogue is every species ECOCROP can score — 2,066 of them, spanning
// fruit, vegetables, herbs, spices, nuts, grains, legumes, oilseeds, fodder,
// fibre, timber, medicinal and ornamental plants. 508 carry a curated common
// name, so there are three ways in:
//
//   * the chips, which filter by category,
//   * the search box, which matches common name, scientific name, botanical
//     family or a South African vernacular name (morogo, amadumbe, spanspek)
//     across the whole catalogue, and
//   * the "no common name" switch, which widens the list to the 1,558 species
//     ECOCROP holds under a Latin name.
//
// Search deliberately ignores the recommendation score floor: a grower who
// searches "protea" gets proteas with their score and cautions, not an empty
// list because proteas are not food.
//
// Species with no common name render their botanical family in place of a common
// name, because "Leguminosae" tells a grower something and a bare Latin binomial
// does not.

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon'
import { api } from '../lib/api'

// The categories present in the reference data. Used only until the first
// response arrives, after which the chips come from the API's own counts so
// they can never promise a category that returns nothing. "Other" is left out:
// it is not a kind of plant, it is a gap in the labelling, and a chip that
// returns 933 unnamed species is not a filter.
const FALLBACK_CATEGORIES = [
  'Legume', 'Timber', 'Fruit', 'Vegetable', 'Spice', 'Ornamental', 'Fodder',
  'Herb', 'Industrial', 'Grain', 'Medicinal', 'Fibre', 'Beverage', 'Nut',
  'Staple', 'Oilseed',
]

const CONFIDENCE_LABEL = {
  high: 'strong evidence',
  medium: 'partial evidence',
  low: 'weak evidence',
}

// A grower opening this card wants something they can eat or sell as food, but
// the catalogue is every species ECOCROP can score. Left unfiltered, the list is
// topped by plants that fit the climate beautifully and are not dinner: myrtle
// scored 99 for Johannesburg, ahead of potato at 98. So "Food" is the view the
// card opens on, and "All" plus the per-category chips are one click away.
//
// Beverage is included because tea and coffee are cash crops a smallholder grows
// on purpose. Medicinal, ornamental, timber, fibre, fodder and industrial are not:
// they are legitimately in the catalogue, they are just not what someone means
// when they ask what to plant in the back bed.
const FOOD_CATEGORIES = [
  'Vegetable', 'Fruit', 'Grain', 'Legume', 'Herb',
  'Spice', 'Staple', 'Nut', 'Oilseed', 'Beverage',
]
const FOOD_FILTER = FOOD_CATEGORIES.join(',')

const SEARCH_DEBOUNCE_MS = 350

function ScoreBadge({ score }) {
  const level = score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low'
  return <span className={`crop-score crop-score-${level}`}>{score}</span>
}

export default function CropRecommendations({ fieldProfile }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [category, setCategory] = useState(FOOD_FILTER)
  const [includeAll, setIncludeAll] = useState(false)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')

  const latitude = fieldProfile?.location?.latitude
  const longitude = fieldProfile?.location?.longitude

  // Debounce so a five-letter plant name is one request, not five.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (latitude === null || latitude === undefined || longitude === null || longitude === undefined) {
      setData(null)
      return undefined
    }

    let cancelled = false
    const controller = new AbortController()

    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const response = await api.crops(latitude, longitude, {
          limit: 12,
          category,
          includeAll,
          q: query || undefined,
          signal: controller.signal,
        })
        if (!cancelled) setData(response)
      } catch (apiError) {
        if (apiError?.name === 'AbortError') return
        if (!cancelled) {
          setError(apiError.message)
          setData(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [latitude, longitude, category, includeAll, query])

  const chips = useMemo(() => {
    const counts = data?.catalogue?.categories
    if (!counts) return FALLBACK_CATEGORIES.map((name) => ({ name, count: null }))
    return Object.entries(counts)
      .filter(([name]) => name !== 'Other')
      .map(([name, count]) => ({ name, count }))
  }, [data])

  // The Food chip sums its categories out of the catalogue, measured exactly the
  // way every other chip is. It is deliberately not the number of results: the
  // "N of 2,066 species" counter above reports how many were actually scored for
  // this field, which is smaller because species with no common name are left out
  // until the toggle below is switched on.
  const foodCount = useMemo(() => {
    const counts = data?.catalogue?.categories
    if (!counts) return null
    const total = FOOD_CATEGORIES.reduce((sum, name) => sum + (counts[name] || 0), 0)
    return total || null
  }, [data])

  if (latitude === null || latitude === undefined) return null

  const crops = data?.crops || []
  const catalogue = data?.catalogue
  const context = data?.context
  const searching = query.length > 0

  const handleSearch = (event) => {
    const value = event.target.value
    setSearch(value)
    // A category filter and a name search fight each other: typing a plant name
    // and being told nothing matched because a stale chip says "Fruit" is the
    // kind of silent dead end this rewrite exists to remove.
    if (value.trim()) setCategory(null)
  }

  return (
    <div className="container">
      <div className="crop-recs card">
        <div className="card-label">
          <span><Icon name="leaf" size={18} /> {searching ? 'CROP SEARCH' : 'RECOMMENDED CROPS'}</span>
          {catalogue && (
            <span className="source-label">
              {searching
                ? `${catalogue.species_scored} MATCH${catalogue.species_scored === 1 ? '' : 'ES'} OF ${catalogue.species_available} SPECIES`
                : `${catalogue.species_scored} OF ${catalogue.species_available} SPECIES`}
            </span>
          )}
        </div>

        <p className="crop-recs-lede">
          {searching ? (
            <>
              Matching any species ECOCROP can score, by common name, scientific
              name or botanical family.
            </>
          ) : (
            <>
              Scored against this field&apos;s own measurements
              {context ? (
                <>
                  {' — '}
                  {context.mean_temperature_c != null && `${context.mean_temperature_c} °C in ${context.month}`}
                  {context.annual_rainfall_mm != null && `, ${context.annual_rainfall_mm} mm a year`}
                  {context.soil_ph != null && `, modelled soil pH near ${context.soil_ph}`}
                  {context.soil_texture ? `, ${context.soil_texture}` : ''}
                  .
                </>
              ) : '.'}
            </>
          )}
        </p>

        {context?.missing_inputs?.length > 0 && !searching && (
          <p className="crop-context-note">
            Missing for this location: {context.missing_inputs.join(', ')}. Scores are less
            certain and say so.
          </p>
        )}

        <div className="crop-search">
          <Icon name="search" size={16} />
          <input
            type="search"
            value={search}
            onChange={handleSearch}
            placeholder="Find any plant — mango, sorrel, Acacia, Protea…"
            aria-label="Search the crop catalogue by name or family"
          />
          {search && (
            <button type="button" className="crop-search-clear" onClick={() => setSearch('')}>
              Clear
            </button>
          )}
        </div>

        <div className="crop-filters" role="group" aria-label="Filter crops by category">
          <button
            type="button"
            className={`crop-filter ${category === FOOD_FILTER ? 'active' : ''}`}
            onClick={() => setCategory(FOOD_FILTER)}
            title="Vegetables, fruit, grains, legumes, herbs, spices, staples, nuts, oilseeds and beverage crops"
          >
            Food
            {foodCount != null && <span className="crop-filter-count">{foodCount}</span>}
          </button>
          <button
            type="button"
            className={`crop-filter ${category === null ? 'active' : ''}`}
            onClick={() => setCategory(null)}
          >
            All
          </button>
          {chips.map(({ name, count }) => (
            <button
              key={name}
              type="button"
              className={`crop-filter ${category === name ? 'active' : ''}`}
              onClick={() => setCategory(category === name ? null : name)}
            >
              {name}
              {count != null && <span className="crop-filter-count">{count}</span>}
            </button>
          ))}
        </div>

        <label className="crop-catalogue-toggle">
          <input
            type="checkbox"
            checked={includeAll}
            onChange={(event) => setIncludeAll(event.target.checked)}
          />
          <span>
            Include species with no common name
            {catalogue ? ` (${catalogue.species_available} in total)` : ''}
          </span>
        </label>

        {loading && <p className="crop-loading">Comparing this field with 2,000 crop envelopes…</p>}

        {error && (
          <p className="card-error" role="alert">
            <strong>Crops unavailable.</strong> {error}
          </p>
        )}

        {!loading && !error && crops.length === 0 && (
          <p className="crop-empty">
            {searching ? (
              <>
                Nothing in the catalogue matches <strong>{query}</strong>. ECOCROP holds
                2,066 species, so try a shorter word, a genus (<em>Citrus</em>), a
                family (<em>Leguminosae</em>) or a local name (<em>morogo</em>).
              </>
            ) : (
              <>
                Nothing matched{' '}
                {category === FOOD_FILTER
                  ? 'food crops '
                  : category
                    ? `${category.toLowerCase()} crops `
                    : ''}
                with enough confidence. Try <em>All</em>, or include species with no common
                name.
              </>
            )}
          </p>
        )}

        {crops.length > 0 && (
          <p className="crop-guide-hint">
            Tap a name for its planting guide: the months that suit your field, the
            steps, and the tools you will need.
          </p>
        )}

        {crops.length > 0 && (
          <ul className="crop-list">
            {crops.map((crop) => {
              const named = crop.name !== crop.scientific_name
              return (
                <li key={`${crop.name}-${crop.scientific_name}`}>
                  <ScoreBadge score={crop.score} />
                  <div className="crop-body">
                    <Link to={`/crop/${crop.slug}`} className="crop-name-link">
                      {crop.name}
                      <Icon name="arrow" size={13} />
                    </Link>
                    {/* An unnamed species shows its family instead of repeating
                        the Latin binomial that is already the heading. */}
                    <em className="crop-latin">
                      {named ? crop.scientific_name : crop.family || 'No common name in ECOCROP'}
                    </em>
                    <span className="crop-meta">
                      {crop.category} · {CONFIDENCE_LABEL[crop.confidence] || crop.confidence}
                    </span>
                    {crop.reasons?.[0] && <span className="crop-reason">{crop.reasons[0]}</span>}
                    {crop.cautions?.[0] && (
                      <span className="crop-caution">{crop.cautions[0]}</span>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}

        {data?.source && (
          <p className="crop-source">
            {data.source.name}. {data.source.method} Score 0-100.
            {data.source.cached ? ' Cached for this field.' : ''}
          </p>
        )}
      </div>
    </div>
  )
}
