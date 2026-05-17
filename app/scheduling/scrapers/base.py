"""
app/scheduling/scrapers/base.py — BaseScraper abstract class

Foundation for all OpenClaw scrapers. Subclasses implement fetch() and
parse(); BaseScraper handles audit, dedup, retry, and DB writes.

Design principles:
  - Scrapers run under Automate persona, but BELOW the agent pipeline.
    No /agent hop, no LLM tokens, no interceptor. Audit is via scraper_runs.
  - Sync httpx + psycopg2. Wrap calls in asyncio.to_thread() at the
    dispatcher level (jobs.py) for concurrency.
  - DB credentials come from app.config.get_settings() — same Keychain
    overlay as the rest of the stack (ADR-039 A1).
  - No fallback to env-var-with-default. If Keychain isn't loaded, fail loud.

ADR references:
  ADR-039 H4 — first scraper for federal_policy_brief
  ADR-029   — audit table (scraper_runs serves analogous purpose for scrapers)
  ADR-030   — network whitelist (scrapers fetch only from pinned URLs;
                                 no Brave Search, no discovery)
"""
from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

import httpx
import psycopg2

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ScrapedRow — what a subclass returns from parse()
# ---------------------------------------------------------------------------

@dataclass
class ScrapedRow:
    """
    One parsed document, ready for insertion into scraped_content.
    Subclass parse() returns this; base class fills in source_domain,
    content_hash, project, and scraper_run_id automatically.
    """
    url_path: str
    raw_content: str
    content_type: Optional[str] = None
    publishing_agency: Optional[str] = None
    document_title: Optional[str] = None
    publication_date: Optional[date] = None


# ---------------------------------------------------------------------------
# Exceptions used internally for retry classification
# ---------------------------------------------------------------------------

class _RetryableError(Exception):
    """Raised internally when a fetch error should trigger retry."""
    pass


class _FatalError(Exception):
    """Raised internally when a fetch error should NOT retry."""
    pass


# ---------------------------------------------------------------------------
# BaseScraper
# ---------------------------------------------------------------------------

