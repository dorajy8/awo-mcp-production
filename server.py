import json
import math
from pathlib import Path
import sys

import pandas as pd
from mcp.server.fastmcp import FastMCP

from src.data_loader import DataLoader, resolve_source
from src.data_repository import DataRepository


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_SOURCE = resolve_source(BASE_DIR)


# --------------------------------------------------
# Load data
# --------------------------------------------------

loader = DataLoader(DATA_SOURCE)
datasets = loader.load_all()

repository = DataRepository(datasets)


# --------------------------------------------------
# MCP server
# --------------------------------------------------

mcp = FastMCP("AWO MCP")


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def normalize_nan(value):
    """Convert pandas/NumPy NaN values to JSON-compatible None."""

    if isinstance(value, dict):
        return {
            key: normalize_nan(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            normalize_nan(item)
            for item in value
        ]

    if isinstance(value, float) and math.isnan(value):
        return None

    return value


def to_json(data) -> str:
    """Convert Python data to a JSON string."""

    return json.dumps(
        normalize_nan(data),
        ensure_ascii=False,
        indent=2,
    )


# --------------------------------------------------
# MCP Tools
# --------------------------------------------------

@mcp.tool()
def count_facilities(city: str) -> int:
    """
    Count AWO facilities in a city.

    Args:
        city: City name, for example "Berlin".
    """

    return repository.count_facilities(city)

@mcp.tool()
def detect_duplicates() -> str:
    """
    Detect exact duplicate rows in all AWO datasets.

    A duplicate means that every column in a row is identical
    to another row in the same dataset.

    Returns:
        JSON containing the complete duplicated rows and
        their number of occurrences.
    """

    results = repository.detect_duplicates()

    return to_json(results)

@mcp.tool()
def search_facilities(city: str) -> str:
    """
    Search for AWO facilities in a city.

    Args:
        city: City name, for example "Berlin".

    Returns:
        JSON containing matching facilities and their basic contact/address information.
    """

    results = repository.search_facilities(city)

    return to_json(results)


@mcp.tool()
def get_facility_details(name: str) -> str:
    """
    Find AWO facilities by name and return detailed information.

    Args:
        name: Full or partial facility name.

    Returns:
        JSON containing facility details, address, provider,
        and the facility's service description.
    """

    results = repository.get_facility_details(name)

    return to_json(results)


@mcp.tool()
def search_services(query: str) -> str:
    """
    Search the structured AWO service catalogue.

    Args:
        query: Search term, such as "Senioren", "Pflege", or "Beratung".

    Returns:
        JSON containing matching services.
    """

    results = repository.search_services(query)

    return to_json(results)

@mcp.tool()
def check_completeness() -> str:
    """
    Check completeness of all AWO datasets.

    Missing values include both NaN and empty/whitespace-only
    strings.

    Returns:
        JSON containing dataset-level and column-level
        completeness statistics.
    """

    results = repository.check_completeness()

    return to_json(results)

@mcp.tool()
def generate_statistics() -> str:
    """
    Generate statistics for the AWO datasets.

    Returns:
        JSON containing dataset sizes, facility statistics,
        service statistics, and relationship statistics.
    """

    results = repository.generate_statistics()

    return to_json(results)

@mcp.tool()
def compare_facilities(
    facility_1: str,
    facility_2: str,
) -> str:
    """
    Compare two AWO facilities by name.

    Args:
        facility_1: Full or partial name of the first facility.
        facility_2: Full or partial name of the second facility.

    Returns:
        JSON containing the details of both facilities.
    """

    results = repository.compare_facilities(
        facility_1,
        facility_2,
    )

    return to_json(results)

@mcp.tool()
def get_awo_details(iri: str) -> str:
    """
    Get the address, map link, and opening hours for one AWO facility.

    Args:
        iri: Facility IRI, as returned by search_facilities or
            get_facility_details.

    Returns:
        JSON containing the facility's address, Google Maps link, contact
        details, opening hours, accessibility, offers, provider, and a link
        to its entry in the source directory (caritas.de or dhs.de).
    """

    result = repository.get_awo_details(iri)

    if result is None:
        return f"No AWO facility found with IRI '{iri}'."

    return to_json(result)

@mcp.tool()
def find_nearby(
    location: str,
    radius_km: float = 2.0,
    query: str | None = None,
    accessible_only: bool = False,
    limit: int = 10,
) -> str:
    """
    Find AWO facilities near a location, nearest first.

    Args:
        location: "latitude,longitude" (for example "52.5446,13.3592"),
            a postal code (for example "13353"), or part of a street name
            (for example "Müllerstraße"). For a landmark or neighbourhood,
            pass its approximate coordinates.
        radius_km: Search radius in kilometres. Defaults to 2.
        query: Optional search terms matched against name, group (German or
            English), category, services, offers, and audience. Separate
            several terms with commas to match any of them (for example
            "Sucht, Alkohol" or "Wohnungsnot, obdach").
        accessible_only: Only return facilities marked as wheelchair accessible.
        limit: Maximum number of results. Defaults to 10.

    Returns:
        JSON containing the resolved origin, the number of matches, and the
        nearest facilities with distance, address, contact, and opening hours.
    """

    results = repository.find_nearby(
        location,
        radius_km=radius_km,
        query=query,
        accessible_only=accessible_only,
        limit=limit,
    )

    return to_json(results)

# --------------------------------------------------
# MCP Prompts
# --------------------------------------------------

# Search terms that work well with find_nearby, by kind of need. The data is
# in German, so German terms match best.
SEARCH_TERM_HINTS = """
- Addiction (alcohol, drugs, gambling, gaming, medication): "Sucht, Alkohol, Drogen,
  Glücksspiel, Mediennutzung, Medikamenten"
- Housing loss, eviction, homelessness: "Wohnungsnot, Wohnungslos, obdach, Notübernachtung"
- Debt: "Schuldner"
- Children, youth, families: "Jugend, Kinder, Familie, Eltern"
- Older people and care: "Senior, Pflege"
- Disability or mental health: "Behinder, psych, Eingliederung"
- Migration and integration: "Migration"
- Unemployment and training: "erwerbslos, arbeitslos, Ausbildung"
- Outreach and drop-in (staff who come to you, or walk in without an appointment):
  "Streetwork, aufsuchend, Kontakt- und Anlaufstelle"
"""

RELEVANCE_RUBRIC = """
Rate how strongly you'd recommend each place as a step for this person, from 1 to 5.
Start from first-step fit, then adjust:
- First-step fit (most important):
  3 = a good place to start for this need (e.g. a counselling centre for drinking),
  2 = addresses the need but usually comes later or suits only some people
      (e.g. supported living, a clinic for a specific group),
  1 = only loosely related.
- Distance: within 1 km +1, 1–3 km +0.5, further +0.
- Reachability: phone or email listed +1, only a source link or address +0.5.
- If the person needs step-free access and it isn't listed as accessible, -1.
Round to the nearest whole number, then cap it: places with first-step fit 2 can
get at most 3/5, and fit 1 at most 2/5. So 4–5/5 always means "a good place to
start". Show it as ★ (e.g. ★★★★☆ 4/5).
The rating reflects fit for their need based on the directory data, not the quality
of the service; say so once.
"""


@mcp.prompt(title="Find help near me")
def find_help(situation: str = "", location: str = "") -> str:
    """
    Explain the kinds of help available for someone's need, recommend 3–5
    nearby places rated by relevance, and list who to contact first.

    Args:
        situation: What the person needs help with, in their own words.
        location: Where they are: a postal code, street, or landmark in Berlin.
    """

    return f"""You are helping someone find social services in Berlin using the AWO tools.
Be warm and brief, and use plain language. Reply in the language the person writes in.
Keep the whole answer short enough to read on a phone.

What they need help with: {situation or "not given yet"}
Where they are: {location or "not given yet"}

Before answering:
1. If they mention danger to themselves or others, give these numbers before
   anything else: 112 (emergency), 110 (police), Telefonseelsorge
   0800 111 0 111 or 0800 111 0 222 (free, 24/7).
2. If the need or the location is missing, ask for it in one short question.
   Don't ask for names or other personal details; they aren't needed to search.
3. Turn their need into German search terms and call find_nearby with
   comma-separated terms. Useful terms:
{SEARCH_TERM_HINTS}
   For a landmark or neighbourhood, pass its approximate "latitude,longitude".
   If they need step-free access, set accessible_only.
   If fewer than 3 results come back, widen radius_km (2 → 5) or broaden the terms.
   If the need suggests they may not be able to come in (e.g. homelessness,
   addiction), also search the outreach and drop-in terms.
4. Call get_awo_details for the most promising places. Read their offers, topics,
   names, and categories to work out who each place is for (e.g. women only,
   pregnant women, people who use illegal drugs, young people).

Then answer in this order:

A. A one-line acknowledgement, then a safety note only if the need calls for one
   (e.g. don't stop heavy daily drinking suddenly because withdrawal can be
   dangerous; act quickly on an eviction notice because deadlines are short).

B. Kinds of help: 2–4 short bullets on the types of service that exist for this
   need (e.g. counselling centre, clinic, supported living, drop-in, outreach),
   what each is for, and which is usually the best first step.

C. Recommended places: 3 to 5, ordered by rating. For each:
   - Name and rating
   - Who it's for, in one line, flagging limits like "women only" or
     "mainly for illegal drugs"
   - Address, distance, and the directions link
   - Opening hours, or "not listed"
{RELEVANCE_RUBRIC}

D. Who to contact first: the three best-rated places that can be reached, as a
   compact list of name, phone, email, and when to call. Don't repeat their
   descriptions. Prefer outreach or drop-in services when they fit the need.
   - The directory lists facility contact details only, not named staff or
     outreach workers. Never invent names, phone numbers, or email addresses.
   - If fewer than three places have contact details, say so plainly. For those
     places, give their source link (source_url), which often lists more contact
     information; if there's none, give the address to visit during opening hours.

E. What the directory doesn't cover, in one line, when it matters for this need
   (e.g. self-help groups, services outside central and northern Berlin). Then
   offer to look for something else or somewhere else.

If nothing fits, say so honestly rather than suggesting unrelated services."""


# --------------------------------------------------
# Run server
# --------------------------------------------------

if __name__ == "__main__":
    print("AWO MCP server starting...", file=sys.stderr)
    mcp.run()

    
