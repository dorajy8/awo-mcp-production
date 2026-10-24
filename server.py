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
        query: Optional search term matched against name, group (German or
            English), category, services, and audience (for example "Sucht",
            "addiction", "Jugend", "Alkohol").
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
# Run server
# --------------------------------------------------

if __name__ == "__main__":
    print("AWO MCP server starting...", file=sys.stderr)
    mcp.run()

    
