"""One crop in full: when to plant it here, what to do, and what it needs.

ECOCROP gives three envelopes - temperature, rainfall, pH - and nothing else.
There is no planting calendar, no spacing, no tool list and no days-to-harvest
in the catalogue, and writing those per species would be exactly the invention
this project was rebuilt to remove. So the line is kept explicit:

* **Numbers** are the crop's own record, quoted from `data/crop_reference.csv`
  and attributed to FAO ECOCROP.
* **Months** are arithmetic on the grower's field. The crop's temperature window
  is compared with the field's twelve monthly normals, so "plant in October" is
  a statement about this coordinate rather than a generic calendar. Where the
  field never reaches the window, the page says so and gives the closest run
  instead of quietly pretending.
* **Steps** are general agronomy for the crop's group - a fruit plant, a
  vegetable bed, a field crop. They are labelled as general, and wherever a real
  number is missing (spacing, seed depth, days to harvest) the text says so and
  points at the seed packet.

Every tool and every need names a market section, so a step that says "you will
need a spade" is one tap from the page where spades are being sold. That is the
whole point: a guide that ends in a shopping list nobody can act on is a leaflet.
"""

from __future__ import annotations

from calendar import month_name as MONTH_NAMES

from crops import (
    ECOCROP_ATTRIBUTION,
    HEAVY_TEXTURES,
    ROOT_CROPS,
    evaluate_crop,
    field_context,
    find_by_slug,
    slugify,
)

SEASON_OF_MONTH = {
    12: "Summer", 1: "Summer", 2: "Summer",
    3: "Autumn", 4: "Autumn", 5: "Autumn",
    6: "Winter", 7: "Winter", 8: "Winter",
    9: "Spring", 10: "Spring", 11: "Spring",
}

MONTHS = tuple(MONTH_NAMES[number] for number in range(1, 13))

# A monthly mean daily minimum at or below this is a month with frost mornings: if
# the average night is already 5 °C, the coldest ones in the record are below zero.
FROST_RISK_MIN_C = 5.0

# A crop whose own window starts at or below this shrugs frost off; one that
# wants 15 °C and up does not. The line comes from its record, not from a list
# of hardy species someone would have to keep up to date.
FROST_HARDY_BELOW_C = 2.0

# How far outside its temperature window a month may sit and still be worth
# reporting as "the closest you will get here".
MARGINAL_GAP_C = 3.0

# A month carries enough rain for a crop when it delivers at least this share of
# the crop's own annual need, pro-rated over twelve months.
RAIN_SHARE_OK = 0.5

# Crops are grouped by how they are planted, not by what they are called. The
# group decides the steps, because "prepare a bed" and "dig a planting hole" are
# different instructions and the catalogue only knows the category.
GROUP_BY_CATEGORY = {
    "Fruit": "orchard",
    "Nut": "orchard",
    "Beverage": "orchard",
    "Timber": "timber",
    "Vegetable": "bed",
    "Herb": "bed",
    "Spice": "bed",
    "Medicinal": "bed",
    "Ornamental": "bed",
    "Grain": "field",
    "Legume": "field",
    "Oilseed": "field",
    "Staple": "field",
    "Fodder": "field",
    "Fibre": "field",
    "Industrial": "field",
}

GROUP_LABELS = {
    "orchard": "A perennial you plant once and pick from for years",
    "timber": "A tree crop, planted once and harvested in years, not months",
    "bed": "A garden-bed crop, grown in a prepared bed",
    "field": "A field crop, sown in rows in open ground",
    "plant": "General plant care",
}

# Categories a grower is most likely selling on, so the packing step appears
# where it applies instead of on every page.
SOLD_CATEGORIES = {
    "Fruit", "Vegetable", "Herb", "Spice", "Grain", "Legume",
    "Staple", "Oilseed", "Nut", "Beverage",
}

# Legumes fix their own nitrogen. Feeding them like a cabbage gives leaf and no
# pod, so they are the one group that does not get a fertiliser need.
SELF_FEEDING = {"Legume", "Fodder"}

