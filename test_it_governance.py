#!/usr/bin/env python3
"""
IT Governance section tests for generate_brief_review.py (v9.8, Entry #050,
ADR-048 Part A).

Run:  python3 test_it_governance.py
No database, Ollama or network needed. Exits non-zero on the first failure.
Agency strings are the exact forms stored in scraped_content.
"""
import generate_brief_review as g


def check(name, got, want=True):
    if got != want:
        raise SystemExit(f"FAIL {name}\n  got:  {got!r}\n  want: {want!r}")
    print(f"ok   {name}")


CMS = "Health and Human Services Department, Centers for Medicare & Medicaid Services"
SSA = "Social Security Administration"
IRS = "Treasury Department, Internal Revenue Service"
FDA = "Health and Human Services Department, Food and Drug Administration"
MATCH = "Privacy Act matching program notice"
SORN = "Privacy Act system of records notice"


def doc(agency, title="", abstract=""):
    return {"publishing_agency": agency, "document_title": title,
            "raw_content": abstract}


G = g.is_it_governance
check("CMS matching notice (real title)", G(doc(CMS, "Privacy Act of 1974; Matching Program"), MATCH))
check("SSA system of records notice", G(doc(SSA, "Privacy Act of 1974; System of Records"), SORN))
check("IRS FTI safeguards rule", G(doc(IRS, "Safeguards for Federal Tax Information"), "final rule"))
check("CMS ARC-AMPE mention", G(doc(CMS, "", "security controls under ARC-AMPE"), "notice"))
check("SSA data exchange", G(doc(SSA, "", "electronic data exchange with states"), "notice"))
check("section 6103 by number", G(doc(IRS, "", "disclosure under section 6103"), "proposed rule"))
check("CMS payment rule not routed", G(doc(CMS, "Medicare Program; IPPS; Correction"), "final rule"), False)
check("FDA privacy notice not routed (agency out of scope)",
      G(doc(FDA, "Privacy Act of 1974; System of Records"), SORN), False)
check("'safeguarding' is not 'safeguard'",
      G(doc(CMS, "Safeguarding Program Integrity"), "notice"), False)
check("IRS SORN kept in scope by the IRS filter",
      g.irs_in_scope(doc(IRS, "Privacy Act of 1974; System of Records")))
check("IRS farmland still dropped", g.irs_in_scope(doc(IRS, "Farmland Installments")), False)
check("section order: after TANF, before Cross-Program",
      g.AREA_ORDER, ["CMS", "SNAP", "TANF", "IT Governance", "Cross-Program"])

# ---- reference block from the tracked register ----
reg = g.load_it_gov_register()
ref = g.it_gov_reference(reg)
check("register has 3 frameworks", len(reg["frameworks"]), 3)
check("26 U.S.C. 6103 listed", "26 U.S.C. 6103 -- Confidentiality" in ref)
check("45 CFR 155.260 listed", "45 CFR 155.260" in ref)
check("operator-included 20 CFR part 401 listed", "20 CFR part 401" in ref)
check("TSSR v12.1 listed", "Version 12.1, April 28, 2026" in ref)
check("ARC-AMPE v1.0.4 listed", "v1.0.4, May 7, 2026" in ref)
check("TSSR v12.1 authority 32 CFR part 2002 listed", "32 CFR part 2002" in ref)
check("Part B stated as not active", "not yet active (ADR-048 Part B)" in ref)
check("every register entry has an https link",
      all(x["url"].startswith("https://") for k in ("frameworks", "statutes", "regulations") for x in reg[k]))

# ---- HTML: section present every week, with and without documents ----
D = {"document_title": "Privacy Act of 1974; Matching Program", "publication_date": "2026-09-25",
     "_instrument": MATCH, "publishing_agency": CMS,
     "url_path": "https://www.federalregister.gov/documents/2026/09/25/x/privacy-act"}
empty = g.brief_html("r", "s", [], {}, it_gov_reg=reg)
check("no-docs week still has the IT Governance heading", "<h2>IT Governance</h2>" in empty)
check("no-docs week says so", "No IT governance documents" in empty)
check("reference links rendered", '<a href="https://www.ecfr.gov/current/title-45/section-155.260">' in empty)
full = g.brief_html("r", "s", [("IT Governance", "CMS renewed a matching program.")],
                    {"IT Governance": [D]}, it_gov_reg=reg)
check("docs week has prose and its Sources", "CMS renewed a matching program." in full and D["url_path"] in full)
check("docs week has no 'no documents' line", "No IT governance documents" not in full)
check("IT Governance before Cross-Program in HTML",
      g.brief_html("r", "s", [("Cross-Program", "XP")], {"Cross-Program": [D]}, it_gov_reg=reg).index("IT Governance")
      < g.brief_html("r", "s", [("Cross-Program", "XP")], {"Cross-Program": [D]}, it_gov_reg=reg).index("<h2>Cross-Program"))
check("without a register, no IT section is forced", "<h2>IT Governance</h2>" not in g.brief_html("r", "s", [], {}))
print("all IT governance tests passed")
