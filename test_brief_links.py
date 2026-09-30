#!/usr/bin/env python3
"""
Link / HTML output tests for generate_brief_review.py (v9.7, Entry #050).

Run:  python3 test_brief_links.py
No database, Ollama or network needed. Exits non-zero on the first failure.
"""
import email
import generate_brief_review as g


def check(name, ok):
    if not ok:
        raise SystemExit(f"FAIL {name}")
    print(f"ok   {name}")


URL = ("https://www.federalregister.gov/documents/2026/09/29/2026-19946/"
       "medicare-program-hospital-inpatient")
D1 = {"document_title": "Medicare Program; IPPS; Correction",
      "publication_date": "2026-09-29", "_instrument": "final rule",
      "publishing_agency": "Health and Human Services Department, Centers for "
                           "Medicare & Medicaid Services",
      "url_path": URL}
D2 = {"document_title": "No link <b>here</b> & there",
      "publication_date": "2026-09-28", "_instrument": "notice",
      "publishing_agency": "Social Security Administration", "url_path": None}
EVIL = dict(D1, url_path='javascript:alert(1)')
ROWS = {"CMS": [D1], "Cross-Program": [D2]}

src = g.section_sources([D1, D2])
check("plain sources list has the title", "Medicare Program; IPPS; Correction" in src)
check("plain sources list has the link", URL in src)
check("missing link prints title only", "No link <b>here</b> & there (2026-09-28)" in src)
check("non-FR url never linked", g._safe_url(EVIL) == "")

h = g.brief_html("2026-09-23 to 2026-09-30", "Summary & more.\n\nSecond para.",
                 [("CMS", "CMS text <script>x</script>"), ("Cross-Program", "XP")],
                 ROWS)
check("FR link is a real anchor", f'<a href="{URL}">' in h)
check("model text is escaped", "<script>" not in h and "&lt;script&gt;" in h)
check("title markup is escaped", "&lt;b&gt;here&lt;/b&gt; &amp; there" in h)
check("paragraphs split", h.count("<p>") >= 3)
check("each section has a Sources list", h.count("<p class=m>Sources:</p>") == 2)
check("addendum present with agency", "Social Security Administration; notice" in h)
hb = g.brief_html("r", "s", [], ROWS, banner="TEST COPY\n! warning <x>")
check("banner shown and escaped", "TEST COPY<br>! warning &lt;x&gt;" in hb)

ha = g.brief_html("r", "s", [("CMS", "t")], {"CMS": [EVIL]})
check("javascript: url not linked", "javascript:" not in ha)

# multipart assembly, as send_email builds it (no SMTP)
msg = g.EmailMessage()
msg.set_content("plain body")
msg.add_alternative(h, subtype="html")
parsed = email.message_from_bytes(msg.as_bytes())
types = [p.get_content_type() for p in parsed.walk()]
check("multipart/alternative with text and html",
      types == ["multipart/alternative", "text/plain", "text/html"])
print("all brief-link tests passed")
