"""
app/scheduling/scrapers/__init__.py — Scraper registry

Central registry of all scrapers, grouped by project. The dispatcher in
jobs.py imports SCRAPERS and filters by project at runtime.

Adding a new scraper:
  1. Create the subclass in app/scheduling/scrapers/<name>.py
  2. Set `scraper_name`, `source_domain`, and `project` class attributes
  3. Import it below
  4. Add it to the SCRAPERS list

Adding a new project:
  1. Add scrapers as above with the new project value
  2. Register a new cron in scheduler.py calling scrape_dispatcher_job
     with project=<new project name>

Project naming convention (snake_case, matches directory names):
  federal_policy_brief  — Prototype persona, SaaS
  medical_brief         — Research persona, personal
  durham_politics       — Research persona, personal
"""
from app.scheduling.scrapers.base import BaseScraper, ScrapedRow
from app.scheduling.scrapers.federal_register import FederalRegisterScraper

# ---------------------------------------------------------------------------
# Registry — every scraper class that should run on schedule belongs here.
# Order within the list is preserved for logging, but dispatch is concurrent
# (bounded by DISPATCH_CONCURRENCY in jobs.py).
# ---------------------------------------------------------------------------

SCRAPERS: list[type[BaseScraper]] = [
    # federal_policy_brief (Prototype project)
    FederalRegisterScraper,
    # cms, hhs, usda, ... — pending
    #
    # medical_brief (Research project) — pending
    #
    # durham_politics (Research project) — pending
]


def scrapers_for_project(project: str) -> list[type[BaseScraper]]:
    """
    Return all scraper classes whose `project` attribute matches.
    Called by the dispatcher in jobs.py to filter SCRAPERS down to one project.
    """
    return [s for s in SCRAPERS if s.project == project]


__all__ = ["BaseScraper", "ScrapedRow", "SCRAPERS", "scrapers_for_project"]
