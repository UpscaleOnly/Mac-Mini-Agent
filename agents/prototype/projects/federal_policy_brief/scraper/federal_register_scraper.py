# federal_register_scraper.py
# Scraper for federalregister.gov REST API.
# ADR-039 H4 - first scraper for federal_policy_brief project.
# Persona: Automate

import hashlib
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

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
SOURCE_DOMAIN = "federalregister.gov"


def get_db_conn():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="openclaw",
        user="openclaw",
        password=os.environ.get("POSTGRES_PASSWORD", "changeme"),
    )


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_documents(days_back=1):
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    documents = []
    for agency in TARGET_AGENCIES:
        params = {
            "conditions[agencies][]": agency,
            "conditions[publication_date][gte]": since,
            "conditions[type][]": TARGET_TYPES,
            "fields[]": [
                "document_number",
                "title",
                "type",
                "abstract",
                "agency_names",
                "publication_date",
                "html_url",
            ],
            "per_page": 100,
            "order": "newest",
        }
        try:
            response = httpx.get(
                f"{FR_API_BASE}/documents.json",
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            log.info(f"Agency {agency}: {len(results)} documents")
            documents.extend(results)
        except Exception as e:
            log.error(f"Failed {agency}: {e}")
    return documents


def build_raw_content(doc):
    title = doc.get("title") or ""
    abstract = doc.get("abstract") or ""
    return f"{title}\n\n{abstract}".strip()


def map_type(fr_type):
    return {
        "RULE": "final_rule",
        "PRORULE": "proposed_rule",
        "NOTICE": "notice",
        "PRESDOCU": "presidential_document",
    }.get(fr_type, "other")


def insert_documents(conn, documents):
    inserted = 0
    skipped = 0
    with conn.cursor() as cur:
        for doc in documents:
            raw = build_raw_content(doc)
            if not raw:
                skipped += 1
                continue
            chash = content_hash(raw)
            url_path = doc.get("html_url") or doc.get("document_number") or ""
            agency_names = doc.get("agency_names") or []
            publishing_agency = ", ".join(agency_names) if agency_names else None
            pub_date = doc.get("publication_date") or None
            try:
                cur.execute(
                    "INSERT INTO scraped_content "
                    "(source_domain, url_path, content_hash, raw_content, "
                    "content_type, publishing_agency, document_title, publication_date) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (source_domain, content_hash) DO NOTHING",
                    (
                        SOURCE_DOMAIN,
                        url_path,
                        chash,
                        raw,
                        map_type(doc.get("type", "")),
                        publishing_agency,
                        doc.get("title"),
                        pub_date,
                    ),
                )
                if cur.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                log.error(f"Insert failed {url_path}: {e}")
                conn.rollback()
                skipped += 1
    conn.commit()
    return inserted, skipped


def main():
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    log.info(f"Fetching Federal Register documents from last {days_back} day(s)")
    documents = fetch_documents(days_back=days_back)
    log.info(f"Total fetched: {len(documents)}")
    if not documents:
        log.info("No documents found. Exiting.")
        return
    conn = get_db_conn()
    try:
        inserted, skipped = insert_documents(conn, documents)
        log.info(f"Complete. Inserted: {inserted} | Skipped: {skipped}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
