"""Load the crop reference CSV into Supabase.

Why this exists
---------------
The hackathon build seeded `crop_reference` by hand into one Supabase project and
never committed the script, so nobody could recreate the database and nobody
could say where the numbers came from. This is the missing script.

What it loads
-------------
`backend/data/crop_reference.csv`, which is itself generated from the FAO
ECOCROP archive by `backend/data/build_crop_data.py`. The CSV is the reviewed
artefact; this script only moves it into Postgres.

Idempotent
----------
Rows are upserted on `scientific_name`, which is unique in `schema.sql`. Running
this twice updates rather than duplicates, so it is safe to re-run after
regenerating the CSV. It never deletes: a species that disappears from the CSV
stays in the table, because silently dropping rows a user may have referenced is
worse than leaving a stale one. Pass `--prune` to remove them deliberately.

Scope
-----
The API does not read this table. `backend/crops.py` scores against the CSV
directly, which keeps crop recommendations working with no database at all. The
table exists so the reference data is queryable (joins, SQL exploration, future
features) and so the schema is honestly populated rather than an empty stub.

Usage
-----
    python backend/seed.py --dry-run     # validate the CSV, touch no database
    python backend/seed.py               # upsert into the configured Supabase

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in backend/.env. The service key
bypasses Row Level Security, which is required here because `crop_reference` has
no insert policy for anon or authenticated users.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "data" / "crop_reference.csv"

TABLE = "crop_reference"
CONFLICT_COLUMN = "scientific_name"

# Columns written to the table, in CSV order. `id` and `created_at` are left to
# Postgres defaults so a re-run does not churn them.
COLUMNS = [
    "name",
    "scientific_name",
    "category",
    "min_temp",
    "max_temp",
    "min_rainfall_mm",
    "max_rainfall_mm",
    "min_ph",
    "max_ph",
    "source",
]

# Empty cells mean "the archive has no value", not zero. They must become NULL,
# because a 0 mm rainfall envelope would score every dryland crop as a perfect
# match.
NULLABLE = {
    "category",
    "min_rainfall_mm",
    "max_rainfall_mm",
    "min_ph",
    "max_ph",
    "source",
}


class SeedError(Exception):
    """A problem with the CSV that should stop the run before any write."""


def _number(raw: str, *, column: str, row_number: int, required: bool) -> float | None:
    text = (raw or "").strip()
    if not text:
        if required:
            raise SeedError(f"row {row_number}: {column} is empty, but the schema requires it")
        return None
    try:
        return float(text)
    except ValueError as error:
        raise SeedError(f"row {row_number}: {column} is not a number ({raw!r})") from error


def read_rows(path: Path = CSV_PATH) -> list[dict]:
    """Parse and validate the CSV into insert-ready dicts."""
    if not path.exists():
        raise SeedError(
            f"{path} is missing. Regenerate it with: python backend/data/build_crop_data.py"
        )

    rows: list[dict] = []
    seen: dict[str, int] = {}

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise SeedError(
                f"{path.name} is missing column(s): {', '.join(missing)}. "
                "The CSV layout and COLUMNS here must stay in step."
            )

        for row_number, raw in enumerate(reader, start=2):  # 2 = first data row
            scientific_name = (raw.get("scientific_name") or "").strip()
            name = (raw.get("name") or "").strip()

            if not scientific_name:
                raise SeedError(f"row {row_number}: scientific_name is empty")
            if not name:
                raise SeedError(f"row {row_number}: name is empty ({scientific_name})")

            # The upsert's ON CONFLICT target must be unique within one batch.
            # Postgres rejects a statement that hits the same key twice, so catch
            # it here with the row numbers instead of surfacing a driver error.
            if scientific_name in seen:
                raise SeedError(
                    f"row {row_number}: duplicate scientific_name {scientific_name!r} "
                    f"(already on row {seen[scientific_name]})"
                )
            seen[scientific_name] = row_number

            min_temp = _number(raw.get("min_temp"), column="min_temp", row_number=row_number, required=True)
            max_temp = _number(raw.get("max_temp"), column="max_temp", row_number=row_number, required=True)
            if min_temp > max_temp:
                raise SeedError(
                    f"row {row_number}: min_temp {min_temp} exceeds max_temp {max_temp} "
                    f"for {scientific_name}"
                )

            record: dict = {
                "name": name,
                "scientific_name": scientific_name,
                "min_temp": min_temp,
                "max_temp": max_temp,
            }
            for column in NULLABLE:
                record[column] = (raw.get(column) or "").strip() or None

            for column in ("min_rainfall_mm", "max_rainfall_mm", "min_ph", "max_ph"):
                record[column] = _number(
                    raw.get(column),
                    column=column,
                    row_number=row_number,
                    required=False,
                )

            rows.append({column: record[column] for column in COLUMNS})

    if not rows:
        raise SeedError(f"{path.name} has a header but no data rows")

    return rows


def seed(rows: list[dict], *, batch_size: int = 500, prune: bool = False) -> int:
    """Upsert `rows` in batches. Returns the number of rows written."""
    # Imported here so `--dry-run` works without the Supabase client installed.
    import db

    client = db.get_supabase()
    written = 0

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        client.table(TABLE).upsert(batch, on_conflict=CONFLICT_COLUMN).execute()
        written += len(batch)
        print(f"  upserted {written}/{len(rows)}", flush=True)

    if prune:
        # Deliberate, opt-in only. PostgREST cannot express "not in a list of
        # 2,000 values" in a URL, so this reads the existing keys back and
        # deletes the difference.
        existing = client.table(TABLE).select(CONFLICT_COLUMN).execute().data or []
        keep = {row[CONFLICT_COLUMN] for row in rows}
        stale = [row[CONFLICT_COLUMN] for row in existing if row[CONFLICT_COLUMN] not in keep]
        for index in range(0, len(stale), batch_size):
            client.table(TABLE).delete().in_(CONFLICT_COLUMN, stale[index : index + batch_size]).execute()
        print(f"  pruned {len(stale)} row(s) no longer in the CSV", flush=True)

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load backend/data/crop_reference.csv into the crop_reference table."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and validate the CSV, then stop without connecting to a database",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="rows per upsert request (default 500, keeps request bodies small)",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="also delete rows whose scientific_name is no longer in the CSV",
    )
    args = parser.parse_args(argv)

    try:
        rows = read_rows()
    except SeedError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    named = sum(1 for row in rows if row["name"] != row["scientific_name"])
    print(f"parsed {len(rows)} crops from {CSV_PATH.name} ({named} with a common name)")

    if args.dry_run:
        print("dry run: no database connection attempted")
        return 0

    try:
        written = seed(rows, batch_size=args.batch_size, prune=args.prune)
    except SeedError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # HTTPException from db.get_supabase, or a driver error
        print(f"error: {error}", file=sys.stderr)
        print(
            "hint: check SUPABASE_URL and SUPABASE_SERVICE_KEY in backend/.env, and make "
            "sure schema.sql has been applied to that project.",
            file=sys.stderr,
        )
        return 1

    print(f"done: {written} row(s) upserted into {TABLE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
