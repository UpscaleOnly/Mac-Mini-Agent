#!/usr/bin/env python3
"""
Federal Register fetch() pagination tests (Entry #043).

Run:  python3 test_fr_pagination.py
      (or inside the container: docker exec openclaw_fastapi python test_fr_pagination.py)
No network, no database -- _http_get_with_retry is replaced by a fake that
serves canned pages. Exits non-zero on the first failure.

The defect being guarded: fetch() used to read only the first page (newest
100 per agency), so a wide window silently lost its OLDEST documents.
"""
from datetime import date

from app.scheduling.scrapers.base import _FatalError
from app.scheduling.scrapers.federal_register import (
    FederalRegisterBackfill,
    FederalRegisterScraper,
)
from app.scheduling.scrapers import SCRAPERS


def check(name, got, want):
    if got != want:
        raise SystemExit(f"FAIL {name}\n  got:  {got!r}\n  want: {want!r}")
    print(f"ok   {name}")


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def make(cls=FederalRegisterScraper, pages_per_agency=None, fail_agency=None, **kw):
    """
    pages_per_agency: {agency: n_pages}; each page holds 100 docs except the
    last (37). Agencies not listed return one empty page.
    """
    pages_per_agency = pages_per_agency or {}
    s = cls(**kw) if kw else cls(days_back=1)
    s.inter_agency_sleep_seconds = 0
    s.inter_page_sleep_seconds = 0
    s.calls = []

    def fake_get(url, params=None, headers=None):
        s.calls.append((url, params))
        if params is not None:  # first page of an agency
            agency = params["conditions[agencies][]"]
            page = 1
        else:                   # next_page_url: fake://<agency>/<page>
            _, _, agency, page = url.split("/", 3)
            page = int(page)
        if agency == fail_agency:
            raise _FatalError("HTTP 500 (simulated)")
        n = pages_per_agency.get(agency, 1 if agency in pages_per_agency else 0)
        if n == 0:
            return FakeResponse({"results": [], "next_page_url": None})
        size = 100 if page < n else 37
        results = [{"document_number": f"{agency}-{page}-{i}"} for i in range(size)]
        nxt = f"fake://{agency}/{page + 1}" if page < n else None
        return FakeResponse({"results": results, "next_page_url": nxt})

    s._http_get_with_retry = fake_get
    return s


HHS = "health-and-human-services-department"

# ---- pagination ----
s = make(pages_per_agency={HHS: 3})
docs = s.fetch()
check("follows next_page_url across 3 pages", len(docs), 237)
check("oldest page is included (the Aug 4-16 failure mode)",
      any(d["document_number"] == f"{HHS}-3-0" for d in docs), True)
check("later pages sent without params (next_page_url carries the query)",
      [p for u, p in s.calls if u.startswith("fake://")], [None, None])
check("single-page agency still works",
      len(make(pages_per_agency={HHS: 1}).fetch()), 37)

# ---- runaway cap is reported, not silent ----
s = make(pages_per_agency={HHS: 25})
s.MAX_PAGES = 5
try:
    docs = s.fetch()
    check("cap: partial results returned", len(docs), 500)
except RuntimeError:
    raise SystemExit("FAIL cap raised instead of returning partial results")
import logging
class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(); self.msgs = []
    def emit(self, r):
        self.msgs.append(r.getMessage())
cap = _Capture()
logging.getLogger("app.scheduling.scrapers.federal_register").addHandler(cap)
s = make(pages_per_agency={HHS: 25}); s.MAX_PAGES = 5; s.fetch()
check("cap: logged as older documents NOT fetched",
      any("MAX_PAGES=5" in m and "NOT fetched" in m for m in cap.msgs), True)

# ---- failure isolation still holds ----
docs = make(pages_per_agency={HHS: 2, "agriculture-department": 1},
            fail_agency="internal-revenue-service").fetch()
check("one agency failing does not lose the others", len(docs), 137 + 37)

# ---- date bounds ----
s = make(date_from=date(2026, 8, 1), date_to=date(2026, 8, 19))
s.fetch()
first = s.calls[0][1]
check("date_from sets gte", first["conditions[publication_date][gte]"], "2026-08-01")
check("date_to sets lte", first["conditions[publication_date][lte]"], "2026-08-19")
s = make()
s.fetch()
check("nightly run sends no lte bound",
      "conditions[publication_date][lte]" in s.calls[0][1], False)

# ---- backfill isolation ----
b = FederalRegisterBackfill(date(2026, 8, 1), date(2026, 8, 19))
check("backfill records under its own scraper_name",
      b.scraper_name, "federal_register_backfill")
check("backfill does not auto-compute days_back", b.uses_days_back_catchup, False)
check("backfill is not registered for the nightly dispatcher",
      FederalRegisterBackfill in SCRAPERS, False)
check("nightly scraper name unchanged",
      FederalRegisterScraper.scraper_name, "federal_register")

print("\nall pagination tests passed")
