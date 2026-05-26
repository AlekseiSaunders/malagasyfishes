"""Darwin Core Archive export for GBIF publishing.

Implements TDWG's Darwin Core (DwC) standard so GBIF can ingest the
platform's species-locality data. The output is a Darwin Core Archive
(DwC-A) — a ZIP file containing:

    occurrence.txt    one row per locality, tab-separated
    eml.xml           Ecological Metadata Language: dataset metadata
    meta.xml          archive descriptor: column → DwC term mapping

GBIF's IPT (Integrated Publishing Toolkit) consumes this format directly.
For the platform's first GBIF integration, expose a public, no-auth
endpoint that returns the archive over HTTPS — the IPT will fetch and
re-publish.

Coordinate generalization
-------------------------

Per the platform's sensitive-data rules and GBIF best practice for
threatened species:

- Records on species marked sensitive (IUCN CR/EN/VU, or
  Species.location_sensitivity=override_sensitive, or per-record
  legacy is_sensitive=True) publish the **generalized** location
  (0.1° grid, ~11 km) with `coordinateUncertaintyInMeters=11000` and
  the DwC `dataGeneralizations` term set explaining why.
- Non-sensitive records publish exact coordinates with
  `coordinateUncertaintyInMeters` derived from `coordinate_precision`.
- Records with `needs_review=True` are excluded entirely from the
  archive (they are quarantined pending re-verification).

The platform's authenticated Tier 3+ surfaces continue to serve exact
coordinates; this module is the *public* publication path only.

References
----------

- DwC quick reference: https://dwc.tdwg.org/terms/
- GBIF sensitive-species protocol: https://docs.gbif.org/sensitive-species
- DwC-A specification: https://dwc.tdwg.org/text/
- EML 2.1.1: https://eml.ecoinformatics.org/
"""

from __future__ import annotations

import datetime
import io
import zipfile
from collections.abc import Iterable
from typing import TypedDict
from xml.sax.saxutils import escape as xml_escape

from django.conf import settings
from django.db.models import QuerySet

from species.models import Species, SpeciesLocality

# Dataset identity. These are visible in GBIF's portal once published, so
# wording matters; keep them aligned with the About-page copy.
DATASET_TITLE = "Malagasy Freshwater Fishes — Endemic Species Occurrences"
DATASET_SHORTNAME = "mffcp-occurrences"
DATASET_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DATASET_LICENSE_NAME = "Creative Commons Attribution 4.0 International (CC BY 4.0)"
DATASET_LANGUAGE = "en"
DATASET_RIGHTS_HOLDER = "Malagasy Freshwater Fishes Conservation Platform"
DATASET_PUBLISHER = "Malagasy Freshwater Fishes Conservation Platform"
DEFAULT_CONTACT_EMAIL = "alekseisaunders@gmail.com"
DEFAULT_CONTACT_NAME = "Aleksei Saunders"

GENERALIZATION_NOTE = (
    "Coordinates generalized to a 0.1° (≈11 km) grid for IUCN-threatened "
    "species per GBIF sensitive-species best practice. Exact coordinates "
    "are available to authenticated platform coordinators upon request."
)

GENERALIZED_UNCERTAINTY_M = 11_000  # 0.1° at the equator

# Map our coordinate-precision enum onto a defensible
# `coordinateUncertaintyInMeters`. Conservative — these are
# upper bounds, not measurements.
PRECISION_TO_UNCERTAINTY_M: dict[str, int] = {
    SpeciesLocality.CoordinatePrecision.EXACT: 100,
    SpeciesLocality.CoordinatePrecision.APPROXIMATE: 1_000,
    SpeciesLocality.CoordinatePrecision.LOCALITY_CENTROID: 5_000,
    SpeciesLocality.CoordinatePrecision.WATER_BODY_CENTROID: 10_000,
}

# Map our locality_type enum onto DwC `basisOfRecord`.
# DwC values are constrained — pick the closest match.
LOCALITY_TYPE_TO_BASIS: dict[str, str] = {
    SpeciesLocality.LocalityType.TYPE_LOCALITY: "PreservedSpecimen",
    SpeciesLocality.LocalityType.COLLECTION_RECORD: "PreservedSpecimen",
    SpeciesLocality.LocalityType.LITERATURE_RECORD: "MaterialCitation",
    SpeciesLocality.LocalityType.OBSERVATION: "HumanObservation",
}

# `occurrenceStatus` mapping. Most rows are `present`; extirpated
# historical records publish as `absent`.
PRESENCE_TO_OCCURRENCE_STATUS: dict[str, str] = {
    SpeciesLocality.PresenceStatus.PRESENT: "present",
    SpeciesLocality.PresenceStatus.HISTORICALLY_PRESENT_EXTIRPATED: "absent",
    SpeciesLocality.PresenceStatus.PRESENCE_UNKNOWN: "present",  # GBIF demands one
    SpeciesLocality.PresenceStatus.REINTRODUCED: "present",
}