TOOLS: dict[str, dict] = {
    "spade": {
        "label": "Spade",
        "why": "Digs the planting hole and turns soil to a spade's depth.",
        "market": "tools",
    },
    "fork": {
        "label": "Garden fork",
        "why": "Loosens soil and lifts roots without slicing through them.",
        "market": "tools",
    },
    "hoe": {
        "label": "Hoe",
        "why": "Clears weeds and draws the furrow a row of seed is sown into.",
        "market": "tools",
    },
    "rake": {
        "label": "Rake",
        "why": "Levels a bed and covers seed with an even layer of soil.",
        "market": "tools",
    },
    "wheelbarrow": {
        "label": "Wheelbarrow",
        "why": "Moves compost, manure and harvest crates without carrying them.",
        "market": "tools",
    },
    "trowel": {
        "label": "Hand trowel",
        "why": "Plants a seedling at the depth it grew in its bag.",
        "market": "tools",
    },
    "watering-can": {
        "label": "Watering can",
        "why": "Waters in a transplant without washing the soil off its roots.",
        "market": "irrigation",
    },
    "hose": {
        "label": "Hose or drip line",
        "why": "Gets water to the row through a dry spell with less waste.",
        "market": "irrigation",
    },
    "line": {
        "label": "Planting line and tape",
        "why": "Keeps rows straight and spacing even, so every plant gets its share.",
        "market": "tools",
    },
    "stakes": {
        "label": "Stakes and ties",
        "why": "Holds a young plant upright while its roots take hold.",
        "market": "tools",
    },
    "secateurs": {
        "label": "Pruning shears",
        "why": "Cuts cleanly, and a clean cut heals faster than a torn stem.",
        "market": "tools",
    },
    "sprayer": {
        "label": "Knapsack sprayer",
        "why": "Applies a spray evenly - useful the day something does show up.",
        "market": "tools",
    },
    "shade": {
        "label": "Shade cloth or netting",
        "why": "Cuts sun and wind on a young plant and keeps birds off the fruit.",
        "market": "protection",
    },
    "mulch": {
        "label": "Mulch (dry grass, straw or leaves)",
        "why": "Keeps the soil damp and cool and holds weeds down.",
        "market": "soil",
    },
    "compost": {
        "label": "Compost or well-rotted manure",
        "why": "Feeds the soil and holds water where the roots can reach it.",
        "market": "soil",
    },
    "seed": {
        "label": "Seed or seedlings",
        "why": "The planting material itself, from a seed packet to a bagged tree.",
        "market": "seeds",
    },
    "crates": {
        "label": "Crates or bags",
        "why": "Gets a harvest to a buyer without bruising it on the way.",
        "market": "packing",
    },
}

# The market's own section names, so a tool is linked to the page it is sold on
# without the frontend keeping a second copy of this list.
SECTION_LABELS = {
    "seeds": "Seeds & seedlings",
    "soil": "Soil & compost",
    "fertiliser": "Fertiliser & plant food",
    "irrigation": "Watering & irrigation",
    "tools": "Tools & equipment",
    "protection": "Pest & disease control",
    "packing": "Packing & selling",
}


# --- Season -----------------------------------------------------------------


def _gap(mean: float | None, window: tuple[float, float] | None) -> float | None:
    """Degrees outside a temperature window. 0.0 means inside it."""
    if mean is None or window is None:
        return None
    low, high = window
    if low <= mean <= high:
        return 0.0
    return round(low - mean if mean < low else mean - high, 1)


def _rain_ok(month_rain: float | None, window: tuple[float, float] | None) -> bool | None:
    """Does this month deliver half the crop's annual need, pro-rated?"""
    if month_rain is None or window is None:
        return None
    return month_rain >= (window[0] / 12) * RAIN_SHARE_OK


def _runs(numbers: list[int]) -> list[list[int]]:
    """Group months into consecutive runs, wrapping December into January.

    A South African warm season runs October to March, which crosses the year
    boundary. Treating that as two windows would report "October to December"
    and "January to March" as if a grower had to plant twice.
    """
    present = sorted(set(numbers))
    if not present:
        return []
    if len(present) == 12:
        return [present]

    runs: list[list[int]] = [[present[0]]]
    for number in present[1:]:
        if number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])

    if len(runs) > 1 and runs[0][0] == 1 and runs[-1][-1] == 12:
        runs[0] = runs.pop() + runs[0]
    return runs


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return words[0] if words else ""
    if len(words) == 2:
        return f"{words[0]} and {words[1]}"
    return f"{', '.join(words[:-1])} and {words[-1]}"


