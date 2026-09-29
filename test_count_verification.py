#!/usr/bin/env python3
"""
Count-verification tests for generate_brief_review.py (v8, Entry #040).

Run:  python3 test_count_verification.py
No database, Ollama or network needed -- it imports the generator's pure
functions only. Exits non-zero on the first failure.

Sentences are taken from, or shaped like, real generator output. v7's tests
passed while the live run failed, because they tested the wrong shape; test
the shape the model actually writes.
"""
import generate_brief_review as g


def check(name, got, want):
    if got != want:
        raise SystemExit(f"FAIL {name}\n  got:  {got!r}\n  want: {want!r}")
    print(f"ok   {name}")


def row(instrument, agency="HHS", title=""):
    return {"_instrument": instrument, "publishing_agency": agency,
            "document_title": title, "raw_content": ""}


# ---- extraction: modifier words between number and unit ----
X = g._extract_counts
check("adjacent count still works", X("CMS issued three notices"), {(3, "notice")})
check("ICR phrase (the Sept 20 gap)",
      X("published two information collection requests regarding"),
      {(2, "request")})
check("sentence-initial ICR phrase",
      X("Two information collection requests were published"), {(2, "request")})
check("digit with modifiers", X("3 new SNAP rules"), {(3, "rule")})
check("modified state count (the 15-vs-18 shape)",
      X("notices for 15 participating states"), {(15, "state")})
check("request for information", X("two requests for information"),
      {(2, "request")})
check("function word ends the phrase", X("within 7 days of the comments"),
      {(7, "day")})
check("nearest unit wins", X("3 notices issued rules"), {(3, "notice")})
check("three modifiers is too many", X("two big new SNAP rules"), set())
check("date tail is not a count", X("on 2026-09-17 the proposed rules"), set())
check("dollar tail is not a count", X("$1,250 grants"), set())
check("hyphenated duration is not a count", X("a 3-year extension"), set())

# ---- ground truth ----
rows = [row("information collection request"),
        row("information collection request"),
        row("request for information"),
        row("final rule"),
        row("Privacy Act matching program notice")]
t = g.ground_truth_counts(rows)
check("request truth counts both request instruments", t["request"], 3)
check("ICR is not a notice", t["notice"], 1)
check("no requests -> no truth (unverifiable, not 'wrong, 0')",
      "request" in g.ground_truth_counts([row("final rule")]), False)

# ---- end to end through verify_counts ----
icr = [row("information collection request"),
       row("information collection request")]
truth = g.ground_truth_counts(icr)
check("correct ICR count verifies",
      g.verify_counts("TANF", "published two information collection requests",
                      "", truth), [])
w = g.verify_counts("TANF", "published three information collection requests",
                    "", truth)
check("wrong ICR count is caught", len(w) == 1 and "WRONG" in w[0], True)


# ---- enumeration: "one X" as a member of a correctly stated total ----
# Real SNAP text from the 2026-09-27 review run, which v8's first cut flagged.
snap = ("published two information collection requests on 2026-09-24. "
        "One information collection request, titled Turnip the Beet, seeks "
        "comment. The second information collection request, titled FNA QRS, "
        "also seeks comment.")
check("enumeration after a verified total is accepted",
      g.verify_counts("SNAP", snap, "", truth), [])
w = g.verify_counts("SNAP", "SNAP issued one information collection request.",
                    "", truth)
check("standalone 'one' is still caught", len(w) == 1 and "WRONG" in w[0], True)
w = g.verify_counts("SNAP", "published three information collection requests. "
                    "One information collection request, titled X.", "", truth)
check("'one' after a WRONG total does not ride along",
      len(w) == 2 and all("WRONG" in x for x in w), True)
notices18 = [row("notice")] * 18
w = g.verify_counts("SNAP", "two notices were issued. One notice concerns X.",
                    "", g.ground_truth_counts(notices18))
check("enumeration needs the TRUE total, not any total",
      len(w) == 2, True)
summary_truth = {"request": {2, 5}}
check("executive summary: enumeration against an acceptable set",
      g.verify_counts("EXECUTIVE SUMMARY", "FNA published two information "
                      "collection requests. One request concerns X.", "",
                      summary_truth), [])

# ---- F13 (Entry #048): verbatim shapes from the Sep 29 v9 live run ----
check("ICR compound phrase with a modifier (F13 TANF)",
      X("Two recent information collection requests from HHS"), {(2, "request")})
check("plain ICR count unchanged by the compound unit",
      X("published two information collection requests"), {(2, "request")})
tanf = ("Two recent information collection requests from the Health and Human "
        "Services Department, Children and Families Administration, address data "
        "collection activities. One request, published 2026-09-17, concerns the "
        "Diaper Distribution Demonstration and Research Pilot (DDDRP). A separate "
        "information collection request, published 2026-09-15, comes from OCSE.")
check("F13 TANF live text verifies clean",
      g.verify_counts("TANF", tanf, "",
                      g.ground_truth_counts([row("information collection request")] * 2)),
      [])
# KNOWN LIMITATION, pinned deliberately. The CMS text is correct (three
# notices: "A notice" + "Two notices"), but it never states the total, and
# accepting a count below the true total is the tolerance approach ruled out
# after the 15-vs-18 fabrication (Entry #037). This stays a warning; if this
# test ever starts passing with no warnings, a tolerance has crept in.
cms = ("A notice issued by CMS acknowledges the approval of an application from "
       "DNV Healthcare USA Inc. Two notices published by CMS address billing and "
       "appeals processes. One notice, published 2026-09-16, announces a public "
       "meeting. Additionally, a notice published 2026-09-16 announces the annual "
       "adjustment to the amount in controversy threshold.")
w = g.verify_counts("CMS", cms, "", g.ground_truth_counts([row("notice")] * 3))
check("F13 CMS subset counts stay flagged (known limitation, no tolerance)",
      len(w) == 2 and all("WRONG" in x for x in w), True)

print("\nall count-verification tests passed")
