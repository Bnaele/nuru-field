// CropPage — one species, in full.
//
// The recommendation card answers "what could I plant". This page answers the
// question a grower asks straight after: when do I plant it here, what do I do,
// and what do I need. It is fetched from /api/crops/{slug}, which carries the
// crop's ECOCROP windows, this field's fit, the planting months computed from
// the field's own monthly normals, and the steps and tools.
//
// The provenance line at the bottom is not decoration. The windows are measured
// data, the months are arithmetic on this field, and the steps are general
// practice for the crop group — the page says which is which, because a grower
// deciding what to spend money on deserves to know.
//
// The page renders without a field too. A bookmarked link or a reload before the
// field profile arrives still gets the windows, the steps and the tools; only
// the months are withheld, and the page says so instead of inventing a season.

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Icon from '../components/Icon'
import { api } from '../lib/api'

const CONFIDENCE_LABEL = {
  high: 'strong evidence',
  medium: 'partial evidence',
  low: 'weak evidence',
}

const MONTH_STATUS_LABEL = {
  'in-window': 'inside its temperature window',
  close: 'close to its temperature window',
  outside: 'outside its temperature window',
  frost: 'frost risk',
  unknown: 'no temperature data',
}

function formatRange(window, unit = '') {
  if (!window) return 'Not carried by ECOCROP'
  const suffix = unit ? ` ${unit}` : ''
  return `${window[0]}–${window[1]}${suffix}`
}

function markFor(section) {
  return `/market?kind=input&category=${section}`
}

function ScoreBadge({ score }) {
  const level = score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low'
  return <span className={`crop-score crop-score-${level}`}>{score}</span>
}

