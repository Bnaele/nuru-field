// MarketSnapshot — fresh produce prices from the Joburg Market daily sheet.
//
// Rewritten. The old version called /api/market-snapshot, an endpoint that no
// longer exists, and expected rows shaped `{ crop_name, demand_level }` from a
// seeded table. The real sheet gives a commodity name, a realised price per
// kilogram, kilograms sold, and the date it applies to.
//
// The "demand" column is gone on purpose. The sheet reports what traded, not
// whether demand is high, and inventing a label from it would be guesswork.

import { useEffect, useRef, useState } from 'react'
import Icon from './Icon'
import { api } from '../lib/api'

function kilograms(value) {
  if (value === null || value === undefined) return null
  const tonnes = Number(value) / 1000
  if (!Number.isFinite(tonnes)) return null
  return tonnes >= 1 ? `${tonnes.toFixed(1)} t` : `${Math.round(Number(value))} kg`
}

export default function MarketSnapshot({ location }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [includeUnsold, setIncludeUnsold] = useState(false)

  // The field's coordinates, when one has been picked. They do not filter the
  // sheet — every market's prices are Johannesburg's — they let the card name
  // the market that is actually nearest.
  const latitude = Number.isFinite(location?.latitude) ? location.latitude : undefined
  const longitude = Number.isFinite(location?.longitude) ? location.longitude : undefined

  // Debounce so typing "tomato" is one request, not six.
  const debounceRef = useRef(null)
  const [debouncedQuery, setDebouncedQuery] = useState('')

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setDebouncedQuery(query.trim()), 350)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query])

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const response = await api.marketPrices({
          q: debouncedQuery || undefined,
          limit: 24,
          includeUnsold,
          latitude,
          longitude,
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
  }, [debouncedQuery, includeUnsold, latitude, longitude])

  const rows = data?.rows || []

  return (
    <div className="container">
      <div className="market-card card">
        <div className="card-label">
          <span><Icon name="leaf" size={18} /> MARKET PRICES</span>
          {data?.as_of_label && <span className="source-label">AS OF {data.as_of_label.toUpperCase()}</span>}
        </div>

        <p className="market-lede">
          What fresh produce actually sold for at {data?.market || 'Joburg Market'} on{' '}
          {data?.as_of_label || 'the latest trading day'}. Prices are the day&apos;s total
          value divided by kilograms sold — realised averages, not asking prices.
        </p>

        {/* One market's sheet was being read as if it were local. Name the scope
            before the numbers, not after them. */}
        {data?.source?.scope && (
          <p className="market-scope">
            <Icon name="location" size={15} />
            <span>{data.source.scope}</span>
          </p>
        )}

        <div className="market-controls">
          <label className="market-search">
            <Icon name="search" size={15} />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search a commodity, e.g. tomato"
              aria-label="Search market prices"
            />
          </label>
          <label className="market-toggle">
            <input
              type="checkbox"
              checked={includeUnsold}
              onChange={(event) => setIncludeUnsold(event.target.checked)}
            />
            Include produce that did not trade
          </label>
        </div>

        {loading && <p className="market-loading">Reading the Joburg Market sheet…</p>}

        {/* The sheet is a daily snapshot, so an older one is still genuinely
            useful. Say which day it is instead of leaving the card empty. */}
        {!loading && data?.stale && data?.stale_note && (
          <p className="market-stale" role="status">{data.stale_note}</p>
        )}

        {error && (
          <p className="card-error" role="alert">
            <strong>Prices unavailable.</strong> {error}
          </p>
        )}

        {!loading && !error && rows.length === 0 && (
          <p className="market-empty">
            {debouncedQuery
              ? `Nothing on today's sheet matches "${debouncedQuery}".`
              : 'No traded prices on the sheet today. Try including produce that did not trade.'}
          </p>
        )}

        {rows.length > 0 && (
          <table className="market-table">
            <thead>
              <tr>
                <th>Commodity</th>
                <th>R / kg</th>
                <th>Sold</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.commodity}>
                  <td>{row.commodity}</td>
                  <td>
                    {row.price_per_kg !== null
                      ? `R${Number(row.price_per_kg).toFixed(2)}`
                      : <span className="market-untraded">did not trade</span>}
                  </td>
                  <td>{kilograms(row.total_kg_sold) || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {data && (
          <p className="market-source">
            {data.market || 'Joburg Market'} · {data.listed_count} commodities listed,{' '}
            {data.traded_count} traded.
            {data.source_url && (
              <> <a href={data.source_url} target="_blank" rel="noreferrer">Source sheet</a></>
            )}
          </p>
        )}
      </div>
    </div>
  )
}