def _possessive(name: str) -> str:
    """`Banana's`, but `Dry beans'` - a plural name does not take another s."""
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def _window_label(months: list[int]) -> str:
    names = [MONTHS[number - 1] for number in months]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{names[0]} to {names[-1]}"


def _seasons(months: list[int]) -> list[str]:
    seen: list[str] = []
    for number in months:
        season = SEASON_OF_MONTH[number]
        if season not in seen:
            seen.append(season)
    return seen


def planting_window(
    crop: dict,
    normals: list[dict],
    field_rainfall_mm: float | None,
) -> dict:
    """Which months suit this crop on this field, computed from the normals.

    A month qualifies when its mean temperature is inside the crop's ECOCROP
    window and it is not a frost month. When no month qualifies, the closest
    run is reported instead and the gap is stated in degrees, because "October
    to March, still 4 °C short" is usable advice and an empty answer is not.
    """
    window = crop["temperature"]
    low, high = window
    frost_hardy = low <= FROST_HARDY_BELOW_C

    months: list[dict] = []
    for normal in normals:
        number = normal.get("month")
        if not number:
            continue
        gap = _gap(normal.get("mean_temp_c"), window)
        min_temp = normal.get("mean_min_temp_c")
        frost = bool(
            min_temp is not None and min_temp <= FROST_RISK_MIN_C and not frost_hardy
        )
        if gap is None:
            status = "unknown"
        elif frost:
            status = "frost"
        elif gap == 0.0:
            status = "in-window"
        elif gap <= MARGINAL_GAP_C:
            status = "close"
        else:
            status = "outside"

        months.append(
            {
                "month": number,
                "name": MONTHS[number - 1],
                "season": SEASON_OF_MONTH[number],
                "mean_temp_c": normal.get("mean_temp_c"),
                "mean_min_temp_c": min_temp,
                "rainfall_mm": normal.get("rainfall_mm"),
                "temperature_gap_c": gap,
                "rain_ok": _rain_ok(normal.get("rainfall_mm"), crop["rainfall"]),
                "frost_risk": frost,
                "status": status,
            }
        )

    if not months:
        return {
            "available": False,
            "note": (
                "Monthly climate normals are unavailable for this location, so the "
                "planting months cannot be worked out. The windows below still apply."
            ),
            "months": [],
            "windows": [],
            "closest": None,
            "frost_months": [],
        }

    frost_months = [month["name"] for month in months if month["frost_risk"]]
    inside = [month for month in months if month["status"] == "in-window"]
    close = [month for month in months if month["status"] == "close"]
    chosen = inside or close
    basis = "in-window" if inside else ("close" if close else "none")

    # Filled only when nothing qualifies, and read again below to say what the
    # warmest run was.
    closest_windows: list[dict] = []
    shortest: float | None = None

    rainfall_window = crop["rainfall"]
    field_rain = field_rainfall_mm

    def rain_sentence() -> str:
        if not rainfall_window or field_rain is None:
            return ""
        rain_low, rain_high = rainfall_window
        if field_rain < rain_low:
            return (
                f" It wants {rain_low:g}-{rain_high:g} mm a year and this field averages "
                f"{field_rain:g} mm, so plan to irrigate - rain alone will not cover it."
            )
        if field_rain > rain_high:
            return (
                f" It wants {rain_low:g}-{rain_high:g} mm a year and this field averages "
                f"{field_rain:g} mm, so raised beds and drainage matter more than extra water."
            )
        return (
            f" Rainfall here - {field_rain:g} mm a year - sits inside its "
            f"{rain_low:g}-{rain_high:g} mm window."
        )

    if not chosen:
        # Nothing qualifies, but a season still has to be reported: the warmest
        # run is what a grower would try, and naming it with the gap in degrees
        # is more use than "no". Months within a degree of the warmest are kept
        # together so the answer is a run, not a single lucky month.
        usable = [month for month in months if not month["frost_risk"]] or months
        shortest = min(
            (month["temperature_gap_c"] for month in usable),
            key=lambda gap: 99 if gap is None else gap,
        )
        closest_months = [
            month["month"]
            for month in usable
            if month["temperature_gap_c"] is not None
            and month["temperature_gap_c"] <= shortest + 1.0
        ]
        closest_runs = _runs(closest_months)
        closest_windows = [
            {"label": _window_label(run), "months": run, "seasons": _seasons(run)}
            for run in closest_runs
        ]
        summary = (
            f"{crop['name']} wants {low:g}-{high:g} °C, and no month on this field "
            f"comes within {MARGINAL_GAP_C:g} °C of that. The warmest run is "
            f"{_join([item['label'] for item in closest_windows])}, still about "
            f"{shortest:g} °C short - worth trying in your warmest, most sheltered "
            "spot, but expect slow growth and a small harvest." + rain_sentence()
        )
        windows = []
    else:
        windows = [
            {
                "label": _window_label(run),
                "months": run,
                "seasons": _seasons(run),
            }
            for run in _runs([month["month"] for month in chosen])
        ]
        if basis == "in-window":
            summary = (
                f"Plant {_join([item['label'] for item in windows])}: those are the "
                f"months when this field's average temperature sits inside "
                f"{_possessive(crop['name'])} {low:g}-{high:g} °C window."
            )
        else:
            gap = min(month["temperature_gap_c"] for month in chosen)
            where = _join([item["label"] for item in windows])
            if gap <= 1.0:
                summary = (
                    f"Plant {where}: those months sit within {gap:g} °C of "
                    f"{_possessive(crop['name'])} {low:g}-{high:g} °C window, which is "
                    "as close as this field gets. Plant at the start of the run and it "
                    "will do fine; the edge of a window costs yield, not the crop."
                )
            else:
                summary = (
                    f"{crop['name']} wants {low:g}-{high:g} °C and no month here fully "
                    f"reaches that. The closest run is {where}, about {gap:g} °C short - "
                    "worth trying in your warmest, most sheltered spot, but expect slower "
                    "growth and a smaller harvest."
                )
        summary += rain_sentence()

    closest = None
    if not windows and closest_windows and shortest is not None:
        closest = {
            "label": closest_windows[0]["label"],
            "months": closest_windows[0]["months"],
            "seasons": closest_windows[0]["seasons"],
            "short_by_c": shortest,
        }

    if frost_months and not frost_hardy:
        summary += (
            f" {_join(frost_months)} {'is a month' if len(frost_months) == 1 else 'are months'}"
            f" that average below {FROST_RISK_MIN_C:g} °C at night; this crop is not frost-hardy."
        )

    best_start = None
    if windows:
        widest = max(windows, key=lambda item: len(item["months"]))
        best_start = MONTHS[widest["months"][0] - 1]
    elif closest:
        best_start = MONTHS[closest["months"][0] - 1]

    return {
        "available": True,
        "basis": basis,
        "summary": summary,
        "best_start": best_start,
        "windows": windows,
        "closest": closest,
        "months": months,
        "frost_months": frost_months,
        "field": {"annual_rainfall_mm": field_rain},
        "method": (
            "Each month's ten-year mean temperature is compared with this crop's "
            "ECOCROP temperature window; months whose mean night temperature drops "
            "to frost level are excluded for frost-tender crops."
        ),
    }


