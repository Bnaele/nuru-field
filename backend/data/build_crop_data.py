"""Build backend/data/crop_reference.csv from the FAO ECOCROP archive.

Why this exists
---------------
The hackathon build shipped a hand-written crop table that nobody could trace:
`crop_reference` was seeded directly into a Supabase project and the seed script
was never committed. This script replaces it with values derived from a public,
citable source, so anyone can regenerate the file and check it.

Source
------
ECOCROP: FAO Crop Ecological Requirements Database, archived on Zenodo.
    DOI  10.5281/zenodo.13319716
    https://zenodo.org/records/13319716
    Scraped from the original FAO ECOCROP data sheets by supersistence
    (github.com/supersistence/EcoCrop-ScrapeR).

The archive is "measurements or facts" format. For each taxon it carries
optimal growth temperature, optimal annual rainfall and optimal soil pH as a
min/max pair, distinguished by statisticalMethod:

    SIO_001113 -> minimum
    SIO_001114 -> maximum

What is derived vs. what is authored
------------------------------------
- Derived (from ECOCROP): min_temp, max_temp, min_rainfall_mm, max_rainfall_mm,
  min_ph, max_ph.
- Authored here (human judgement, not agronomic data): the species-to-common-name
  mapping and the category label. Common names and groupings are labels, not
  measurements, so they are not something a dataset can supply.

Usage
-----
    python backend/data/build_crop_data.py            # regenerate the CSV
    python backend/data/build_crop_data.py --check    # verify the CSV is current

The raw archive is downloaded into a gitignored scratch directory; only the
derived CSV is committed, because the archive is 10 MB and reproducible from
its DOI in one request.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

ZENODO_ZIP = "https://zenodo.org/api/records/13319716/files/archive.zip/content"
SOURCE_NAME = "FAO ECOCROP via Zenodo 10.5281/zenodo.13319716"

HERE = Path(__file__).resolve().parent
OUT_CSV = HERE / "crop_reference.csv"
SCRATCH = HERE / ".ecocrop"
ARCHIVE = SCRATCH / "archive.zip"

# Species we surface, mapped to the name a grower would search for and a rough
# functional grouping. Grouping is presentational only.
CURATED: dict[str, tuple[str, str]] = {
    # --- grains and staples ---
    "Zea mays": ("Maize", "Grain"),
    "Triticum aestivum": ("Wheat", "Grain"),
    "Hordeum vulgare": ("Barley", "Grain"),
    "Avena sativa": ("Oats", "Grain"),
    "Secale cereale": ("Rye", "Grain"),
    "Sorghum bicolor": ("Sorghum", "Grain"),
    "Pennisetum glaucum": ("Pearl millet", "Grain"),
    "Oryza sativa": ("Rice", "Grain"),
    "Solanum tuberosum": ("Potato", "Staple"),
    "Ipomoea batatas": ("Sweet potato", "Staple"),
    "Manihot esculenta": ("Cassava", "Staple"),
    "Colocasia esculenta": ("Taro", "Staple"),
    # --- legumes ---
    "Phaseolus vulgaris": ("Dry beans", "Legume"),
    "Pisum sativum": ("Peas", "Legume"),
    "Cicer arietinum": ("Chickpea", "Legume"),
    "Lens culinaris": ("Lentil", "Legume"),
    "Arachis hypogaea": ("Groundnut", "Legume"),
    "Glycine max": ("Soybean", "Legume"),
    "Vigna unguiculata": ("Cowpea", "Legume"),
    "Vicia faba": ("Faba bean", "Legume"),
    "Medicago sativa": ("Lucerne", "Fodder"),
    # --- oil and fibre ---
    "Helianthus annuus": ("Sunflower", "Oilseed"),
    "Brassica napus": ("Canola", "Oilseed"),
    "Sesamum indicum": ("Sesame", "Oilseed"),
    "Gossypium hirsutum": ("Cotton", "Fibre"),
    "Saccharum officinarum": ("Sugarcane", "Industrial"),
    # --- vegetables ---
    "Solanum lycopersicum": ("Tomato", "Vegetable"),
    "Lycopersicon esculentum": ("Tomato", "Vegetable"),
    "Spinacia oleracea": ("Spinach", "Vegetable"),
    "Daucus carota": ("Carrot", "Vegetable"),
    "Allium cepa": ("Onion", "Vegetable"),
    "Allium sativum": ("Garlic", "Vegetable"),
    "Solanum melongena": ("Brinjal", "Vegetable"),
    "Capsicum annuum": ("Pepper", "Vegetable"),
    "Cucumis sativus": ("Cucumber", "Vegetable"),
    "Cucumis melo": ("Melon", "Vegetable"),
    "Citrullus lanatus": ("Watermelon", "Vegetable"),
    "Cucurbita maxima": ("Pumpkin", "Vegetable"),
    "Cucurbita pepo": ("Squash", "Vegetable"),
    "Lactuca sativa var. capitata": ("Lettuce", "Vegetable"),
    "Beta vulgaris": ("Beetroot", "Vegetable"),
    "Pastinaca sativa": ("Parsnip", "Vegetable"),
    "Apium graveolens var. dulce": ("Celery", "Vegetable"),
    "Abelmoschus esculentus": ("Okra", "Vegetable"),
    "Brassica oleracea var. capitata": ("Cabbage", "Vegetable"),
    "Brassica oleracea var. botrytis": ("Cauliflower", "Vegetable"),
    "Brassica oleracea var. italica": ("Broccoli", "Vegetable"),
    "Brassica chinensis": ("Pak choi", "Vegetable"),
    # --- fruit ---
    "Vitis vinifera": ("Grape", "Fruit"),
    "Citrus limon": ("Lemon", "Fruit"),
    "Citrus sinensis": ("Orange", "Fruit"),
    "Malus domestica": ("Apple", "Fruit"),
    "Pyrus communis": ("Pear", "Fruit"),
    "Prunus persica": ("Peach", "Fruit"),
    "Prunus armeniaca": ("Apricot", "Fruit"),
    "Persea americana": ("Avocado", "Fruit"),
    "Mangifera indica": ("Mango", "Fruit"),
    "Musa acuminata": ("Banana", "Fruit"),
    "Fragaria x ananassa": ("Strawberry", "Fruit"),
    "Punica granatum": ("Pomegranate", "Fruit"),
    "Psidium guajava": ("Guava", "Fruit"),
    "Ananas comosus": ("Pineapple", "Fruit"),
    "Ficus carica": ("Fig", "Fruit"),
    "Olea europaea": ("Olive", "Fruit"),
    "Passiflora edulis": ("Granadilla", "Fruit"),
    # --- beverage ---
    "Coffea arabica": ("Coffee", "Beverage"),
    "Camellia sinensis": ("Tea", "Beverage"),
}

PROPERTIES = {
    "OptimalGrowthTemperature": ("min_temp", "max_temp"),
    "optimal_rainfall": ("min_rainfall_mm", "max_rainfall_mm"),
    "OptimalGrowthpH": ("min_ph", "max_ph"),
}

FIELDS = [
    "name", "scientific_name", "category",
    "min_temp", "max_temp",
    "min_rainfall_mm", "max_rainfall_mm",
    "min_ph", "max_ph",
    "source",
]


def fetch_archive() -> Path:
    """Download the ECOCROP archive once into a gitignored scratch dir."""
    if ARCHIVE.exists() and ARCHIVE.stat().st_size > 100_000:
        return ARCHIVE
    SCRATCH.mkdir(parents=True, exist_ok=True)
    print(f"downloading {ZENODO_ZIP}", file=sys.stderr)
    with urllib.request.urlopen(ZENODO_ZIP, timeout=120) as response:
        ARCHIVE.write_bytes(response.read())
    return ARCHIVE


def read_archive(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Return (taxonID -> scientificName, measurement rows)."""
    with zipfile.ZipFile(path) as archive:
        taxa_rows = list(csv.DictReader(
            io.TextIOWrapper(archive.open("taxa.txt"), encoding="utf-8", errors="ignore"),
            delimiter="\t",
        ))
        measurements = list(csv.DictReader(
            io.TextIOWrapper(archive.open("measurementsorfacts.txt"), encoding="utf-8", errors="ignore"),
            delimiter="\t",
        ))
    taxa = {row["taxonID"]: row["scientificName"] for row in taxa_rows}
    return taxa, measurements


