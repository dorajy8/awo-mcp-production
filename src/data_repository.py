import math
from urllib.parse import parse_qs, quote, urlparse

import pandas as pd


class DataRepository:
    """Provides access to the normalized AWO datasets."""

    def __init__(self, datasets: dict[str, pd.DataFrame]):
        self.einrichtung = datasets["einrichtung"]
        self.adresse = datasets["adresse"]
        self.angebot = datasets["angebot"]
        self.traeger = datasets["traeger"]

        # Build indexes for IRI-based relationships.
        self.address_by_iri = {}
        for _, address in self.adresse.iterrows():
            iri = address["iri"]
            self.address_by_iri[iri] = {
                "iri": iri,
                "schema:streetAddress": address["schema:streetAddress"],
                "schema:postalCode": address["schema:postalCode"],
                "schema:addressLocality": address["schema:addressLocality"],
                "schema:addressCountry": address["schema:addressCountry"],
                "schema:latitude": address["schema:latitude"],
                "schema:longitude": address["schema:longitude"],
            }

        self.provider_by_iri = {}
        for _, provider in self.traeger.iterrows():
            iri = provider["iri"]
            self.provider_by_iri[iri] = {
                "iri": iri,
                "schema:name": provider["schema:name"],
                "foaf:homepage": provider["foaf:homepage"],
                "schema:address": provider["schema:address"],
            }

        self.offers_by_facility = {}
        for _, offer in self.angebot.iterrows():
            name = clean(offer["schema:name"])
            category = clean(offer["schema:category"])
            entry = {
                "name": name or category,
                "category": category if name and category != name else None,
            }

            if not entry["name"]:
                continue

            offers = self.offers_by_facility.setdefault(offer["schema:provider"], [])

            if entry not in offers:
                offers.append(entry)

    def count_facilities(self, city: str) -> int:
        """Count facilities in a city."""

        addresses = self.einrichtung["schema:address"].map(
            self.address_by_iri
        )

        city_values = addresses.apply(
            lambda address: (
                address.get("schema:addressLocality")
                if isinstance(address, dict)
                else None
            )
        )

        return int(
            city_values
            .fillna("")
            .str.casefold()
            .eq(city.casefold())
            .sum()
        )

    def search_facilities(self, city: str) -> list[dict]:
        """Find facilities in a city."""

        results = []

        for _, facility in self.einrichtung.iterrows():
            address_iri = facility["schema:address"]

            if pd.isna(address_iri):
                continue

            address = self.address_by_iri.get(address_iri)

            if not address:
                continue

            locality = address.get("schema:addressLocality")

            if pd.isna(locality):
                continue

            if str(locality).casefold() != city.casefold():
                continue

            results.append(
                {
                    "iri": facility["iri"],
                    "name": facility["schema:name"],
                    "street": address.get("schema:streetAddress"),
                    "postal_code": address.get("schema:postalCode"),
                    "city": locality,
                    "telephone": facility["schema:telephone"],
                    "email": facility["schema:email"],
                    "homepage": facility["foaf:homepage"],
                }
            )

        return results

    def get_facility_details(self, name: str) -> list[dict]:
        """Find facilities by name and return their details."""

        matches = self.einrichtung[
            self.einrichtung["schema:name"]
            .fillna("")
            .str.casefold()
            .str.contains(name.casefold(), regex=False)
        ]

        results = []

        for _, facility in matches.iterrows():
            address = self.address_by_iri.get(
                facility["schema:address"]
            )

            provider = self.provider_by_iri.get(
                facility["schema:parentOrganization"]
            )

            result = {
                "iri": facility["iri"],
                "name": facility["schema:name"],
                "alternate_name": facility["schema:alternateName"],
                "telephone": facility["schema:telephone"],
                "email": facility["schema:email"],
                "homepage": facility["foaf:homepage"],
                "category": facility["schema:category"],
                "service_description": facility["schema:availableService"],
            }

            if address:
                result["address"] = {
                    "street": address.get("schema:streetAddress"),
                    "postal_code": address.get("schema:postalCode"),
                    "city": address.get("schema:addressLocality"),
                    "country": address.get("schema:addressCountry"),
                    "latitude": address.get("schema:latitude"),
                    "longitude": address.get("schema:longitude"),
                }

            if provider:
                result["provider"] = {
                    "iri": provider.get("iri"),
                    "name": provider.get("schema:name"),
                    "homepage": provider.get("foaf:homepage"),
                }

            results.append(result)

        return results

    def search_services(self, query: str) -> list[dict]:
        """Search the structured service catalogue."""

        text_columns = [
            "schema:name",
            "schema:category",
            "schema:audience",
        ]

        mask = pd.Series(False, index=self.angebot.index)

        for column in text_columns:
            mask |= (
                self.angebot[column]
                .fillna("")
                .astype(str)
                .str.casefold()
                .str.contains(
                    query.casefold(),
                    regex=False,
                )
            )

        matches = self.angebot[mask]

        return matches[
            [
                "iri",
                "schema:name",
                "schema:category",
                "schema:audience",
            ]
        ].to_dict("records")

    def detect_duplicates(self) -> dict:
        """
        Detect exact duplicate rows in all datasets.

        A duplicate means that every column in a row has
        the same value as another row in the same dataset.
        """

        datasets = {
            "einrichtung": self.einrichtung,
            "adresse": self.adresse,
            "angebot": self.angebot,
            "traeger": self.traeger,
        }

        duplicates = {}

        for dataset_name, df in datasets.items():

            # Find rows that are exact duplicates.
            duplicate_mask = df.duplicated(
                keep=False
            )

            duplicate_rows = df[duplicate_mask]

            if duplicate_rows.empty:
                continue

            # Group identical rows together.
            grouped = (
                duplicate_rows
                .groupby(
                    list(df.columns),
                    dropna=False,
                    sort=False,
                )
                .size()
                .reset_index(name="occurrences")
            )

            groups = []

            for _, group in grouped.iterrows():

                row = {
                    column: group[column]
                    for column in df.columns
                }

                groups.append(
                    {
                        "occurrences": int(group["occurrences"]),
                        "row": row,
                    }
                )

            duplicates[dataset_name] = groups

        return duplicates

    def check_completeness(self) -> dict:
        """
        Check data completeness for all datasets.

        Both NaN values and empty/whitespace-only strings
        are treated as missing.
        """

        datasets = {
            "einrichtung": self.einrichtung,
            "adresse": self.adresse,
            "angebot": self.angebot,
            "traeger": self.traeger,
        }

        completeness = {}

        for dataset_name, df in datasets.items():
            total_rows = len(df)
            columns = {}

            for column in df.columns:
                missing_mask = (
                    df[column].isna()
                    | df[column].astype(str).str.strip().eq("")
                )

                missing_count = int(missing_mask.sum())

                if total_rows > 0:
                    missing_percentage = (
                        missing_count / total_rows
                    ) * 100
                else:
                    missing_percentage = 0.0

                columns[column] = {
                    "total": total_rows,
                    "missing": missing_count,
                    "missing_percentage": round(
                        missing_percentage,
                        2,
                    ),
                }

            total_cells = total_rows * len(df.columns)

            total_missing = sum(
                column_info["missing"]
                for column_info in columns.values()
            )

            if total_cells > 0:
                overall_missing_percentage = (
                    total_missing / total_cells
                ) * 100
            else:
                overall_missing_percentage = 0.0

            completeness[dataset_name] = {
                "rows": total_rows,
                "columns": len(df.columns),
                "total_cells": total_cells,
                "missing_cells": total_missing,
                "missing_percentage": round(
                    overall_missing_percentage,
                    2,
                ),
                "columns_detail": columns,
            }

        return completeness

    def generate_statistics(self) -> dict:
        """
        Generate statistics for the AWO datasets.
        """

        datasets = {
            "einrichtung": self.einrichtung,
            "adresse": self.adresse,
            "angebot": self.angebot,
            "traeger": self.traeger,
        }

        statistics = {
            "dataset_sizes": {
                name: len(df)
                for name, df in datasets.items()
            }
        }

        # ----------------------------------------------
        # Einrichtung statistics
        # ----------------------------------------------

        facilities = self.einrichtung

        # Facilities by city
        addresses = facilities["schema:address"].map(
            self.address_by_iri
        )

        cities = addresses.apply(
            lambda address: (
                address.get("schema:addressLocality")
                if isinstance(address, dict)
                else None
            )
        )

        statistics["facilities_by_city"] = (
            cities
            .dropna()
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .to_dict()
        )

        # Facilities by category
        statistics["facilities_by_category"] = (
            facilities["schema:category"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .to_dict()
        )

        # Facilities by provider
        providers = facilities["schema:parentOrganization"].map(
            self.provider_by_iri
        )

        provider_names = providers.apply(
            lambda provider: (
                provider.get("schema:name")
                if isinstance(provider, dict)
                else None
            )
        )

        statistics["facilities_by_provider"] = (
            provider_names
            .dropna()
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .to_dict()
        )

        # ----------------------------------------------
        # Relationship statistics
        # ----------------------------------------------

        statistics["facility_relationships"] = {
            "with_address": int(
                facilities["schema:address"]
                .map(self.address_by_iri)
                .apply(lambda x: isinstance(x, dict))
                .sum()
            ),
            "without_address": int(
                facilities["schema:address"]
                .map(self.address_by_iri)
                .apply(lambda x: not isinstance(x, dict))
                .sum()
            ),
            "with_provider": int(
                facilities["schema:parentOrganization"]
                .map(self.provider_by_iri)
                .apply(lambda x: isinstance(x, dict))
                .sum()
            ),
            "without_provider": int(
                facilities["schema:parentOrganization"]
                .map(self.provider_by_iri)
                .apply(lambda x: not isinstance(x, dict))
                .sum()
            ),
        }

        # ----------------------------------------------
        # Angebot statistics
        # ----------------------------------------------

        services = self.angebot

        statistics["services_by_category"] = (
            services["schema:category"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .to_dict()
        )

        statistics["services_by_audience"] = (
            services["schema:audience"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .to_dict()
        )

        return statistics

    def compare_facilities(
        self,
        facility_1: str,
        facility_2: str,
    ) -> list[dict]:
        """
        Compare two facilities by name.
        """

        results = []

        for name in [facility_1, facility_2]:
            matches = self.get_facility_details(name)

            results.append(
                {
                    "search_name": name,
                    "matches": matches,
                }
            )

        return results
    def get_awo_details(self, iri: str) -> dict | None:
        """Return address, map link, and opening hours for one facility."""

        matches = self.einrichtung[self.einrichtung["iri"] == iri]

        if matches.empty:
            return None

        facility = matches.iloc[0]
        address = self.address_by_iri.get(facility["schema:address"]) or {}
        address_text = format_address(address)

        latitude = address.get("schema:latitude")
        longitude = address.get("schema:longitude")

        if pd.notna(latitude) and pd.notna(longitude):
            map_query = f"{latitude},{longitude}"
        else:
            map_query = ", ".join(
                part for part in [clean(facility["schema:name"]), address_text] if part
            )

        map_url = (
            "https://www.google.com/maps/search/?api=1&query="
            + quote(map_query)
            if map_query
            else None
        )

        return {
            "iri": facility["iri"],
            "name": facility["schema:name"],
            "alternate_name": first_line(facility["schema:alternateName"]) or None,
            "category": clean(facility["schema:category"]) or None,
            "address": address_text or None,
            "map_url": map_url,
            "telephone": facility["schema:telephone"],
            "email": facility["schema:email"],
            "homepage": facility["foaf:homepage"],
            "source_url": source_url(facility["schema:mainEntityOfPage"]),
            "opening_hours": facility["schema:openingHours"],
            "accessibility": facility["schema:accessibilitySummary"],
            "offers": self.offers_by_facility.get(facility["iri"], []),
            "provider": clean(
                (self.provider_by_iri.get(facility["schema:parentOrganization"]) or {})
                .get("schema:name")
            ) or None,
        }

    def facility_points(self) -> list[dict]:
        """Return every facility that has coordinates, ready for a map."""

        points = []

        for _, facility in self.einrichtung.iterrows():
            address = self.address_by_iri.get(facility["schema:address"])

            if not address:
                continue

            latitude = to_float(address.get("schema:latitude"))
            longitude = to_float(address.get("schema:longitude"))

            if latitude is None or longitude is None:
                continue

            provider = self.provider_by_iri.get(
                facility["schema:parentOrganization"]
            ) or {}

            offers = self.offers_by_facility.get(facility["iri"], [])
            group = facility_group(facility, offers)

            points.append(
                {
                    "iri": facility["iri"],
                    "name": clean(facility["schema:name"]),
                    "alternate_name": first_line(facility["schema:alternateName"]) or None,
                    "group": group,
                    "group_en": GROUP_LABELS_EN[group],
                    "category": clean(facility["schema:category"]) or None,
                    "audience": split_list(facility["schema:audience"]),
                    "services": clean(facility["schema:availableService"]) or None,
                    "offers": offers,
                    "accessible": accessibility_flag(
                        facility["schema:accessibilitySummary"]
                    ),
                    "address": format_address(address) or None,
                    "postal_code": clean(address.get("schema:postalCode")) or None,
                    "latitude": latitude,
                    "longitude": longitude,
                    "telephone": clean(facility["schema:telephone"]) or None,
                    "email": clean(facility["schema:email"]) or None,
                    "homepage": clean(facility["foaf:homepage"]) or None,
                    "source_url": source_url(facility["schema:mainEntityOfPage"]),
                    "opening_hours": clean(facility["schema:openingHours"]) or None,
                    "provider": clean(provider.get("schema:name")) or None,
                    "provider_type": clean(facility["cdf:parentOrgClassification"]) or None,
                }
            )

        return points

    def resolve_location(self, location: str) -> dict | None:
        """
        Turn a location into coordinates without calling an external service.

        Accepts "latitude,longitude", a postal code, or part of a street
        name. Postal codes and streets resolve to the average position of
        the known addresses that match.
        """

        text = location.strip()
        parts = [part.strip() for part in text.split(",")]

        if len(parts) == 2:
            latitude, longitude = to_float(parts[0]), to_float(parts[1])

            if latitude is not None and longitude is not None:
                return {
                    "latitude": latitude,
                    "longitude": longitude,
                    "matched_by": "coordinates",
                }

        addresses = [
            address
            for address in self.address_by_iri.values()
            if to_float(address.get("schema:latitude")) is not None
            and to_float(address.get("schema:longitude")) is not None
        ]

        if text.isdigit():
            matched_by = "postal_code"
            matches = [
                address
                for address in addresses
                if clean(address.get("schema:postalCode")) == text
            ]
        else:
            matched_by = "street"
            matches = [
                address
                for address in addresses
                if text.casefold()
                in clean(address.get("schema:streetAddress")).casefold()
            ]

        if not matches:
            return None

        return {
            "latitude": sum(
                to_float(address["schema:latitude"]) for address in matches
            ) / len(matches),
            "longitude": sum(
                to_float(address["schema:longitude"]) for address in matches
            ) / len(matches),
            "matched_by": matched_by,
            "matched_addresses": len(matches),
        }

    def find_nearby(
        self,
        location: str,
        radius_km: float = 2.0,
        query: str | None = None,
        accessible_only: bool = False,
        limit: int = 10,
    ) -> dict:
        """Find facilities within a radius of a location, nearest first."""

        origin = self.resolve_location(location)

        if origin is None:
            return {
                "location": location,
                "error": (
                    "Could not resolve the location. Use 'latitude,longitude', "
                    "a postal code, or a street name from the dataset."
                ),
                "results": [],
            }

        results = []

        for point in self.facility_points():
            if accessible_only and point["accessible"] is not True:
                continue

            if query and not matches_query(point, query):
                continue

            distance = haversine_km(
                origin["latitude"],
                origin["longitude"],
                point["latitude"],
                point["longitude"],
            )

            if distance > radius_km:
                continue

            results.append({**point, "distance_km": round(distance, 2)})

        results.sort(key=lambda point: point["distance_km"])

        return {
            "location": location,
            "origin": origin,
            "radius_km": radius_km,
            "total_found": len(results),
            "results": results[:limit],
        }


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def clean(value) -> str:
    """Return a stripped string, or "" for missing values."""

    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


def to_float(value) -> float | None:
    """Convert a value to float, or None if it is missing or invalid."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return None if math.isnan(number) else number


def first_line(value) -> str:
    """Return the first line of a multi-line cell."""

    return clean(value).splitlines()[0].strip() if clean(value) else ""


def source_url(value) -> str | None:
    """
    Return the facility's page in its source directory.

    Caritas entries are stored as relative redirect links
    ("/search.ashx?...&u=<real url>"), so the real URL is taken from "u".
    """

    text = clean(value)

    if text.startswith(("http://", "https://")):
        return text

    if text.startswith("/search.ashx"):
        target = parse_qs(urlparse(text).query).get("u", [""])[0]
        return target.split("?")[0] or None

    return None


def split_list(value) -> list[str]:
    """Split a comma-separated cell into a list of values."""

    return [part.strip() for part in clean(value).split(",") if part.strip()]


def format_address(address: dict) -> str:
    """Format an address record as "Street, Postal code City"."""

    street = clean(address.get("schema:streetAddress"))
    postal_code = clean(address.get("schema:postalCode"))
    city = clean(address.get("schema:addressLocality"))

    locality = " ".join(part for part in [postal_code, city] if part)

    return ", ".join(part for part in [street, locality] if part)


def accessibility_flag(summary) -> bool | None:
    """Read the accessibility sentence as True, False, or None if unknown."""

    text = clean(summary).casefold()

    if "nicht barrierefrei" in text:
        return False

    if "barrierefrei" in text:
        return True

    return None


FACILITY_GROUPS = [
    ("Suchthilfe", ["sucht", "drogen", "blaukreuz"]),
    ("Wohnungslosen- & Notfallhilfe", [
        "wohnungslos", "wohnungsnot", "obdach", "kältehilfe", "notübernachtung",
        "übergangshaus", "kleider",
    ]),
    ("Kinder & Jugend", [
        "kinder", "jugend", "schule", "kita", "familie", "eltern", "mütter",
    ]),
    ("Senioren & Pflege", ["senior", "pflege", "altenhilfe", "sgb xi"]),
    ("Behinderung & Teilhabe", ["behinder", "eingliederung"]),
    ("Migration", ["migration", "zugewandert", "flücht", "integration"]),
    ("Gesundheit", ["gesundheit", "krankenhaus", "klinik", "ambulanz", "psych"]),
    ("Beratung & soziale Hilfen", ["beratung", "soziale", "soziotherap", "wohn"]),
]


GROUP_LABELS_EN = {
    "Suchthilfe": "Addiction help",
    "Wohnungslosen- & Notfallhilfe": "Homelessness & emergency help",
    "Kinder & Jugend": "Children & youth",
    "Senioren & Pflege": "Seniors & care",
    "Behinderung & Teilhabe": "Disability & inclusion",
    "Migration": "Migration",
    "Gesundheit": "Health",
    "Beratung & soziale Hilfen": "Counseling & social help",
    "Sonstige": "Other",
}


def facility_group(facility, offers: list[dict] | None = None) -> str:
    """Assign a facility to one broad group for filtering and map colours."""

    if clean(facility["schema:audience"]):
        return "Suchthilfe"

    text = " ".join(
        [
            clean(facility[column])
            for column in ["schema:category", "schema:name", "schema:alternateName"]
        ]
        + [
            f"{offer['name']} {offer['category'] or ''}"
            for offer in offers or []
        ]
    ).casefold()

    for group, keywords in FACILITY_GROUPS:
        if any(keyword in text for keyword in keywords):
            return group

    return "Sonstige"


def matches_query(point: dict, query: str) -> bool:
    """
    Check whether any search term appears in a facility's descriptive fields.

    Separate several terms with commas ("Alkohol, Sucht"); a facility matches
    if it contains at least one of them.
    """

    text = " ".join(
        [
            point["name"],
            point["group"],
            point["group_en"],
            point["category"] or "",
            point["services"] or "",
            point["alternate_name"] or "",
            " ".join(
                f"{offer['name']} {offer['category'] or ''}"
                for offer in point["offers"]
            ),
            " ".join(point["audience"]),
        ]
    ).casefold()

    terms = [term.strip().casefold() for term in query.split(",") if term.strip()]

    return not terms or any(term in text for term in terms)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two points in kilometres."""

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )

    return 6371.0 * 2 * math.asin(math.sqrt(a))