# --- Guide ------------------------------------------------------------------


def group_for(crop: dict) -> str:
    return GROUP_BY_CATEGORY.get(crop["category"], "plant")


def _ph_text(crop: dict) -> str | None:
    window = crop["ph"]
    if not window:
        return None
    return f"pH {window[0]:g}-{window[1]:g}"


def _spot_step(crop: dict, season: dict, group: str) -> dict:
    detail = "Give it the sunniest ground you have"
    if group in ("orchard", "timber"):
        detail += ", with room for the canopy to grow into and shelter from the worst wind"
    else:
        detail += " - most crops in this group want six hours of direct sun a day"
    detail += ". "
    if crop["category"] in ("Vegetable", "Herb", "Spice"):
        detail += "A bed that held a different family last season is the cheapest disease control there is. "
    if season.get("frost_months"):
        detail += (
            f"Do not use the lowest hollow on the plot: cold air pools there in "
            f"{_join(season['frost_months'])}. "
        )
    detail += "Walk it at noon and see what shade falls on it; that shade is what the crop will get."
    return {"title": "Pick the spot", "detail": detail, "tools": []}


def _soil_step(crop: dict, context: dict | None) -> dict:
    ph_text = _ph_text(crop)
    detail = ""
    if ph_text:
        detail = f"Its soil window is {ph_text}. "
    field_ph = (context or {}).get("ph")
    if field_ph is not None and crop["ph"]:
        low, high = crop["ph"]
        if field_ph < low:
            detail += (
                f"This field measures about {field_ph:g}, below it: work in lime or "
                "wood ash a few weeks before planting and give it time to react. "
            )
        elif field_ph > high:
            detail += (
                f"This field measures about {field_ph:g}, above it: compost, "
                "well-rotted manure and mulch pull it down over a season. "
            )
        else:
            detail += f"This field measures about {field_ph:g}, inside the window - nothing to correct. "
    elif not field_ph:
        detail += "A soil test tells you where yours sits; without one, judge by what grew here before. "
    detail += (
        "Dig it over to a spade's depth and work in compost so roots meet soft, "
        "damp soil rather than a hard pan."
    )
    return {"title": "Prepare the soil", "detail": detail, "tools": ["fork", "compost", "wheelbarrow"]}


