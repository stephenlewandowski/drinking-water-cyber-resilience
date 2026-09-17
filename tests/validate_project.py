#!/usr/bin/env python3
"""Validate the static IDEA-0001 consequence-path released exhibit."""

from __future__ import annotations

import csv
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROJECT_README = ROOT / "README.md"
RELEASE_REVIEW = ROOT / "reports" / "IDEA-0001-consequence-path-release-review-2026-08-13.md"
RELEASE_RECORD = ROOT / "published" / "projects" / "IDEA-0001-consequence-path-v0.3.md"
PUBLICATIONS = ROOT / "data" / "publications.csv"
REPOSITORY_SOURCES = ROOT / "data" / "sources.csv"

STAGE_HEADERS = [
    "stage_id",
    "display_order",
    "stage_name",
    "decision_question",
    "evidence_class",
    "documented_or_proposed_content",
    "source_ids",
    "evidence_scope",
    "interpretation_limit",
    "resilience_function",
]

SOURCE_HEADERS = [
    "source_id",
    "title",
    "organization",
    "publication_date",
    "url",
    "role_in_prototype",
    "scope_limit",
    "register_verification_status",
    "last_direct_check",
]

ALLOWED_SOURCE_IDS = {"SRC-0001", "SRC-0002", "SRC-0003", "SRC-0004", "SRC-0005", "SRC-0007", "SRC-0008", "SRC-0009"}
ALLOWED_HOSTS = {"www.fbi.gov", "www.epa.gov", "mn.gov", "www.plymouthmn.gov", "csrc.nist.gov"}
PROHIBITED_HOSTS = {"nypost.com", "www.nypost.com"}
EVIDENCE_CLASSES = {
    "documented_aggregate",
    "documented_case",
    "bounded_synthesis",
    "analytic_question",
}


