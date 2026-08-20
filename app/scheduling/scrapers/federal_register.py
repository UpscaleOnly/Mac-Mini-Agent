"""
app/scheduling/scrapers/federal_register.py — Federal Register API scraper

First scraper for the federal_policy_brief project (ADR-039 H4).
Targets the federalregister.gov REST API — no HTML parsing.

API reference: https://www.federalregister.gov/developers/documentation/api/v1

Query strategy:
  - Loop over TARGET_AGENCIES (6 agencies relevant to federal_policy_brief)
  - For each, fetch documents published in the last `days_back` days
  - Filter by document type (RULE, PRORULE, NOTICE, PRESDOCU)
  - One agency failing does not abort the run — base class records 'partial'

TYPE HANDLING (fixed August 20, 2026 — Entry #019)
  The Federal Register API uses two different vocabularies for document type:
    - QUERY-FILTER codes, which we SEND:      RULE, PRORULE, NOTICE, PRESDOCU
    - DISPLAY strings, which it RETURNS:      "Rule", "Proposed Rule",
                                              "Notice", "Presidential Document"
  The original TYPE_MAP was keyed only on the filter codes but applied to the
  returned display strings. Uppercased, "RULE" and "NOTICE" matched by
  coincidence; "PROPOSED RULE" and "PRESIDENTIAL DOCUMENT" matched nothing and
  fell through to 'other'. Consequence: no proposed rule anywhere in
  scraped_content was labeled as one — including the CY2027 HH PPS rate update,
  the highest-signal item in the set — and each briefed as "a document."

  TYPE_MAP now accepts BOTH vocabularies, so a future change in which form the
  API returns cannot silently reintroduce the defect. Anything unrecognized is
  logged at WARNING with its document number before being stored as 'other' —
  a third vocabulary would surface in `docker logs openclaw_fastapi` instead of
  quietly degrading the brief.

Persona: Automate
Project: federal_policy_brief
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.scheduling.scrapers.base import (
    BaseScraper,
    ScrapedRow,
    _FatalError,
)

log = logging.getLogger(__name__)


class FederalRegisterScraper(BaseScraper):
    # --- Required attributes ------------------------------------------------
    scraper_name = "federal_register"
    source_domain = "federalregister.gov"
    project = "federal_policy_brief"

    # --- Constants ----------------------------------------------------------
    FR_API_BASE = "https://www.federalregister.gov/api/v1"

    TARGET_AGENCIES = [
        "health-and-human-services-department",
        "centers-for-medicare-medicaid-services",
        "agriculture-department",
        "children-and-families-administration",
        "internal-revenue-service",
        "social-security-administration",
    ]

    TARGET_TYPES = ["RULE", "PRORULE", "NOTICE", "PRESDOCU"]

    # Keys are compared after .strip().upper(), so every key here is uppercase.
    # See the TYPE HANDLING note in the module docstring — both the API's
    # query-filter codes and its returned display strings must be present.
    TYPE_MAP = {
        # Query-filter codes (what we send in conditions[type][])
        "RULE": "final_rule",
        "PRORULE": "proposed_rule",
        "NOTICE": "notice",
        "PRESDOCU": "presidential_document",
        # Returned display strings (what the API actually gives back)
        "FINAL RULE": "final_rule",
        "PROPOSED RULE": "proposed_rule",
        "PRESIDENTIAL DOCUMENT": "presidential_document",
    }

    REQUESTED_FIELDS = [
        "document_number",
        "title",
        "type",
        "abstract",
        "agency_names",
        "publication_date",
        "html_url",
    ]

    PER_PAGE = 100

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(self, days_back: int = 1):
        """
        days_back — how many days back from now to fetch.
        Default 1 means 'yesterday and today' which is right for a daily 01:00 ET run.
        """
        self.days_back = days_back

    # ------------------------------------------------------------------
    # fetch() — required by BaseScraper
    # ------------------------------------------------------------------

    def fetch(self) -> list[dict]:
        """
        Query the Federal Register API once per agency.
        Returns a flat list of result dicts.
        One agency failing is logged and skipped — does not abort the run.
        """
        since = (
            datetime.now(timezone.utc) - timedelta(days=self.days_back)
        ).strftime("%Y-%m-%d")

        all_results: list[dict] = []
        failures: list[str] = []

        for agency in self.TARGET_AGENCIES:
            params = {
                "conditions[agencies][]": agency,
                "conditions[publication_date][gte]": since,
                "conditions[type][]": self.TARGET_TYPES,
                "fields[]": self.REQUESTED_FIELDS,
                "per_page": self.PER_PAGE,
                "order": "newest",
            }

            try:
                response = self._http_get_with_retry(
                    f"{self.FR_API_BASE}/documents.json",
                    params=params,
                )
                results = response.json().get("results", [])
                log.info(
                    "FR API: agency=%s docs=%d since=%s",
                    agency, len(results), since,
                )
                all_results.extend(results)
            except _FatalError as e:
                # Retries exhausted or non-retryable response — skip this agency
                failures.append(f"{agency}: {e}")
                log.error("FR API: agency=%s skipped — %s", agency, e)
            except Exception as e:
                # Anything else — JSON parse error, unexpected — also skip
                failures.append(f"{agency}: {type(e).__name__}: {e}")
                log.error(
                    "FR API: agency=%s unexpected error — %s: %s",
                    agency, type(e).__name__, e,
                )

            # Politeness pause between agencies
            time.sleep(self.inter_agency_sleep_seconds)

        if failures and not all_results:
            # Every agency failed — propagate so run() marks status='failed'
            raise RuntimeError(
                f"All {len(self.TARGET_AGENCIES)} agencies failed: {'; '.join(failures)}"
            )

        if failures:
            # Some succeeded, some failed — run() will mark status='partial'
            log.warning(
                "FR API: %d/%d agencies failed — %s",
                len(failures), len(self.TARGET_AGENCIES), failures,
            )

        return all_results

    # ------------------------------------------------------------------
    # Type mapping
    # ------------------------------------------------------------------

    def map_content_type(self, doc: dict) -> str:
        """
        Translate the Federal Register 'type' field to our content_type value.

        Accepts either the API's query-filter code or its display string.
        An unrecognized value is logged at WARNING and stored as 'other' — it
        should never happen, and if it does we want it visible in the container
        logs rather than silently flattening the brief.
        """
        raw_type = doc.get("type")
        lookup = (raw_type or "").strip().upper()
        content_type = self.TYPE_MAP.get(lookup)

        if content_type is None:
            log.warning(
                "FR parse: unrecognized document type %r — storing 'other' "
                "(document_number=%s). TYPE_MAP may need a new key.",
                raw_type, doc.get("document_number"),
            )
            return "other"

        return content_type

    # ------------------------------------------------------------------
    # parse() — required by BaseScraper
    # ------------------------------------------------------------------

    def parse(self, doc: dict) -> Optional[ScrapedRow]:
        """
        Convert one Federal Register API result dict to a ScrapedRow.
        Returns None if the document has no usable content.
        """
        title = (doc.get("title") or "").strip()
        abstract = (doc.get("abstract") or "").strip()
        raw_content = f"{title}\n\n{abstract}".strip()

        if not raw_content:
            return None

        url_path = doc.get("html_url") or ""
        if not url_path:
            # No URL means we can't link to it later — skip rather than store an unlinkable row
            log.debug(
                "FR parse: skipping doc with no html_url — document_number=%s",
                doc.get("document_number"),
            )
            return None

        agency_names = doc.get("agency_names") or []
        publishing_agency = ", ".join(agency_names) if agency_names else None

        pub_date_str = doc.get("publication_date")
        publication_date = None
        if pub_date_str:
            try:
                publication_date = datetime.strptime(pub_date_str, "%Y-%m-%d").date()
            except ValueError:
                log.warning(
                    "FR parse: invalid publication_date %r — leaving NULL",
                    pub_date_str,
                )

        content_type = self.map_content_type(doc)

        return ScrapedRow(
            url_path=url_path,
            raw_content=raw_content,
            content_type=content_type,
            publishing_agency=publishing_agency,
            document_title=title or None,
            publication_date=publication_date,
        )