def _material_step(crop: dict, group: str) -> dict:
    if group == "orchard":
        detail = (
            "Buy a young plant from a nursery rather than seed: a grafted tree where "
            "the fruit was bred for graft, a seedling in a bag, or - for bananas and "
            "plantains - a strong sucker cut from a healthy clump. Ask what rootstock "
            "it is on, because that decides how big it grows."
        )
        tools = ["seed"]
    elif group == "timber":
        detail = (
            "Buy seedlings or cuttings of the species you actually want to harvest. "
            "Timber is a long commitment, so check the growth habit and the final "
            "spacing before you commit the ground."
        )
        tools = ["seed"]
    elif group == "bed":
        detail = (
            "Seed for most vegetables and herbs; seedlings of tomato, cabbage or "
            "onion buy you four weeks. Check the packet's sow-by date and the "
            "cultivar name - a variety bred for a cool season will bolt in the heat."
        )
        tools = ["seed"]
    else:
        detail = (
            "Use certified seed, and check that the cultivar suits your rainfall and "
            "the length of your season. Seed saved from a hybrid will not repeat the "
            "parent; open-pollinated seed will."
        )
        tools = ["seed"]
    detail += " Buy a little more than you need: gaps get filled."
    return {"title": "Get the planting material", "detail": detail, "tools": tools}


def _plant_step(crop: dict, season: dict, group: str) -> dict:
    start = season.get("best_start")
    detail = ""
    if start:
        detail += f"Plant at the start of {start}, not the end of the run, so the crop has the whole good season ahead of it. "
    elif season.get("available") is False:
        detail += "Plant when the ground is warm and the rain has started; the windows below tell you what the crop is looking for. "
    if group == "orchard":
        detail += (
            "Dig a hole wider than the root ball, keep the plant at the depth it stood "
            "in its bag, backfill with the soil you took out plus compost, and firm it "
            "in with your heel so no air pocket is left around the roots."
        )
        tools = ["spade", "trowel", "stakes", "watering-can"]
    elif group == "timber":
        detail += (
            "Plant at the depth it grew at, firm the soil around the roots, and stake "
            "it against wind for the first two seasons."
        )
        tools = ["spade", "stakes", "watering-can"]
    elif group == "plant":
        detail += (
            "Plant at the depth it grew at, firm it in, and water it straight away. "
            "If the catalogue has no category for it, follow the seller's own "
            "instructions first - a nursery knows the plant it sold you."
        )
        tools = ["spade", "trowel", "watering-can"]
    elif group == "bed":
        detail += (
            "Sow seed two to three times its own thickness deep, or set seedlings at "
            "the depth they grew in their tray. Space them as the packet says - closer "
            "looks better in week one and gives you disease by week six."
        )
        tools = ["trowel", "line", "rake"]
    else:
        detail += (
            "Draw the furrow the width of your hoe, sow at the rate on the bag, cover "
            "and firm - seed needs soil contact, not a loose pile of clods."
        )
        tools = ["hoe", "line", "rake"]
    return {"title": "Plant it properly", "detail": detail, "tools": tools}


