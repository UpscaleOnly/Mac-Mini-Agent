# Throwaway bake-off harness: runs the real generator, review-only, but feeds it
# the 18 documents consumed by the Sep 27 brief (published Sep 22-28, is_new FALSE).
import sys, datetime as dt
sys.path.insert(0, "/Users/sheldonwheeler/openclaw")
import generate_brief_review as g

def fetch_rows(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT id, publishing_agency, document_title, publication_date,
                              content_type, raw_content, url_path
                       FROM scraped_content
                       WHERE project = %s AND is_new = FALSE
                         AND publication_date BETWEEN %s AND %s
                       ORDER BY publication_date DESC, id DESC""",
                    (g.PROJECT, dt.date(2026, 9, 22), dt.date(2026, 9, 28)))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

g.fetch_rows = fetch_rows
sys.argv = ["generate_brief_review.py", "--model", sys.argv[1], "--think", "off"]
g.main()
