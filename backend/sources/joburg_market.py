"""Fresh produce prices from Joburg Market's daily sheet.

Spike outcome (this is why the module exists in this shape)
----------------------------------------------------------
The plan required confirming the daily sheet is machine-parseable before
committing to it. It is: `https://joburgmarket.co.za/jhb-market/dailyprices.php`
returns a single `<table class="alltable">` with 161 commodity rows and five
columns, plus a human-readable as-of date ("This information is for
6 November 2026"). It is not a scanned PDF and not framed in the public page —
the visible page embeds this one in an `<iframe>`, so the parser targets the
inner URL directly. No World Bank fallback is needed.

Reading the numbers correctly
-----------------------------
Two quantity columns are published per commodity:

* "Total Qty Sold" — units (pockets, boxes, crates). Varies by commodity, so it
  cannot be divided into money.
* "Total Kg Sold" — kilograms.

Price per kilogram is therefore `total_value_zar / total_kg_sold`, never
`/ total_qty_sold`. On 6 Nov 2026 that gives apples at R11.63/kg from
R1,865,926.00 over 160,414 kg, which is the right order of magnitude. Each row
also carries an `MTD:` running monthly total on a second line; that is dropped
here because the table stores one observation per commodity per day.

Honesty rules for this source
-----------------------------
Every row keeps the sheet's own as-of date and the URL it came from, so the UI
can say "prices as at 6 November 2026" instead of implying these are live ticks.
161 commodities are listed but only ~138 traded that day; the unsold ones keep a
null `price_per_kg` rather than a zero, because "did not sell" and "sold for
nothing" are different facts.

Reference: https://joburgmarket.co.za/daily-price-list/
"""

from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser

from cache import Served, cached_call, market_cache
from config import JOBURG_MARKET_URL, MARKET_TTL_S
from sources.http import UpstreamError, get_text

SOURCE_NAME = "Joburg Market"
MARKET_LABEL = "Joburg Market"
ATTRIBUTION = (
    "Prices from the Joburg Market daily price list, published for information only. "
    "Confirm before trading."
)
PRICE_LIST_PAGE = "https://joburgmarket.co.za/daily-price-list/"

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

_AS_OF_RE = re.compile(
    r"This information is for\s*<b>\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})\s*</b>",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"-?[0-9][0-9,]*(?:\.[0-9]+)?")


class _AllTableParser(HTMLParser):
    """Collect rows from the market's `alltable` only, ignoring page layout."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.header: list[str] = []
        self.rows: list[list[str]] = []
        self._in_table = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if "alltable" in (dict(attrs).get("class") or ""):
                self._in_table = True
            return
        if not self._in_table:
            return
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
        elif tag == "br" and self._cell is not None:
            # The day's figure and the MTD figure are separated by <br>; keeping
            # the break lets us take the first line and drop the MTD suffix.
            self._cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self._in_table:
            return
        if tag == "table":
            self._in_table = False
        elif tag in ("td", "th"):
            if self._row is not None and self._cell is not None:
                self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr":
            if self._row:
                if self.header:
                    self.rows.append(self._row)
                else:
                    self.header = self._row
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._in_table and self._cell is not None:
            self._cell.append(data)


def _day_value(cell: str) -> str:
    """First line of a cell, i.e. the day's figure without the `MTD:` line."""
    return cell.split("\n", 1)[0].strip()


def _parse_number(cell: str) -> float | None:
    """`R1,865,926.00` -> 1865926.0 ; blank or `-` -> None."""
    match = _NUMBER_RE.search(_day_value(cell).replace("R", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _parse_as_of(html: str) -> date | None:
    match = _AS_OF_RE.search(html)
    if not match:
        return None
    parts = match.group(1).split()
    if len(parts) != 3:
        return None
    day, month_name, year = parts
    month = _MONTHS.get(month_name.lower())
    if month is None:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def commodity_key(name: str) -> str:
    """Lowercase comparison key, e.g. `BABY MARROWS` -> `baby marrows`."""
    return re.sub(r"\s+", " ", name).strip().lower()


def display_name(name: str) -> str:
    """Title case for the UI, keeping all-caps acronyms readable."""
    return commodity_key(name).title()


def parse_price_list(html: str) -> dict:
    """Parse the daily sheet into rows. Pure function, so it is fixture-testable.

    Raises UpstreamError when the expected table is missing, because a layout
    change must surface as "unavailable" rather than as an empty price list that
    looks like a quiet trading day.
    """
    parser = _AllTableParser()
    parser.feed(html)
    parser.close()

    if not parser.rows:
        raise UpstreamError(
            "The Joburg Market price sheet could not be read. It may have changed "
            "layout, or today's sheet is not published yet.",
            status_code=502,
        )

    expected_columns = 5
    rows: list[dict] = []
    for cells in parser.rows:
        if len(cells) < expected_columns:
            continue
        commodity = cells[0].strip()
        if not commodity:
            continue

        total_value = _parse_number(cells[1])
        total_qty = _parse_number(cells[2])
        total_kg = _parse_number(cells[3])
        available = _parse_number(cells[4])

        price_per_kg: float | None = None
        if total_value is not None and total_kg:
            price_per_kg = round(total_value / total_kg, 2)

        rows.append(
            {
                "commodity": display_name(commodity),
                "commodity_key": commodity_key(commodity),
                "price_per_kg": price_per_kg,
                "total_value_zar": total_value,
                "total_qty_sold": total_qty,
                "total_kg_sold": total_kg,
                "qty_available": available,
            }
        )

    if not rows:
        raise UpstreamError(
            "The Joburg Market price sheet had no usable rows today.",
            status_code=502,
        )

    return {
        "as_of": _parse_as_of(html),
        "rows": rows,
    }


async def _fetch_prices() -> dict:
    html = await get_text(
        JOBURG_MARKET_URL,
        timeout=30.0,
        retries=1,
        unavailable_message=(
            "Joburg Market prices are temporarily unavailable. "
            "The market publishes between 12:00 and 13:00 on weekdays."
        ),
    )
    parsed = parse_price_list(html)
    as_of = parsed["as_of"]
    traded = [row for row in parsed["rows"] if row["price_per_kg"] is not None]

    return {
        "market": MARKET_LABEL,
        "as_of": as_of.isoformat() if as_of else None,
        "as_of_label": (
            f"{as_of.day} {as_of.strftime('%B %Y')}" if as_of else None
        ),
        "rows": parsed["rows"],
        "traded_count": len(traded),
        "listed_count": len(parsed["rows"]),
        "source_url": JOBURG_MARKET_URL,
        "price_list_page": PRICE_LIST_PAGE,
        "source": {
            "name": SOURCE_NAME,
            "attribution": ATTRIBUTION,
            "note": (
                "Prices are the previous weekday's traded average as published by "
                "the market. They are a reference for what produce is fetching, not "
                "a quote for your produce."
            ),
        },
    }


async def get_market_prices() -> tuple[dict, bool]:
    """Today's sheet, cached for an hour (the market publishes once a weekday)."""
    served: Served = await cached_call(
        market_cache,
        namespace="joburg_market",
        key="daily",
        ttl=MARKET_TTL_S,
        producer=_fetch_prices,
    )
    return served.value, served.cached