def _water_step(crop: dict, context: dict | None) -> dict:
    rainfall_window = crop["rainfall"]
    field_rain = (context or {}).get("annual_rainfall_mm")
    detail = ""
    if rainfall_window and field_rain is not None:
        low, high = rainfall_window
        if field_rain < low:
            detail = (
                f"It wants {low:g}-{high:g} mm a year and this field averages "
                f"{field_rain:g} mm, so you will be irrigating through the dry months. "
            )
        elif field_rain > high:
            detail = (
                f"This field averages {field_rain:g} mm, above its {low:g}-{high:g} mm "
                "window: water less often, and more deeply when you do. "
            )
        else:
            detail = (
                f"This field's {field_rain:g} mm a year sits inside its window, so rain "
                "does most of the work and irrigation covers the gaps. "
            )
    elif rainfall_window:
        detail = (
            f"It wants {rainfall_window[0]:g}-{rainfall_window[1]:g} mm a year; this "
            "field's rainfall is unavailable, so judge by the ground. "
        )
    detail += (
        "Water at the base, in the morning, and check with a finger 5 cm down before "
        "you add more - wet surface over dry subsoil is the usual way a plant dies "
        "of thirst in watered ground."
    )
    return {"title": "Water it in and keep it watered", "detail": detail, "tools": ["watering-can", "hose", "mulch"]}


def _feed_step(crop: dict, group: str) -> dict:
    if crop["category"] in SELF_FEEDING:
        detail = (
            "This one feeds itself: legumes and fodder crops fix nitrogen from the "
            "air, and feeding them like a cabbage gives you leaf and no pod. Keep "
            "adding compost and leave the roots in the ground after harvest - they "
            "are the fertiliser for the next crop."
        )
    elif group in ("orchard", "timber"):
        detail = (
            "Compost and mulch at planting, then feed at the start of each growing "
            "season rather than little and often. Keep mulch clear of the stem so it "
            "does not rot the bark."
        )
    else:
        detail = (
            "Compost at planting carries it for weeks; then feed as it starts growing "
            "hard. Too much nitrogen gives leaf at the expense of fruit, so follow "
            "the rate on the bag rather than a guess."
        )
    return {"title": "Feed it and mulch", "detail": detail, "tools": ["mulch", "compost"]}


def _health_step(group: str) -> dict:
    detail = (
        "Walk the row twice a week and look under the leaves, where the first "
        "insects and the first spots show. Act on the few plants at the edge before "
        "it reaches the middle: pulling one sick plant early is cheaper than spraying "
        "a whole bed."
    )
    if group in ("orchard", "timber"):
        detail += " Check the stem at the soil line too - that is where borers and rot start."
    return {"title": "Watch for trouble", "detail": detail, "tools": ["sprayer", "secateurs"]}


def _harvest_step(crop: dict, group: str) -> dict:
    if group == "orchard":
        detail = (
            "Pick when it colours and comes away with a gentle lift, not a pull. For a "
            "bunch or cane crop, cut the whole stem at once rather than taking one at a "
            "time. The variety's own days-to-harvest is on the nursery label; Nuru's "
            "catalogue does not carry it yet."
        )
    elif group == "timber":
        detail = (
            "Timber is harvested on a rotation measured in years. Mark what you plant "
            "and when, because the trees that look identical now will not be when the "
            "decision comes."
        )
    elif group == "bed":
        detail = (
            "Pick what you need and keep picking - most bed crops stop producing once "
            "the fruit is left to ripen on the plant. The variety's days-to-harvest is "
            "on the seed packet; Nuru's catalogue does not carry it yet."
        )
    elif group == "field":
        detail = (
            "Harvest when the grain or pod is hard and the plant is starting to dry, "
            "then dry it further before storing. Stored damp, a good harvest is lost "
            "in a week. The variety's days-to-harvest is on the seed bag; Nuru's "
            "catalogue does not carry it yet."
        )
    else:
        detail = (
            "Harvest at the stage the buyer wants and note the date it happened - "
            "next season that note is worth more than any label on a packet."
        )
    tools = ["crates"] if crop["category"] in SOLD_CATEGORIES else []
    return {"title": "Harvest it", "detail": detail, "tools": tools}