# ---------------------------------------------------------------------------
# Column order — drives both occurrence.txt header AND meta.xml field index
# ---------------------------------------------------------------------------

# `occurrenceID` MUST be index 0 (DwC-A convention; meta.xml's `id` element
# points at it). Order beyond that is stable but not semantically loaded.
DWC_COLUMNS: tuple[str, ...] = (
    "occurrenceID",
    "basisOfRecord",
    "occurrenceStatus",
    "eventDate",
    "year",
    "recordedBy",
    "country",
    "countryCode",
    "decimalLatitude",
    "decimalLongitude",
    "geodeticDatum",
    "coordinateUncertaintyInMeters",
    "coordinatePrecision",
    "locality",
    "waterBody",
    "scientificName",
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "specificEpithet",
    "taxonRank",
    "iucnRedListCategory",
    "dataGeneralizations",
    "informationWithheld",
    "references",
    "modified",
)


class DwcRow(TypedDict, total=False):
    occurrenceID: str
    basisOfRecord: str
    occurrenceStatus: str
    eventDate: str
    year: str
    recordedBy: str
    country: str
    countryCode: str
    decimalLatitude: str
    decimalLongitude: str
    geodeticDatum: str
    coordinateUncertaintyInMeters: str
    coordinatePrecision: str
    locality: str
    waterBody: str
    scientificName: str
    kingdom: str
    phylum: str
    order: str
    family: str
    genus: str
    specificEpithet: str
    taxonRank: str
    iucnRedListCategory: str
    dataGeneralizations: str
    informationWithheld: str
    references: str
    modified: str


# Use class_/order_ key names to avoid Python keywords; `class` written via
# dict assignment inside `locality_to_dwc_row` since TypedDict doesn't allow
# a `class` attribute name.


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


def locality_to_dwc_row(locality: SpeciesLocality) -> dict[str, str]:
    """Map one SpeciesLocality to a DwC row dict.

    Generalization decision: any of (1) species IUCN status in CR/EN/VU,
    (2) species.location_sensitivity == override_sensitive, (3) per-row
    is_sensitive=True flips the record to generalized output. Caller is
    responsible for excluding records with needs_review=True.
    """
    species: Species = locality.species
    sensitive = locality.effective_is_sensitive

    if sensitive and locality.location_generalized is not None:
        point = locality.location_generalized
        uncertainty_m = GENERALIZED_UNCERTAINTY_M
        data_generalizations = GENERALIZATION_NOTE
        information_withheld = "Exact coordinates withheld for sensitive species."
    else:
        point = locality.location
        uncertainty_m = PRECISION_TO_UNCERTAINTY_M.get(str(locality.coordinate_precision), 1_000)
        data_generalizations = ""
        information_withheld = ""

    # PointField stores (x=longitude, y=latitude) per OGC convention.
    longitude = float(point.x) if point is not None else None
    latitude = float(point.y) if point is not None else None

    species_epithet = ""
    parts = species.scientific_name.split(maxsplit=1)
    if len(parts) > 1:
        species_epithet = parts[1].split(maxsplit=1)[0]  # drop subspecies if any

    event_date = ""
    year = ""
    if locality.year_collected:
        year = str(locality.year_collected)
        event_date = year  # ISO 8601 allows year-only as a valid eventDate

    references = locality.source_citation or ""
    modified = locality.updated_at.isoformat() if locality.updated_at else ""

    row: dict[str, str] = {
        "occurrenceID": _occurrence_id(locality),
        "basisOfRecord": LOCALITY_TYPE_TO_BASIS.get(str(locality.locality_type), "Occurrence"),
        "occurrenceStatus": PRESENCE_TO_OCCURRENCE_STATUS.get(
            str(locality.presence_status), "present"
        ),
        "eventDate": event_date,
        "year": year,
        "recordedBy": locality.collector or "",
        "country": "Madagascar",
        "countryCode": "MG",
        "decimalLatitude": f"{latitude:.5f}" if latitude is not None else "",
        "decimalLongitude": f"{longitude:.5f}" if longitude is not None else "",
        "geodeticDatum": "EPSG:4326",
        "coordinateUncertaintyInMeters": str(uncertainty_m),
        "coordinatePrecision": "",
        "locality": locality.locality_name or "",
        "waterBody": locality.water_body or "",
        "scientificName": species.scientific_name,
        "kingdom": "Animalia",
        "phylum": "Chordata",
        "class": "Actinopterygii",
        "order": "",  # not stored on Species; left blank per DwC tolerance
        "family": species.family or "",
        "genus": species.genus or "",
        "specificEpithet": species_epithet,
        "taxonRank": "species",
        "iucnRedListCategory": species.iucn_status or "",
        "dataGeneralizations": data_generalizations,
        "informationWithheld": information_withheld,
        "references": references,
        "modified": modified,
    }
    return row


