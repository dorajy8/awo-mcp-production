import os
from pathlib import Path

import pandas as pd
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import FOAF, RDF


SCHEMA = Namespace("http://schema.org/")
CDF = Namespace("https://civic-data.de/federated-directory#")
ORG = Namespace("http://www.w3.org/ns/org#")


# RDF type and properties for each dataset. Column names match the CSV
# exports so DataRepository works the same with either source.
RDF_DATASETS = {
    "einrichtung": (
        ORG.OrganizationalUnit,
        {
            "schema:name": SCHEMA.name,
            "schema:alternateName": SCHEMA.alternateName,
            "schema:telephone": SCHEMA.telephone,
            "schema:email": SCHEMA.email,
            "foaf:homepage": FOAF.homepage,
            "schema:mainEntityOfPage": SCHEMA.mainEntityOfPage,
            "schema:category": SCHEMA.category,
            "schema:availableService": SCHEMA.availableService,
            "schema:audience": SCHEMA.audience,
            "schema:accessibilitySummary": SCHEMA.accessibilitySummary,
            "schema:openingHours": SCHEMA.openingHours,
            "schema:parentOrganization": SCHEMA.parentOrganization,
            "cdf:parentOrgClassification": CDF.parentOrgClassification,
            "schema:address": SCHEMA.address,
        },
    ),
    "adresse": (
        SCHEMA.PostalAddress,
        {
            "schema:streetAddress": SCHEMA.streetAddress,
            "schema:postalCode": SCHEMA.postalCode,
            "schema:addressLocality": SCHEMA.addressLocality,
            "schema:addressCountry": SCHEMA.addressCountry,
            "schema:latitude": SCHEMA.latitude,
            "schema:longitude": SCHEMA.longitude,
        },
    ),
    "angebot": (
        SCHEMA.Service,
        {
            "schema:name": SCHEMA.name,
            "schema:category": SCHEMA.category,
            "schema:codeValue": SCHEMA.codeValue,
            "schema:audience": SCHEMA.audience,
            "schema:areaServed": SCHEMA.areaServed,
            "schema:openingHours": SCHEMA.openingHours,
            "schema:provider": SCHEMA.provider,
        },
    ),
    "traeger": (
        SCHEMA.Organization,
        {
            "schema:name": SCHEMA.name,
            "foaf:homepage": FOAF.homepage,
            "schema:address": SCHEMA.address,
        },
    ),
}

NUMERIC_COLUMNS = ["schema:latitude", "schema:longitude"]


def resolve_source(base_dir: Path) -> str:
    """
    Return the data source to load.

    Uses the AWO_DATA_SOURCE environment variable (a .ttl path or URL, or a
    CSV directory) and falls back to a local data/directory.ttl copy.
    """

    source = os.environ.get("AWO_DATA_SOURCE")

    if source:
        return source

    local_copy = base_dir / "data" / "directory.ttl"

    if local_copy.exists():
        return str(local_copy)

    raise SystemExit(
        "No data source configured. Set AWO_DATA_SOURCE to the federated "
        "directory's Turtle (.ttl) URL or file path, or place a local copy "
        f"at {local_copy}."
    )


class DataLoader:
    """
    Loads the AWO datasets.

    The source can be:
    - a Turtle (.ttl) file path or URL from the civic-data.de federated
      directory, or
    - a directory containing the four CSV exports (legacy).
    """

    def __init__(self, source: str | Path):
        self.source = str(source)

    def load_all(self) -> dict[str, pd.DataFrame]:
        """Load all four AWO datasets."""

        if Path(self.source).is_dir():
            return self.load_csv_directory(Path(self.source))

        return self.load_rdf(self.source)

    # --------------------------------------------------
    # RDF (Turtle)
    # --------------------------------------------------

    def load_rdf(self, source: str) -> dict[str, pd.DataFrame]:
        """Load the datasets from a Turtle file path or URL."""

        graph = Graph()
        graph.parse(source, format="turtle")

        return {
            name: rdf_frame(graph, rdf_type, columns)
            for name, (rdf_type, columns) in RDF_DATASETS.items()
        }

    # --------------------------------------------------
    # CSV (legacy)
    # --------------------------------------------------

    def load_csv_directory(self, data_dir: Path) -> dict[str, pd.DataFrame]:
        """Load the datasets from the four CSV exports in a directory."""

        return {
            "angebot": pd.read_csv(
                data_dir / "angebotSchema.csv",
                encoding="utf-8",
            ),
            "adresse": pd.read_csv(
                data_dir / "adresseSchema.csv",
                encoding="utf-8",
                dtype={"schema:postalCode": str},
            ),
            "einrichtung": pd.read_csv(
                data_dir / "einrichtungSchema.csv",
                encoding="utf-8",
                dtype={"schema:telephone": str},
            ),
            "traeger": pd.read_csv(
                data_dir / "traegerSchema.csv",
                encoding="utf-8",
            ),
        }


def rdf_frame(
    graph: Graph,
    rdf_type: URIRef,
    columns: dict[str, URIRef],
) -> pd.DataFrame:
    """Build one table from all subjects of a type, one column per property."""

    rows = []

    for subject in sorted(graph.subjects(RDF.type, rdf_type)):
        row = {"iri": str(subject)}

        for column, predicate in columns.items():
            values = sorted(str(value) for value in graph.objects(subject, predicate))

            if values:
                row[column] = ", ".join(values)

        rows.append(row)

    frame = pd.DataFrame(rows, columns=["iri", *columns])

    for column in NUMERIC_COLUMNS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    return frame