def _tools_used(steps: list[dict]) -> list[dict]:
    """Every tool the steps mention, once, with what it is for."""
    keys: list[str] = []
    for step in steps:
        for key in step["tools"]:
            if key not in keys:
                keys.append(key)
    return [
        {
            "key": key,
            **TOOLS[key],
            "market_label": SECTION_LABELS.get(TOOLS[key]["market"]),
        }
        for key in keys
        if key in TOOLS
    ]


def build_steps(crop: dict, season: dict, context: dict | None) -> list[dict]:
    group = group_for(crop)
    steps = [
        _spot_step(crop, season, group),
        _soil_step(crop, context),
        _material_step(crop, group),
        _plant_step(crop, season, group),
        _water_step(crop, context),
        _feed_step(crop, group),
        _health_step(group),
        _harvest_step(crop, group),
    ]
    for number, step in enumerate(steps, start=1):
        step["n"] = number
    return steps


def build_needs(crop: dict, season: dict, context: dict | None) -> list[dict]:
    """The market sections this crop actually sends you to, with the reason.

    Each reason quotes this crop's record or this field's measurement, so the
    shopping list is the answer to a question rather than a generic advert.
    """
    needs: list[dict] = [
        {
            "section": "seeds",
            "label": "Seeds & seedlings",
            "why": f"Seed, a seedling or a sucker to start {crop['name']}.",
        },
        {
            "section": "tools",
            "label": "Tools & equipment",
            "why": "A spade, a hoe and a line do most of this work by hand.",
        },
    ]

    rainfall_window = crop["rainfall"]
    field_rain = (context or {}).get("annual_rainfall_mm")
    if rainfall_window and field_rain is not None and field_rain < rainfall_window[0]:
        needs.append(
            {
                "section": "irrigation",
                "label": "Watering & irrigation",
                "why": (
                    f"This crop wants {rainfall_window[0]:g}-{rainfall_window[1]:g} mm a "
                    f"year and this field averages {field_rain:g} mm."
                ),
            }
        )

    field_ph = (context or {}).get("ph")
    if crop["ph"] and field_ph is not None and not (crop["ph"][0] <= field_ph <= crop["ph"][1]):
        direction = "raise" if field_ph < crop["ph"][0] else "lower"
        needs.append(
            {
                "section": "soil",
                "label": "Soil & compost",
                "why": (
                    f"Soil here measures pH {field_ph:g}, outside this crop's "
                    f"{_ph_text(crop)} window - you need to {direction} it."
                ),
            }
        )
    elif not crop["ph"]:
        needs.append(
            {
                "section": "soil",
                "label": "Soil & compost",
                "why": "ECOCROP has no pH window for this species; compost is the safe correction.",
            }
        )

    if season.get("basis") == "close" or season.get("frost_months"):
        needs.append(
            {
                "section": "protection",
                "label": "Pest & disease control",
                "why": (
                    "The months that suit this crop are marginal here, so windbreaks, "
                    "shade cloth or frost cover are what buy it the extra degrees."
                ),
            }
        )

    if crop["category"] not in SELF_FEEDING:
        needs.append(
            {
                "section": "fertiliser",
                "label": "Fertiliser & plant food",
                "why": "Compost at planting, then a feed once it is growing hard.",
            }
        )

    if crop["category"] in SOLD_CATEGORIES:
        needs.append(
            {
                "section": "packing",
                "label": "Packing & selling",
                "why": "Crates, bags or a scale to get the harvest to a buyer.",
            }
        )
    return needs


