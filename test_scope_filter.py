#!/usr/bin/env python3
"""
USDA and IRS scope-filter tests for generate_brief_review.py (v9.6-9.7, Entry #050).

Run:  python3 test_scope_filter.py
No database, Ollama or network needed. Exits non-zero on the first failure.
Agency strings are the exact forms stored in scraped_content.
"""
import generate_brief_review as g


def check(name, got, want):
    if got != want:
        raise SystemExit(f"FAIL {name}\n  got:  {got!r}\n  want: {want!r}")
    print(f"ok   {name}")


def doc(agency, title="", abstract=""):
    return {"publishing_agency": agency, "document_title": title,
            "raw_content": abstract}


FNA = "Agriculture Department, Food and Nutrition Administration"
FNS = "Agriculture Department, Food and Nutrition Service"
AMS = "Agriculture Department, Agricultural Marketing Service"

S = g.usda_in_scope
check("FNA kept (current name)", S(doc(FNA, "SNAP: Store Eligibility")), True)
check("FNS kept (former name)", S(doc(FNS, "Child Nutrition Programs")), True)
check("FNA kept with no SNAP mention (WIC)", S(doc(FNA, "WIC Food Packages")), True)
check("Sep 30 almond rule dropped",
      S(doc(AMS, "Almonds Grown in California; Extension of Inedible "
                 "Disposition Obligation Deadline")), False)
check("Forest Service dropped", S(doc("Agriculture Department, Forest Service",
                                      "Rescission Notice; Watershed Project")), False)
check("bare department dropped", S(doc("Agriculture Department", "Meeting")), False)
check("other USDA sub-agency mentioning SNAP kept",
      S(doc("Agriculture Department, Office of the Secretary",
            "Delegations of Authority", "Includes SNAP retailer oversight.")), True)
check("full program name, any case, kept",
      S(doc(AMS, "", "supplemental nutrition assistance program purchases")), True)
check("lower-case 'snap' is not the acronym",
      S(doc(AMS, "Snap Beans; Grade Standards")), False)
check("'SNAPSHOT' is not a SNAP mention",
      S(doc(AMS, "SNAPSHOT of Market Conditions")), False)
check("non-USDA untouched (IRS)",
      S(doc("Treasury Department, Internal Revenue Service", "Farmland")), True)
check("non-USDA untouched (CMS)",
      S(doc("Health and Human Services Department, Centers for Medicare & "
            "Medicaid Services", "IPPS Correction")), True)

# routing: area_for is sub-agency based; main() promotes a SNAP-mentioning
# non-FNS USDA document to SNAP. Check the pieces main() relies on.
check("FNA routes to SNAP", g.area_for(FNA), "SNAP")
check("FNS routes to SNAP", g.area_for(FNS), "SNAP")
check("OS falls to Cross-Program before promotion",
      g.area_for("Agriculture Department, Office of the Secretary"), "Cross-Program")
check("is_usda", g.is_usda(doc(AMS)), True)
check("is_usda false for HHS", g.is_usda(doc("Health and Human Services Department")), False)

# ---- IRS (v9.7) ----
IRS = "Treasury Department, Internal Revenue Service"
I = g.irs_in_scope
check("Sep 30 farmland rule dropped",
      I(doc(IRS, "Election To Pay in Installments Tax on Gain From Certain "
                 "Farmland Property", "qualified farmland ... qualified farmer")), False)
check("EITC kept", I(doc(IRS, "Earned Income Credit; Due Diligence")), True)
check("premium tax credit kept",
      I(doc(IRS, "", "rules for the premium tax credit under section 36B")), True)
check("Pub 1075 / FTI kept",
      I(doc(IRS, "Safeguards for Federal Tax Information")), True)
check("child support offset kept",
      I(doc(IRS, "", "refund offsets for past-due child support")), True)
check("LIHTC dropped", I(doc(IRS, "Low-Income Housing Credit Average Income Test")), False)
check("LIHTC acronym dropped", I(doc(IRS, "", "LIHTC compliance monitoring")), False)
check("corporate rule dropped despite health insurance mention",
      I(doc(IRS, "Corporate Alternative Minimum Tax", "health insurance issuers")), False)
check("generic IRS notice dropped", I(doc(IRS, "Open Meeting of the Taxpayer Advocacy Panel")), False)
check("'safeguarding' is not the whole word 'safeguard'",
      I(doc(IRS, "Safeguarding Deposits")), False)
check("non-IRS untouched", I(doc("Social Security Administration", "Corporate")), True)
check("scope reason USDA",
      g.scope_drop_reason(doc(AMS, "Almonds")), "USDA: not FNS/FNA, no SNAP mention")
check("scope reason IRS",
      g.scope_drop_reason(doc(IRS, "Farmland")), "IRS: not HHS-adjacent")
check("scope reason none (CMS)",
      g.scope_drop_reason(doc("Health and Human Services Department, Centers "
                              "for Medicare & Medicaid Services", "X")), None)
print("all scope-filter tests passed")
