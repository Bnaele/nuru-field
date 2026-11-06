// FieldDashboard — the three cards at the top of /field.
//
// Rewritten against the real /api/field-profile response. The previous version
// read `fieldProfile.history.period` and `weather.temperature`, neither of which
// the API returns, so it threw on the first render after a location was picked.
//
// The old soil card showed a "SOIL MOISTURE" ring with a percentage that no
// source ever measured. There is no soil-moisture reading available here, so the
// card now shows what SoilGrids actually reports: texture class, pH and clay
// share. When SoilGrids has no prediction for a pixel it says so instead of
// inventing a number.

import Icon from './Icon'
import { CardSkeleton } from './Skeleton'

function number(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null
  return Number(value).toFixed(digits).replace(/\.0$/, '')
}

function WeatherCard({ weather }) {
  const temperature = number(weather?.temperature_c, 1)
  const wind = number(weather?.wind_kmh)
  const rainChance = number(weather?.rain_chance_pct)

  return (
    <div className="weather-card card">
      <div className="weather-top">
        <div>
          <span className="card-label-text">FIELD WEATHER</span>
          <h3>{weather?.condition || 'No reading yet'}</h3>
        </div>
        <span className="weather-icon"><Icon name="cloud" size={28} /></span>
      </div>

      <div className="weather-main">
        <strong>{temperature ?? '--'}<small>°C</small></strong>
        <span>{weather ? 'Right now, from Open-Meteo' : 'Pick a field to load the forecast'}</span>
      </div>

      <div className="weather-stats">
        <div>
          <Icon name="water" size={18} />
          <span>Rain chance<strong>{rainChance !== null ? `${rainChance}%` : '--'}</strong></span>
        </div>
        <div>
          <Icon name="wind" size={18} />
          <span>Wind<strong>{wind !== null ? `${wind} km/h` : '--'}</strong></span>
        </div>
      </div>

      <p className="weather-note">
        {number(weather?.tomorrow_rain_mm) !== null
          ? `About ${number(weather.tomorrow_rain_mm, 1)} mm of rain is forecast for tomorrow.`
          : 'No rain figure available for tomorrow yet.'}
      </p>
    </div>
  )
}

function SoilCard({ soil }) {
  const clay = number(soil?.clay_pct)
  const ph = number(soil?.ph, 1)
  const available = Boolean(soil?.available)

  return (
    <div className="soil-moisture card">
      <div className="card-label">
        <span><Icon name="water" size={18} /> TOP SOIL</span>
        <span className="source-label">{available ? 'MODELLED, 0-30 CM' : 'NO PREDICTION'}</span>
      </div>

      {available ? (
        <>
          <div className="moisture-display">
            <div
              className="moisture-ring"
              style={{ background: `conic-gradient(#96bf71 0 ${clay ?? 0}%, #dfe6d7 ${clay ?? 0}%)` }}
            >
              <strong>{clay ?? '--'}</strong>
              {clay !== null && <span>% clay</span>}
            </div>
            <div>
              <h3>{soil?.texture_class || 'Texture not classified'}</h3>
              <p>Modelled topsoil from ISRIC SoilGrids at 250 m resolution. Confirm with a jar test before you irrigate on it.</p>
            </div>
          </div>
          <div className="rain-history">
            <span>Soil pH</span>
            <strong>{ph !== null ? `${ph} — ${ph < 5.5 ? 'acidic' : ph > 7.5 ? 'alkaline' : 'near neutral'}` : 'not modelled here'}</strong>
          </div>
        </>
      ) : (
        <div className="soil-unavailable">
          <h3>No soil prediction for this point</h3>
          <p>
            {soil?.reason ||
              'SoilGrids covers farmland at 250 m resolution and has no value for this exact pixel, which usually means built-up or non-agricultural land.'}
          </p>
          <p className="soil-unavailable-hint">
            Move the marker a few hundred metres onto farmland, or ask your local extension
            office for a soil sample. Crop matching still works here — it just skips the soil
            signal and says so.
          </p>
        </div>
      )}
    </div>
  )
}

export default function FieldDashboard({
  fieldProfile,
  locationStatus,
  locationTone,
  locationLoading,
  onUseMyLocation,
}) {
  const showSkeleton = locationLoading && !fieldProfile
  const climate = fieldProfile?.climate
  const weather = fieldProfile?.weather

  return (
    <section className="dashboard-section" id="field">
      <div className="container section-intro">
        <div>
          <div className="eyebrow dark"><span className="eyebrow-number">01</span> Your field dashboard</div>
          <h2>Start with the ground beneath you.</h2>
        </div>
        <p>
          Nuru reads live weather, a ten-year climate normal and modelled soil for a
          coordinate, then explains every figure with its source.
        </p>
      </div>

      <div className="container field-layout">
        <div className="field-profile card">
          <div className="card-label">
            <span><Icon name="location" size={18} /> FIELD PROFILE</span>
            {fieldProfile && <span className="live-badge"><i /> LIVE</span>}
          </div>

          {showSkeleton ? (
            <CardSkeleton />
          ) : (
            <>
              <h3>{fieldProfile?.location?.label || 'Connect your location'}</h3>
              <p className="card-description">
                {fieldProfile?.summary ||
                  'We use approximate coordinates to retrieve weather, climate and soil. You choose when to share them.'}
              </p>

              <button
                className="button button-dark"
                onClick={onUseMyLocation}
                disabled={locationLoading}
              >
                {locationLoading
                  ? 'Reading your field…'
                  : <><Icon name="location" size={18} /> Use my location</>}
              </button>

              {locationStatus && (
                <p
                  className={`location-status ${locationTone === 'success' ? 'success' : ''}`}
                  role={locationTone === 'error' ? 'alert' : 'status'}
                >
                  {locationTone === 'success' && <Icon name="check" size={16} />}
                  {locationStatus}
                </p>
              )}

              {climate && (
                <div className="season-strip">
                  <div>
                    <span>SEASONAL SIGNAL</span>
                    <strong>
                      {climate.season} · {number(climate.mean_temperature_c, 1) ?? '--'} °C
                    </strong>
                  </div>
                  <p>
                    {number(climate.month_rainfall_mm) ?? '--'} mm of rain in {climate.month},
                    against {number(climate.annual_rainfall_mm) ?? '--'} mm a year.
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        <WeatherCard weather={weather} />
        <SoilCard soil={fieldProfile?.soil} />
      </div>
    </section>
  )
}
