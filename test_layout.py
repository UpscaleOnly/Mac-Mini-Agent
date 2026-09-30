#!/usr/bin/env python3
"""
Brief layout tests for generate_brief_review.py (v9.9, Entry #050).

Run:  python3 test_layout.py
No database, Ollama or network needed. Exits non-zero on the first failure.
"""
import datetime as dt
import generate_brief_review as g


def check(name, ok):
    if not ok:
        raise SystemExit(f"FAIL {name}")
    print(f"ok   {name}")


FNA = "Agriculture Department, Food and Nutrition Administration"
AMS = "Agriculture Department, Agricultural Marketing Service"
CMS = "Health and Human Services Department, Centers for Medicare & Medicaid Services"


def raw(agency, title, ctype="notice", url=None, pd="2026-09-10"):
    return {"id": 1, "publishing_agency": agency, "document_title": title,
            "publication_date": pd, "content_type": ctype, "raw_content": "",
            "url_path": url}


# ---- prepare_rows: same filters as the brief ----
kept, scope, routine = g.prepare_rows([
    raw(FNA, "SNAP: Waiver Notice"),
    raw(AMS, "Almonds Grown in California"),
    raw(CMS, "Privacy Act of 1974; Matching Program"),
    raw("Health and Human Services Department, National Institutes of Health",
        "Advisory Committee Meeting"),
])
areas = {d["document_title"]: d["_area"] for d in kept}
check("FNA kept, routed to SNAP", areas.get("SNAP: Waiver Notice") == "SNAP")
check("almond rule dropped as out of scope", len(scope) == 1)
check("CMS matching notice routed to IT Governance",
      areas.get("Privacy Act of 1974; Matching Program") == "IT Governance")
check("routine Cross-Program meeting notice dropped", len(routine) == 1)

# ---- every section, every week ----
check("empty SNAP line", g.empty_section_line("SNAP") ==
      "No new SNAP documents in the Federal Register in this window.")
check("empty IT Governance line", g.empty_section_line("IT Governance") == g.NO_IT_GOV_DOCS)
reg = g.load_it_gov_register()
URL = "https://www.federalregister.gov/documents/2026/09/10/x/snap-waiver"
early = {"SNAP": [dict(kept[0], url_path=URL)]}
h = g.brief_html("r", "s", [("CMS", "cms text")],
                 {"CMS": [dict(kept[0], _area="CMS")]}, it_gov_reg=reg,
                 earlier_by_area=early)
for area in g.AREA_ORDER:
    check(f"HTML has section {area}", f"<h2>{g.AREA_HEADING[area]}</h2>" in h)
check("HTML empty SNAP line", "No new SNAP documents" in h)
check("IT Governance points to Appendix C", g.IT_GOV_POINTER in h)
check("appendices in order A, B, C",
      h.index("<h2>Appendix A") < h.index("<h2>Appendix B") < h.index("<h2>Appendix C"))
check("reference block is in Appendix C, after the body",
      h.index("<h2>Appendix C") < h.index("26 U.S.C. 6103") and h.index("<h2>Cross-Program") < h.index("<h2>Appendix C"))
check("Appendix B lists the earlier document with a link", f'<a href="{URL}">' in h)

# ---- plain-text Appendix B ----
today = dt.date(2026, 9, 30)
b = g.earlier_appendix(early, today=today)
check("Appendix B date range is days 8-30", "published 2026-08-31 to 2026-09-22" in b)
check("Appendix B groups by section with count", "SNAP (1)" in b)
check("Appendix B carries the link", URL in b)
check("Appendix B empty says None", g.earlier_appendix({}, today=today).rstrip().endswith("None."))
check("Appendix C heading in plain reference", g.it_gov_reference(reg).startswith("APPENDIX C"))
check("Appendix A heading", g.attribution({}).startswith("APPENDIX A"))
print("all layout tests passed")