def _occurrence_id(locality: SpeciesLocality) -> str:
    """Globally unique, stable occurrence identifier per GBIF guidance.

    Format: ``mffcp:locality:<pk>``. Stays stable as long as the row's
    primary key is stable (which it is — soft-deletes are not used in
    SpeciesLocality).
    """
    return f"mffcp:locality:{locality.pk}"


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _tsv_escape(value: str) -> str:
    """Tab/newline → space, no quoting (DwC-A is plain TSV).

    Per DwC-A spec, tabs and newlines inside a field must be replaced or
    the row delimiters break. We replace them with spaces — preserving
    the textual content — rather than escape, since GBIF's parsers don't
    consistently handle TSV escaping.
    """
    if not value:
        return ""
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def render_occurrence_tsv(rows: Iterable[dict[str, str]]) -> str:
    """Render rows to a tab-separated `occurrence.txt` body.

    First line is the header (column names per DWC_COLUMNS); subsequent
    lines are values in the same column order. Empty values render as
    empty cells (DwC-A treats blank == not provided).
    """
    out = io.StringIO()
    out.write("\t".join(DWC_COLUMNS))
    out.write("\n")
    for row in rows:
        out.write("\t".join(_tsv_escape(row.get(col, "")) for col in DWC_COLUMNS))
        out.write("\n")
    return out.getvalue()


def render_meta_xml() -> str:
    """Generate ``meta.xml`` — the DwC-A descriptor.

    Pinpoints `occurrence.txt` as the core file, declares the column
    index for each DwC term, and references the row-key column. GBIF's
    IPT validates against this on ingest.
    """
    fields_xml = []
    for index, column in enumerate(DWC_COLUMNS):
        if column == "occurrenceID":
            # The id element below points at index 0; field tag also needs to
            # be present so DwC-A tooling sees the term name.
            fields_xml.append(
                f'    <field index="{index}" term="http://rs.tdwg.org/dwc/terms/{column}"/>'
            )
            continue
        # `class` is a Python keyword in the column list but DwC's term URI
        # is the unprefixed name.
        term_name = column
        fields_xml.append(
            f'    <field index="{index}" term="http://rs.tdwg.org/dwc/terms/{term_name}"/>'
        )
    fields_block = "\n".join(fields_xml)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<archive xmlns="http://rs.tdwg.org/dwc/text/" metadata="eml.xml">
  <core encoding="UTF-8"
        linesTerminatedBy="\\n"
        fieldsTerminatedBy="\\t"
        fieldsEnclosedBy=""
        ignoreHeaderLines="1"
        rowType="http://rs.tdwg.org/dwc/terms/Occurrence">
    <files>
      <location>occurrence.txt</location>
    </files>
    <id index="0"/>
{fields_block}
  </core>