def build_rows(taxa: dict[str, str], measurements: list[dict[str, str]]) -> list[dict[str, str]]:
    wanted = {name: meta for name, meta in CURATED.items()}

    # taxonID -> scientificName, restricted to species we care about
    ids = {tid: name for tid, name in taxa.items() if name in wanted}

    # (taxonID, property) -> {"min": value, "max": value}
    envelopes: dict[tuple[str, str], dict[str, str]] = {}
    for row in measurements:
        tid = row.get("occurrenceID")
        if tid not in ids:
            continue
        prop = row.get("measurementType", "").rsplit("/", 1)[-1]
        if prop not in PROPERTIES:
            continue
        method = row.get("statisticalMethod", "")
        if "SIO_001113" in method:
            bound = "min"
        elif "SIO_001114" in method:
            bound = "max"
        else:
            continue
        value = (row.get("measurementValue") or "").strip()
        if not value:
            continue
        envelopes.setdefault((tid, prop), {})[bound] = value

    rows: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for tid, scientific in sorted(ids.items(), key=lambda pair: pair[1]):
        name, category = wanted[scientific]
        # Lycopersicon esculentum and Solanum lycopersicum are the same crop;
        # keep whichever the archive has complete data for, first one wins.
        if name in seen_names:
            continue

        record = {
            "name": name,
            "scientific_name": scientific,
            "category": category,
            "source": SOURCE_NAME,
        }
        complete = True
        for prop, (min_field, max_field) in PROPERTIES.items():
            bounds = envelopes.get((tid, prop), {})
            if "min" not in bounds or "max" not in bounds:
                complete = False
                break
            record[min_field] = bounds["min"]
            record[max_field] = bounds["max"]

        if not complete:
            continue

        rows.append(record)
        seen_names.add(name)

    # Report anything curated but absent, so a silent regression is impossible.
    missing = sorted(set(wanted) - {r["scientific_name"] for r in rows})
    if missing:
        print(f"warning: no complete ECOCROP record for {len(missing)} species: "
              f"{', '.join(missing)}", file=sys.stderr)

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="regenerate in memory and fail if the committed CSV differs")
    args = parser.parse_args()

    archive = fetch_archive()
    taxa, measurements = read_archive(archive)
    rows = build_rows(taxa, measurements)

    if not rows:
        print("error: no crop rows built — the archive format may have changed", file=sys.stderr)
        return 1

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    generated = buffer.getvalue()

    if args.check:
        existing = OUT_CSV.read_text(encoding="utf-8") if OUT_CSV.exists() else ""
        if existing != generated:
            print("error: crop_reference.csv is stale — run build_crop_data.py", file=sys.stderr)
            return 1
        print(f"ok: {len(rows)} crops, CSV is current")
        return 0

    OUT_CSV.write_text(generated, encoding="utf-8")
    print(f"wrote {OUT_CSV.relative_to(HERE.parent.parent)} — {len(rows)} crops from {SOURCE_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
