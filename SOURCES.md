# Data sources

Every figure the app shows comes from one of the sources below, and every API
response carries a `source` block naming which one and where it came from.

No figure in this repository is invented. Where a source cannot answer for a
coordinate — SoilGrids over a built-up area, for example — the API says so and
returns `null`, rather than filling the gap with a plausible-looking number.

| Data | Source | Key required | Refresh | Licence / terms |
| --- | --- | --- | --- | --- |
| Live weather, forecast | [Open-Meteo](https://open-meteo.com/) | No | 30 min cache | CC BY 4.0, free tier is non-commercial |
| Climate normals (10 yr) | [Open-Meteo Archive](https://open-meteo.com/en/docs/historical-weather-api) | No | 7 day cache | CC BY 4.0, free tier is non-commercial |
| Soil properties | [ISRIC SoilGrids 2.0](https://rest.isric.org/soilgrids/v2.0/docs) | No | 30 day cache | CC BY 4.0 |
| Administrative region | [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/) | No | 30 day cache | ODbL, 1 req/sec, identifying User-Agent |
| Produce prices | [Joburg Market](https://joburgmarket.co.za/daily-price-list/) | No | 1 hour cache | Public daily sheet, published for information |
| Crop envelopes | [FAO ECOCROP](https://zenodo.org/records/13319716) | No | Vendored CSV | See below |

---

## Open-Meteo

`https://api.open-meteo.com/v1/forecast` and
`https://archive-api.open-meteo.com/v1/archive`

Free and keyless. The free tier is for **non-commercial use** up to 10,000 calls
a day; this project is a prototype and stays inside that. **If the app ever
earns revenue, this licence must be revisited** — either a paid Open-Meteo plan
or a different provider.

Attribution ("Weather data by Open-Meteo.com") is required by CC BY 4.0 and is
returned in every weather payload and rendered in the UI footer.

This replaced WeatherAPI, which was a paid endpoint for the 10-year history the
app needs, so on a free key the seasonal signal silently failed.

## ISRIC SoilGrids 2.0

`https://rest.isric.org/soilgrids/v2.0/properties/query`

250 m resolution modelled soil, not a laboratory test. Values are reported as
scaled integers: clay/sand/silt and organic carbon are tenths of a percent,
`phh2o` is pH × 10, nitrogen is hundredths of a gram per kilogram. The source
module converts them and the UI says "modelled estimate" wherever it shows them.

Important behaviour: SoilGrids answers **HTTP 200 with null values** for pixels
it has no prediction for, typically built-up areas. The API surfaces that as
`available: false` with a suggestion to move the pin onto open ground, because
silently returning nothing looks like a bug to a grower.

## OpenStreetMap Nominatim

`https://nominatim.openstreetmap.org/reverse`

Usage policy, enforced in `backend/sources/nominatim.py`: maximum one request
per second, a User-Agent that identifies the application, and caching of
results. Region names are cached for 30 days because administrative names do not
move.

The nine hardcoded South African provincial bounding boxes in `backend/geo.py`
are an **offline fallback only**, used when Nominatim is unreachable. A result
from them is flagged `approximate: true` and the UI says so.

## Joburg Market

`https://joburgmarket.co.za/jhb-market/dailyprices.php`

The daily price sheet, published between 12:00 and 13:00 on weekdays. It is
HTML, not a PDF — the public page embeds this table in an iframe, and the parser
targets the inner URL directly.

Two quantity columns are published and they are not interchangeable:

- **Total Qty Sold** — units (pockets, boxes, crates), and the unit varies by
  commodity, so it cannot be divided into money.
- **Total Kg Sold** — kilograms.

Price per kilogram is therefore `total value / total kg sold`. The sheet also
carries an `MTD:` running monthly figure that this parser drops, because one row
per commodity per day is what the table stores.

Every stored price keeps the sheet's own as-of date and its source URL. Nothing
in the API implies these are live ticks: they are what traded on the day the
sheet reports. Commodities that were listed but did not trade keep a `null`
price rather than zero, because "did not sell" is not "sold for nothing".

If the sheet becomes unparseable the parser raises, and the API reports prices
as unavailable. It never falls back to stale data presented as current.

## FAO ECOCROP (crop envelopes)

**DOI:** [10.5281/zenodo.13319716](https://zenodo.org/records/13319716) —
*ECOCROP: FAO Crop Ecological Requirements Database*, archived by
[supersistence](https://github.com/supersistence/EcoCrop-ScrapeR).

The original FAO ECOCROP site is offline, so this Zenodo archive is the citable
copy. `backend/data/build_crop_data.py` downloads it and derives
`backend/data/crop_reference.csv`.

What is **derived from ECOCROP** — for each crop, the optimal window for growth
temperature, annual rainfall and soil pH, taken from the archive's
`measurements or facts` rows paired by `statisticalMethod`
(`SIO_001113` = minimum, `SIO_001114` = maximum):

- `min_temp`, `max_temp`
- `min_rainfall_mm`, `max_rainfall_mm`
- `min_ph`, `max_ph`

What is **authored in this repository, not from ECOCROP**:

- The species → common name mapping (66 species).
- The category label (Grain, Legume, Vegetable, …).
- The soil-texture adjustment in `backend/crops.py`. ECOCROP carries no texture
  envelope, so scoring one against a fabricated threshold would be dishonest.
  Texture instead makes a small capped adjustment for crops with a well-known
  sensitivity, and every crop that receives one gets a `cautions` line saying it
  is general agronomy guidance rather than a measured threshold.

Regenerate the CSV with:

```bash
cd backend
python data/build_crop_data.py           # rewrite crop_reference.csv
python data/build_crop_data.py --check   # fail if the CSV is stale
```

Only the derived CSV is committed. The 10 MB archive is downloaded into a
gitignored scratch directory, because it is reproducible from its DOI in one
request.