class BaseScraper(ABC):
    """
    Abstract base for all OpenClaw scrapers.

    Subclass contract:
      - Set class attributes: scraper_name, source_domain, project
      - Implement fetch() — returns list[dict] of raw source documents
      - Implement parse() — converts one raw doc to ScrapedRow (or None to skip)

    Optional overrides (class attributes with defaults):
      - max_retries (default 5)
      - retry_sleep_seconds (default 120)
      - request_timeout (default 30)
      - inter_agency_sleep_seconds (default 1)
    """

    # --- Required class attributes (subclass MUST set) ----------------------
    scraper_name: str = ""        # e.g. "federal_register"
    source_domain: str = ""       # e.g. "federalregister.gov"
    project: str = ""             # e.g. "federal_policy_brief"

    # --- Tunable retry policy (subclass MAY override) -----------------------
    max_retries: int = 5
    retry_sleep_seconds: int = 120
    request_timeout: int = 30
    inter_agency_sleep_seconds: int = 1

    # ------------------------------------------------------------------
    # Abstract methods — subclass implements
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch(self) -> list[dict]:
        """
        Return a list of raw documents from the source.
        Each doc is a dict — its shape is source-specific.
        Use self._http_get_with_retry() for individual HTTP calls.
        """
        ...

    @abstractmethod
    def parse(self, doc: dict) -> Optional[ScrapedRow]:
        """
        Convert one raw doc to a ScrapedRow.
        Return None to skip this doc (e.g. empty content, irrelevant type).
        """
        ...

    # ------------------------------------------------------------------
    # Public entry point — called by the dispatcher
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Execute one scraper run end-to-end.

        Returns a summary dict — useful for logging in the dispatcher.
        Never raises. All errors are logged and recorded in scraper_runs.
        """
        self._validate_subclass_attrs()
        log.info(
            "Scraper run starting: name=%s project=%s domain=%s",
            self.scraper_name, self.project, self.source_domain,
        )

        run_id: Optional[int] = None
        conn = None
        retries_used = 0
        docs_fetched = 0
        docs_inserted = 0
        docs_skipped = 0
        status = "failed"
        error_message: Optional[str] = None

        try:
            conn = self._get_db_conn()
            run_id = self._open_run_record(conn)

            try:
                docs = self.fetch()
                docs_fetched = len(docs)
                log.info("Scraper %s fetched %d docs", self.scraper_name, docs_fetched)
            except Exception as e:
                error_message = f"fetch() failed: {type(e).__name__}: {e}"
                log.error("Scraper %s: %s", self.scraper_name, error_message)
                docs = []

            for doc in docs:
                try:
                    row = self.parse(doc)
                except Exception as e:
                    log.warning(
                        "Scraper %s: parse error on one doc — %s: %s",
                        self.scraper_name, type(e).__name__, e,
                    )
                    docs_skipped += 1
                    continue

                if row is None:
                    docs_skipped += 1
                    continue

                outcome = self._insert_row(conn, run_id, row)
                if outcome == "inserted":
                    docs_inserted += 1
                else:
                    docs_skipped += 1

            # Determine final status
            if error_message and docs_fetched == 0:
                status = "failed"
            elif error_message:
                status = "partial"
            else:
                status = "success"

        except Exception as e:
            # Catastrophic — DB connect failed, run record write failed, etc.
            error_message = f"run() failed: {type(e).__name__}: {e}"
            log.error("Scraper %s: %s", self.scraper_name, error_message)
            status = "failed"
        finally:
            if conn is not None and run_id is not None:
                try:
                    self._close_run_record(
                        conn, run_id, status,
                        docs_fetched, docs_inserted, docs_skipped,
                        retries_used, error_message,
                    )
                except Exception as e:
                    log.error(
                        "Scraper %s: failed to close run record %s — %s",
                        self.scraper_name, run_id, e,
                    )
            if conn is not None:
                conn.close()

        summary = {
            "scraper_name": self.scraper_name,
            "project": self.project,
            "status": status,
            "docs_fetched": docs_fetched,
            "docs_inserted": docs_inserted,
            "docs_skipped": docs_skipped,
            "retries_used": retries_used,
            "error": error_message,
        }
        log.info("Scraper run complete: %s", summary)
        return summary

    # ------------------------------------------------------------------
    # HTTP helper — subclass uses inside fetch()
    # ------------------------------------------------------------------

    def _http_get_with_retry(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> httpx.Response:
        """
        GET with up to self.max_retries attempts and self.retry_sleep_seconds
        between attempts.

        Retries on: TimeoutException, ConnectError, ReadError, 5xx, 429
        Does NOT retry on: 4xx (other than 429), other exceptions.

        Raises _FatalError after exhaustion or on non-retryable response.
        Caller (subclass fetch()) decides whether to skip-and-continue
        or re-raise.
        """
        attempt = 0
        last_error: Optional[str] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                response = httpx.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.request_timeout,
                )
            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
                last_error = f"{type(e).__name__}: {e}"
                log.warning(
                    "Scraper %s: %s on attempt %d/%d — retrying in %ds",
                    self.scraper_name, last_error, attempt, self.max_retries,
                    self.retry_sleep_seconds,
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_sleep_seconds)
                continue
            except Exception as e:
                # Unexpected exception type — do not retry
                raise _FatalError(f"non-retryable {type(e).__name__}: {e}") from e

            status_code = response.status_code

            if 200 <= status_code < 300:
                return response

            if status_code == 429 or 500 <= status_code < 600:
                last_error = f"HTTP {status_code}"
                log.warning(
                    "Scraper %s: %s on attempt %d/%d — retrying in %ds",
                    self.scraper_name, last_error, attempt, self.max_retries,
                    self.retry_sleep_seconds,
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_sleep_seconds)
                continue

            # 4xx (other than 429) — do not retry
            raise _FatalError(f"HTTP {status_code} (non-retryable)")

        # Retries exhausted
        raise _FatalError(
            f"retries exhausted ({self.max_retries} attempts) — last error: {last_error}"
        )

    # ------------------------------------------------------------------
    # Internal helpers — DB, hashing, run record
    # ------------------------------------------------------------------

    def _validate_subclass_attrs(self) -> None:
        """Fail loud if a subclass forgot to set required class attributes."""
        missing = [
            name for name in ("scraper_name", "source_domain", "project")
            if not getattr(self, name, "")
        ]
        if missing:
            raise RuntimeError(
                f"{type(self).__name__} is missing required class attrs: {missing}"
            )

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _get_db_conn():
        """
        Open a psycopg2 connection using settings from app.config.
        Same Keychain overlay path as the rest of the stack (ADR-039 A1).
        No env-var fallback — if Settings isn't loaded, this raises.
        """
        from app.config import get_settings
        settings = get_settings()
        return psycopg2.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
        )

    def _open_run_record(self, conn) -> int:
        """Insert a 'running' row into scraper_runs and return its id."""
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scraper_runs "
                "(scraper_name, project, source_domain, status) "
                "VALUES (%s, %s, %s, 'running') "
                "RETURNING id",
                (self.scraper_name, self.project, self.source_domain),
            )
            run_id = cur.fetchone()[0]
        conn.commit()
        return run_id

    def _close_run_record(
        self,
        conn,
        run_id: int,
        status: str,
        docs_fetched: int,
        docs_inserted: int,
        docs_skipped: int,
        retries_used: int,
        error_message: Optional[str],
    ) -> None:
        """Update the scraper_runs row with final status and counts."""
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scraper_runs SET "
                "  ended_at = NOW(), "
                "  status = %s, "
                "  docs_fetched = %s, "
                "  docs_inserted = %s, "
                "  docs_skipped = %s, "
                "  retries_used = %s, "
                "  error_message = %s "
                "WHERE id = %s",
                (
                    status, docs_fetched, docs_inserted, docs_skipped,
                    retries_used, error_message, run_id,
                ),
            )
        conn.commit()

    def _insert_row(self, conn, run_id: int, row: ScrapedRow) -> str:
        """
        Insert one ScrapedRow into scraped_content with ON CONFLICT DO NOTHING.
        Returns 'inserted' or 'skipped'.
        """
        raw = row.raw_content.strip()
        if not raw:
            return "skipped"
        chash = self._content_hash(raw)

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO scraped_content "
                    "(source_domain, url_path, content_hash, raw_content, "
                    "content_type, publishing_agency, document_title, "
                    "publication_date, project, scraper_run_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (source_domain, content_hash) DO NOTHING",
                    (
                        self.source_domain, row.url_path, chash, raw,
                        row.content_type, row.publishing_agency, row.document_title,
                        row.publication_date, self.project, run_id,
                    ),
                )
                outcome = "inserted" if cur.rowcount == 1 else "skipped"
            conn.commit()
            return outcome
        except Exception as e:
            log.error(
                "Scraper %s: insert failed for %s — %s",
                self.scraper_name, row.url_path, e,
            )
            conn.rollback()
            return "skipped"