</archive>
"""


def render_eml_xml(
    *,
    record_count: int,
    contact_name: str = DEFAULT_CONTACT_NAME,
    contact_email: str = DEFAULT_CONTACT_EMAIL,
    homepage_url: str | None = None,
    pub_date: datetime.date | None = None,
) -> str:
    """Generate ``eml.xml`` — Ecological Metadata Language.

    Describes the dataset: title, abstract, contact, license, geographic
    coverage, taxonomic coverage, methods. GBIF's portal renders this on
    the published dataset page, so wording is publicly visible.

    `record_count` is interpolated into the abstract so a researcher
    glancing at the GBIF page sees the dataset size without downloading.
    """
    homepage = homepage_url or _frontend_url()
    pub_date = pub_date or datetime.date.today()
    pub_date_iso = pub_date.isoformat()

    title = xml_escape(DATASET_TITLE)
    abstract = xml_escape(
        f"Occurrence records ({record_count:,}) for Madagascar's endemic "
        "freshwater fish, drawn from the Malagasy Freshwater Fishes "
        "Conservation Platform's curated species-locality registry. "
        "Records on IUCN-threatened species (CR, EN, VU) publish with "
        "coordinates generalized to a 0.1° (~11 km) grid per GBIF "
        "sensitive-species best practice; non-threatened records publish "
        "with the highest precision the source supports. The platform "
        "complements rather than replaces ZIMS, IUCN Red List, FishBase, "
        "and GBIF — this dataset is the platform's contribution back."
    )
    license_name = xml_escape(DATASET_LICENSE_NAME)
    license_url = xml_escape(DATASET_LICENSE_URL)
    rights_holder = xml_escape(DATASET_RIGHTS_HOLDER)
    publisher = xml_escape(DATASET_PUBLISHER)
    contact_name_x = xml_escape(contact_name)
    contact_email_x = xml_escape(contact_email)
    homepage_x = xml_escape(homepage)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.1.1"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://eml.ecoinformatics.org/eml-2.1.1 https://eml.ecoinformatics.org/eml-2.1.1/eml.xsd"
         packageId="{DATASET_SHORTNAME}/{pub_date_iso}"
         system="mffcp"
         scope="system"
         xml:lang="{DATASET_LANGUAGE}">
  <dataset>
    <alternateIdentifier>{DATASET_SHORTNAME}</alternateIdentifier>
    <title xml:lang="{DATASET_LANGUAGE}">{title}</title>
    <creator>
      <organizationName>{publisher}</organizationName>
      <electronicMailAddress>{contact_email_x}</electronicMailAddress>
      <onlineUrl>{homepage_x}</onlineUrl>
    </creator>
    <pubDate>{pub_date_iso}</pubDate>
    <language>{DATASET_LANGUAGE}</language>
    <abstract>
      <para>{abstract}</para>
    </abstract>
    <keywordSet>
      <keyword>Madagascar</keyword>
      <keyword>freshwater fish</keyword>
      <keyword>endemic species</keyword>
      <keyword>IUCN Red List</keyword>
      <keyword>conservation</keyword>
      <keywordThesaurus>n/a</keywordThesaurus>
    </keywordSet>
    <intellectualRights>
      <para>This work is licensed under a {license_name}. License URL: {license_url}.</para>
    </intellectualRights>
    <distribution scope="document">
      <online>
        <url function="information">{homepage_x}</url>
      </online>
    </distribution>
    <coverage>
      <geographicCoverage>
        <geographicDescription>
          Madagascar (mainland and surrounding inland waters)
        </geographicDescription>
        <boundingCoordinates>
          <westBoundingCoordinate>43.2</westBoundingCoordinate>
          <eastBoundingCoordinate>50.5</eastBoundingCoordinate>
          <northBoundingCoordinate>-11.9</northBoundingCoordinate>
          <southBoundingCoordinate>-25.6</southBoundingCoordinate>
        </boundingCoordinates>
      </geographicCoverage>
      <taxonomicCoverage>
        <generalTaxonomicCoverage>
          Endemic freshwater fish of Madagascar (Actinopterygii)
        </generalTaxonomicCoverage>
        <taxonomicClassification>
          <taxonRankName>class</taxonRankName>
          <taxonRankValue>Actinopterygii</taxonRankValue>
        </taxonomicClassification>
      </taxonomicCoverage>
    </coverage>
    <contact>
      <individualName>
        <surName>{contact_name_x}</surName>
      </individualName>
      <organizationName>{publisher}</organizationName>
      <electronicMailAddress>{contact_email_x}</electronicMailAddress>
    </contact>
    <additionalInfo>
      <para>Rights holder: {rights_holder}.</para>
    </additionalInfo>
  </dataset>
</eml:eml>
"""


def _frontend_url() -> str:
    return getattr(settings, "FRONTEND_BASE_URL", "https://malagasyfishes.org")


# ---------------------------------------------------------------------------
# Archive assembly
# ---------------------------------------------------------------------------


def published_localities_queryset() -> QuerySet[SpeciesLocality]:
    """Queryset of localities that publish to GBIF.

    Excludes:
    - `needs_review=True` (quarantined; awaiting source re-verification)
    - `species.taxonomic_status='undescribed'` rows where the
      species's `provisional_name` is empty (no name to publish under)
    """
    return (
        SpeciesLocality.objects.select_related("species")
        .filter(needs_review=False)
        .exclude(species__taxonomic_status="undescribed", species__provisional_name="")
    )


def build_archive_bytes(
    *,
    contact_name: str = DEFAULT_CONTACT_NAME,
    contact_email: str = DEFAULT_CONTACT_EMAIL,
    homepage_url: str | None = None,
    pub_date: datetime.date | None = None,
) -> bytes:
    """Build a complete DwC-A as a ZIP byte-string.

    Single allocation — fine for the size of the platform's dataset
    (~hundreds to low thousands of records). If volume grows, swap in
    a streaming response that writes each section to the wire as it's
    generated.
    """
    qs = published_localities_queryset()
    rows = [locality_to_dwc_row(loc) for loc in qs.iterator()]
    occurrence_tsv = render_occurrence_tsv(rows)
    eml_xml = render_eml_xml(
        record_count=len(rows),
        contact_name=contact_name,
        contact_email=contact_email,
        homepage_url=homepage_url,
        pub_date=pub_date,
    )
    meta_xml = render_meta_xml()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("occurrence.txt", occurrence_tsv)
        zf.writestr("eml.xml", eml_xml)
        zf.writestr("meta.xml", meta_xml)
    return buf.getvalue()