def build_watch(crop: dict, season: dict, context: dict | None) -> list[str]:
    """One line per real risk, each traceable to a number."""
    watch: list[str] = []
    texture = (context or {}).get("texture_class")
    if texture in HEAVY_TEXTURES and crop["name"] in ROOT_CROPS:
        watch.append(
            f"{texture} soil is heavy and this crop's harvest is a root or bulb - "
            "plant on ridges or in raised beds or it will fork and rot."
        )
    field_ph = (context or {}).get("ph")
    if crop["ph"] and field_ph is not None and not (crop["ph"][0] <= field_ph <= crop["ph"][1]):
        watch.append(
            f"pH here is about {field_ph:g} against its {_ph_text(crop)} window; "
            "correct it before planting rather than after."
        )
    if season.get("frost_months") and crop["temperature"][0] > FROST_HARDY_BELOW_C:
        watch.append(
            f"{_join(season['frost_months'])} can frost here and this crop's window "
            f"starts at {crop['temperature'][0]:g} °C. Frost cloth or a sheltered "
            "spot is the difference between a crop and a loss."
        )
    rainfall_window = crop["rainfall"]
    field_rain = (context or {}).get("annual_rainfall_mm")
    if rainfall_window and field_rain is not None and field_rain < rainfall_window[0]:
        watch.append(
            f"Rainfall here is {field_rain:g} mm against a {rainfall_window[0]:g}-"
            f"{rainfall_window[1]:g} mm need. Without irrigation this crop will stall "
            "in the dry months."
        )
    if season.get("basis") == "close":
        watch.append(
            "No month reaches this crop's temperature window on this field. It is a "
            "try, not a sure thing - and the yield will reflect that."
        )
    if crop["category"] in SELF_FEEDING:
        watch.append(
            "Do not feed this group nitrogen-heavy fertiliser; it fixes its own and "
            "the extra goes into leaf instead of pod."
        )
    return watch


def build_guide(crop: dict, season: dict, context: dict | None) -> dict:
    group = group_for(crop)
    steps = build_steps(crop, season, context)
    return {
        "group": group,
        "group_label": GROUP_LABELS.get(group, GROUP_LABELS["plant"]),
        "steps": steps,
        "tools": _tools_used(steps),
        "needs": build_needs(crop, season, context),
        "watch": build_watch(crop, season, context),
    }


# --- The page payload -------------------------------------------------------


def _crop_block(crop: dict) -> dict:
    return {
        "slug": slugify(crop["scientific_name"]),
        "name": crop["name"],
        "scientific_name": crop["scientific_name"],
        "family": crop["family"],
        "category": crop["category"],
        "has_common_name": crop["has_common_name"],
        "temperature_c": list(crop["temperature"]),
        "rainfall_mm_per_year": list(crop["rainfall"]) if crop["rainfall"] else None,
        "soil_ph": list(crop["ph"]) if crop["ph"] else None,
        "source": crop["source"],
    }


async def detail_for(
    slug: str,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict | None:
    """Everything one crop page needs, or None when the slug is not a species.

    Coordinates are optional. Without them the page still carries the crop's
    windows, steps and tools, and says the months need a field; with them the
    season is computed against this field's own normals.
    """
    crop = find_by_slug(slug)
    if crop is None:
        return None

    context: dict | None = None
    weather: dict | None = None
    soil: dict | None = None
    cached = False
    if latitude is not None and longitude is not None:
        context, weather, soil, cached = await field_context(latitude, longitude)

    fit = evaluate_crop(crop, context) if context else None
    climate = (weather or {}).get("climate") or {}
    normals = climate.get("monthly_normals") or []
    field_rain = (context or {}).get("annual_rainfall_mm")

    season = planting_window(crop, normals, field_rain)
    if context and climate:
        season["field"] = {
            "annual_rainfall_mm": field_rain,
            "years_used": climate.get("years_used"),
            "years_span": climate.get("years_span"),
            "provider": (weather or {}).get("source", {}).get("climate_name"),
        }

    guide = build_guide(crop, season, context)

    return {
        "crop": _crop_block(crop),
        "fit": fit,
        "season": season,
        "guide": guide,
        "context": (
            {
                "month": context["month_name"],
                "mean_temperature_c": context["same_month_mean_temp_c"],
                "annual_rainfall_mm": context["annual_rainfall_mm"],
                "soil_ph": context["ph"],
                "soil_texture": context["texture_class"],
            }
            if context
            else None
        ),
        "source": {
            "numbers": ECOCROP_ATTRIBUTION,
            "climate": (
                (weather or {}).get("source", {}).get("attribution")
                if weather
                else None
            ),
            "method": (
                "Temperature, rainfall and pH windows are FAO ECOCROP. Planting "
                "months are computed from this location's monthly climate normals. "
                "Steps and tools are general practice for the crop group, not "
                "ECOCROP data, and where a real number is missing the text says so."
            ),
            "cached": cached,
        },
    }