def load_csv(path: Path, expected_headers: list[str], errors: list[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != expected_headers:
                errors.append(f"{path.name}: header mismatch")
                return []
            rows = []
            for line_number, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    errors.append(f"{path.name}:{line_number}: malformed CSV row")
                    continue
                cleaned = {key: value.strip() for key, value in row.items()}
                cleaned["__line__"] = str(line_number)
                rows.append(cleaned)
            return rows
    except (OSError, csv.Error, UnicodeError) as exc:
        errors.append(f"{path.name}: could not parse: {exc}")
        return []


def check_iso_date(value: str, location: str, errors: list[str]) -> None:
    if not value:
        return
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors.append(f"{location}: invalid ISO date {value!r}")
        return
    if parsed.isoformat() != value:
        errors.append(f"{location}: date must use YYYY-MM-DD")


def main() -> int:
    errors: list[str] = []
    stages = load_csv(DATA / "path-stages.csv", STAGE_HEADERS, errors)
    sources = load_csv(DATA / "source-snapshot.csv", SOURCE_HEADERS, errors)

    try:
        project_readme = PROJECT_README.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"README.md: could not read project page: {exc}")
        project_readme = ""

    try:
        release_review = RELEASE_REVIEW.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"release-review record: could not read: {exc}")
        release_review = ""

    try:
        release_record = RELEASE_RECORD.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"release record: could not read: {exc}")
        release_record = ""

    try:
        with PUBLICATIONS.open("r", encoding="utf-8", newline="") as handle:
            publications = list(csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeError) as exc:
        errors.append(f"publications register could not be read: {exc}")
        publications = []

    try:
        with REPOSITORY_SOURCES.open("r", encoding="utf-8", newline="") as handle:
            repository_sources = {
                row["source_id"]: row for row in csv.DictReader(handle) if row.get("source_id")
            }
    except (OSError, csv.Error, UnicodeError, KeyError) as exc:
        errors.append(f"repository sources register could not be read: {exc}")
        repository_sources = {}

    source_ids = {row["source_id"] for row in sources}
    if source_ids != ALLOWED_SOURCE_IDS:
        errors.append(
            "source-snapshot.csv: source set must be exactly "
            + ", ".join(sorted(ALLOWED_SOURCE_IDS))
        )

    seen_source_ids: set[str] = set()
    for row in sources:
        line = row["__line__"]
        source_id = row["source_id"]
        if not re.fullmatch(r"SRC-\d{4}", source_id):
            errors.append(f"source-snapshot.csv:{line}: invalid source ID {source_id!r}")
        if source_id in seen_source_ids:
            errors.append(f"source-snapshot.csv:{line}: duplicate source ID {source_id}")
        seen_source_ids.add(source_id)
        if row["register_verification_status"] != "verified":
            errors.append(f"source-snapshot.csv:{line}: source is not register-verified")
        registered = repository_sources.get(source_id)
        if registered is None:
            errors.append(
                f"source-snapshot.csv:{line}: {source_id} is absent from data/sources.csv"
            )
        else:
            for snapshot_field, register_field in (
                ("title", "title"),
                ("organization", "organization"),
                ("publication_date", "publication_date"),
                ("url", "url_or_location"),
                ("register_verification_status", "verification_status"),
            ):
                if row[snapshot_field] != registered.get(register_field, "").strip():
                    errors.append(
                        f"source-snapshot.csv:{line}: {snapshot_field} disagrees with "
                        f"data/sources.csv for {source_id}"
                    )
        check_iso_date(
            row["publication_date"],
            f"source-snapshot.csv:{line}:publication_date",
            errors,
        )
        check_iso_date(
            row["last_direct_check"],
            f"source-snapshot.csv:{line}:last_direct_check",
            errors,
        )
        parsed = urlparse(row["url"])
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            errors.append(f"source-snapshot.csv:{line}: URL must use HTTPS")
        if host in PROHIBITED_HOSTS:
            errors.append(f"source-snapshot.csv:{line}: prohibited source host {host}")
        if host not in ALLOWED_HOSTS:
            errors.append(f"source-snapshot.csv:{line}: unapproved source host {host!r}")

    if "Static released exhibit v0.3" not in project_readme:
        errors.append("README.md: missing v0.3 released-exhibit label")
    if "- Status: released" not in project_readme:
        errors.append("README.md: missing released status")
    if "Release-review record:" not in project_readme or "Release record:" not in project_readme:
        errors.append("README.md: missing release record links")
    if "PUB-0001" not in project_readme:
        errors.append("README.md: missing PUB-0001 reference")
    for marker in (
        "Release state: released",
        "Release decision: AUTHORIZE STATIC RELEASE",
        "New York Post",
    ):
        if marker not in release_record:
            errors.append(f"release record: missing {marker!r}")
    if "not released or approved for publication" in project_readme:
        errors.append("README.md: stale unreleased gate remains")
    if project_readme.count("```mermaid") != 1:
        errors.append("README.md: expected exactly one Mermaid diagram")
    if "No interaction or animation was added to v0.3" not in project_readme:
        errors.append("README.md: static v0.3 interaction decision is not explicit")
    if "v0.4 evidence-lens enhancement" not in project_readme:
        errors.append("README.md: missing v0.4 evidence-lens draft marker")
    if "bounded evidence-class filter" not in project_readme:
        errors.append("README.md: missing bounded evidence-class filter decision")

    publication = next(
        (row for row in publications if row.get("publication_id") == "PUB-0001"),
        None,
    )
    if publication is None:
        errors.append("publications.csv: missing PUB-0001 release row")
    else:
        for field, expected in (
            ("idea_id", "IDEA-0001"),
            ("format", "mixed_media_project"),
            ("publication_date", "2026-08-13"),
            ("version", "v0.3"),
        ):
            if publication.get(field, "").strip() != expected:
                errors.append(
                    f"publications.csv: PUB-0001 {field} must be {expected!r}"
                )
        check_iso_date(
            publication.get("publication_date", "").strip(),
            "publications.csv:PUB-0001:publication_date",
            errors,
        )
        if not publication.get("url", "").startswith(
            "https://github.com/stephenlewandowski/current-events-km/"
        ):
            errors.append("publications.csv: PUB-0001 URL must point to the release archive")
        if "static release" not in publication.get("notes", "").lower():
            errors.append("publications.csv: PUB-0001 notes must describe the static release")

    lowered_readme = project_readme.lower()
    if "<script" in lowered_readme or "javascript:" in lowered_readme:
        errors.append("README.md: executable client-side content is not allowed")

    snapshot_by_id = {row["source_id"]: row for row in sources}
    for source_id in sorted(ALLOWED_SOURCE_IDS):
        links = re.findall(
            rf"\[{re.escape(source_id)}\]\((https://[^)]+)\)", project_readme
        )
        if not links:
            errors.append(f"README.md: no source link found for {source_id}")
            continue
        expected_url = snapshot_by_id.get(source_id, {}).get("url", "")
        for link in links:
            if link != expected_url:
                errors.append(
                    f"README.md: {source_id} link disagrees with source snapshot"
                )

    for link in re.findall(r"\]\((https://[^)]+)\)", project_readme):
        host = (urlparse(link).hostname or "").lower()
        if host in PROHIBITED_HOSTS:
            errors.append(f"README.md: prohibited source host {host}")
        if host not in ALLOWED_HOSTS:
            errors.append(f"README.md: unapproved external source host {host!r}")

    seen_stage_ids: set[str] = set()
    for row in stages:
        line = row["__line__"]
        stage_id = row["stage_id"]
        if not re.fullmatch(r"PATH-\d{2}[A-Z]?", stage_id):
            errors.append(f"path-stages.csv:{line}: invalid stage ID {stage_id!r}")
        if stage_id in seen_stage_ids:
            errors.append(f"path-stages.csv:{line}: duplicate stage ID {stage_id}")
        seen_stage_ids.add(stage_id)
        try:
            order = int(row["display_order"])
            if order < 1 or order > 6:
                raise ValueError
        except ValueError:
            errors.append(f"path-stages.csv:{line}: display_order must be 1 through 6")
        if row["evidence_class"] not in EVIDENCE_CLASSES:
            errors.append(
                f"path-stages.csv:{line}: invalid evidence class {row['evidence_class']!r}"
            )
        linked_ids = [item.strip() for item in row["source_ids"].split(";") if item.strip()]
        if not linked_ids:
            errors.append(f"path-stages.csv:{line}: source_ids must not be blank")
        for source_id in linked_ids:
            if source_id not in source_ids:
                errors.append(
                    f"path-stages.csv:{line}: unknown source reference {source_id}"
                )
        for required_field in (
            "stage_name",
            "decision_question",
            "documented_or_proposed_content",
            "evidence_scope",
            "interpretation_limit",
            "resilience_function",
        ):
            if not row[required_field]:
                errors.append(f"path-stages.csv:{line}: {required_field} must not be blank")

    if len(stages) != 7:
        errors.append(f"path-stages.csv: expected 7 rows, found {len(stages)}")

    if errors:
        print("PROJECT VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PROJECT VALIDATION: PASS")
    print(f"- consequence-path rows: {len(stages)}")
    print(f"- source snapshot rows: {len(sources)}")
    print("- stage and source IDs: unique and correctly formatted")
    print("- source references: valid")
    print("- public source snapshot: matches authoritative source register")
    print("- evidence classes and dates: valid")
    print("- source hosts: approved primary government sources only")
    print("- project page: source-linked, release-record gated, and v0.4 interaction decision recorded")
    print("- executable client-side interaction: absent from the authoritative README; website filter is a separately reviewed progressive enhancement")
    return 0


if __name__ == "__main__":
    sys.exit(main())