export default function CropPage({ fieldProfile }) {
  const { slug } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [missing, setMissing] = useState(false)

  const latitude = fieldProfile?.location?.latitude
  const longitude = fieldProfile?.location?.longitude
  const hasField = latitude !== null && latitude !== undefined && longitude !== null && longitude !== undefined

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    setLoading(true)
    setError('')
    setMissing(false)

    api
      .crop(slug, latitude, longitude, { signal: controller.signal })
      .then((payload) => {
        if (!cancelled) setData(payload)
      })
      .catch((failure) => {
        if (failure.name === 'AbortError') return
        if (cancelled) return
        if (failure.status === 404) {
          setMissing(true)
          setData(null)
        } else {
          setError(failure.message)
          setData(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [slug, latitude, longitude])

  const back = (
    <Link to="/field" className="market-link-quiet crop-back">
      <Icon name="arrow" size={15} /> Back to your field
    </Link>
  )

  if (missing) {
    return (
      <main className="crop-page">
        <div className="container">
          {back}
          <div className="card crop-missing">
            <h1>That plant is not in the catalogue</h1>
            <p>
              Nothing matches <strong>{slug}</strong>. The catalogue holds 2,066 species;
              search it by common name, scientific name or family from your field page.
            </p>
            <Link to="/field" className="button button-primary">Search the catalogue</Link>
          </div>
        </div>
      </main>
    )
  }

  if (loading && !data) {
    return (
      <main className="crop-page">
        <div className="container">
          {back}
          <p className="crop-loading" role="status">Reading the catalogue and this field&apos;s climate…</p>
        </div>
      </main>
    )
  }

  if (error) {
    return (
      <main className="crop-page">
        <div className="container">
          {back}
          <p className="card-error" role="alert">
            <strong>This crop page is unavailable.</strong> {error}
          </p>
        </div>
      </main>
    )
  }

  if (!data) return null

  const { crop, fit, season, guide, context, source } = data
  const toolLabel = Object.fromEntries(guide.tools.map((tool) => [tool.key, tool.label]))
  const bestMonths = new Set(
    (season.windows?.length ? season.windows : season.closest ? [season.closest] : [])
      .flatMap((window) => window.months),
  )

  return (
    <main className="crop-page">
      <div className="container">
        {back}

        <header className="crop-head">
          <div>
            <p className="market-kicker">Crop guide</p>
            <h1>{crop.name}</h1>
            <p className="crop-head-latin">
              <em>{crop.scientific_name}</em>
              {crop.has_common_name && crop.family ? ` · ${crop.family}` : ''} · {crop.category}
            </p>
          </div>
          {fit && (
            <div className="crop-head-score">
              <ScoreBadge score={fit.score} />
              <div>
                <strong>{CONFIDENCE_LABEL[fit.confidence] || fit.confidence}</strong>
                <span>{fit.growing_season}</span>
              </div>
            </div>
          )}
        </header>

        <section className="crop-facts" aria-label="What this crop needs">
          <div>
            <span>Temperature</span>
            <strong>{formatRange(crop.temperature_c, '°C')}</strong>
          </div>
          <div>
            <span>Rainfall a year</span>
            <strong>{formatRange(crop.rainfall_mm_per_year, 'mm')}</strong>
          </div>
          <div>
            <span>Soil pH</span>
            <strong>{formatRange(crop.soil_ph)}</strong>
          </div>
          <div>
            <span>Group</span>
            <strong>{guide.group_label}</strong>
          </div>
        </section>

        <div className="crop-columns">
          <section className="card crop-season">
            <div className="card-label">
              <span><Icon name="spark" size={18} /> BEST TIME TO PLANT</span>
              {season.available && season.best_start && (
                <span className="source-label">START IN {season.best_start.toUpperCase()}</span>
              )}
            </div>

            <p className="crop-season-summary">
              {season.available
                ? season.summary
                : hasField
                  ? season.note
                  : 'Load your field to see which months suit this crop where you are. The windows and the steps below still apply.'}
            </p>

            {season.available && season.months.length > 0 && (
              <>
                <div className="crop-months" role="list" aria-label="Monthly climate normals for this field">
                  {season.months.map((month) => {
                    const chosen = bestMonths.has(month.month)
                    return (
                      <div
                        key={month.month}
                        role="listitem"
                        className={`crop-month crop-month-${month.status}${chosen ? ' chosen' : ''}`}
                        title={`${month.name}: ${month.mean_temp_c ?? '–'} °C mean, ${month.rainfall_mm ?? '–'} mm rain, ${MONTH_STATUS_LABEL[month.status] || month.status}`}
                      >
                        <span className="crop-month-name">{month.name.slice(0, 1)}</span>
                        <strong>{month.mean_temp_c === null ? '–' : Math.round(month.mean_temp_c)}</strong>
                        <span className="crop-month-rain">{month.rainfall_mm === null ? '–' : month.rainfall_mm}</span>
                      </div>
                    )
                  })}
                </div>
                <p className="crop-month-key">
                  Month, mean °C, rain mm. Green months sit inside its window; olive ones
                  are close; the outline marks where to start planting.
                </p>
              </>
            )}

            {season.available && season.closest && (
              <p className="crop-context-note">
                No month reaches {formatRange(crop.temperature_c, '°C')} on this field.
                The warmest run is {season.closest.label}, still about{' '}
                {season.closest.short_by_c} °C short.
              </p>
            )}

            {season.field?.annual_rainfall_mm != null && (
              <p className="crop-season-field">
                This field averages {season.field.annual_rainfall_mm} mm of rain a year
                {season.field.years_used ? ` over ${season.field.years_used} years` : ''}
                {context?.soil_texture ? `, on ${context.soil_texture}` : ''}.
              </p>
            )}
          </section>

          <section className="card crop-fit">
            <div className="card-label">
              <span><Icon name="pulse" size={18} /> FIT FOR THIS FIELD</span>
              {fit && <span className="source-label">{fit.score} / 100</span>}
            </div>

            {!fit ? (
              <p className="crop-fit-empty">
                {hasField
                  ? 'The score for this field is unavailable right now.'
                  : 'Set your field and this panel scores the crop against your own temperature, rainfall and soil pH.'}
              </p>
            ) : (
              <>
                <ul className="crop-reasons">
                  {fit.reasons.map((reason) => (
                    <li key={reason} className="crop-reason"><Icon name="check" size={14} />{reason}</li>
                  ))}
                </ul>
                <ul className="crop-reasons">
                  {fit.cautions.map((caution) => (
                    <li key={caution} className="crop-caution">{caution}</li>
                  ))}
                </ul>
                {context && (
                  <p className="crop-fit-context">
                    Measured here: {context.mean_temperature_c ?? '–'} °C in {context.month},{' '}
                    {context.annual_rainfall_mm ?? '–'} mm a year
                    {context.soil_ph != null ? `, soil pH ${context.soil_ph}` : ', soil pH unavailable'}.
                  </p>
                )}
              </>
            )}
          </section>
        </div>

        <section className="card crop-steps-card">
          <div className="card-label">
            <span><Icon name="leaf" size={18} /> HOW TO PLANT IT</span>
            <span className="source-label">{guide.group_label}</span>
          </div>

          <p className="crop-steps-lede">
            General practice for this group of crops. The numbers in the seasons panel
            are measured; the spacing, seed depth and days to harvest are on the packet,
            because Nuru&apos;s catalogue does not carry them.
          </p>

          <ol className="crop-steps">
            {guide.steps.map((step) => (
              <li key={step.n}>
                <span className="crop-step-n" aria-hidden="true">{step.n}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.detail}</p>
                  {step.tools.length > 0 && (
                    <p className="crop-step-tools">
                      Needs: {step.tools.map((key) => toolLabel[key]).filter(Boolean).join(', ')}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>

        <div className="crop-columns">
          <section className="card crop-tools-card">
            <div className="card-label">
              <span><Icon name="spark" size={18} /> TOOLS YOU WILL NEED</span>
              <span className="source-label">{guide.tools.length} ITEMS</span>
            </div>
            <ul className="crop-tool-list">
              {guide.tools.map((tool) => (
                <li key={tool.key}>
                  <div>
                    <strong>{tool.label}</strong>
                    <span>{tool.why}</span>
                  </div>
                  <Link to={markFor(tool.market)} className="crop-market-link">
                    {tool.market_label}
                  </Link>
                </li>
              ))}
            </ul>
          </section>

          <section className="card crop-needs-card">
            <div className="card-label">
              <span><Icon name="cloud" size={18} /> WHAT TO BUY FOR THIS ONE</span>
            </div>
            <ul className="crop-need-list">
              {guide.needs.map((need) => (
                <li key={need.section}>
                  <Link to={markFor(need.section)} className="crop-need-link">
                    <strong>{need.label}</strong>
                    <Icon name="arrow" size={14} />
                  </Link>
                  <span>{need.why}</span>
                </li>
              ))}
            </ul>

            {guide.watch.length > 0 && (
              <div className="crop-watch">
                <span>Watch out for</span>
                <ul>
                  {guide.watch.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        </div>

        <p className="crop-provenance">
          {source.numbers}. {source.climate ? `${source.climate}. ` : ''}
          {source.method}
          {source.cached ? ' Cached for this field.' : ''}
        </p>
      </div>
    </main>
  )
}
