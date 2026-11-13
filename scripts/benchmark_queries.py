"""Time every analysis query as movie_app_user and write reports/query_performance.md.

Usage:  python scripts/benchmark_queries.py [--runs 5]

Each query runs `runs` times on one warm connection (the time covers execution
and fetching the rows, not connecting). PASS = median under 2 s.
For a FAIL, EXPLAIN (ANALYZE, BUFFERS) is added to the report.
"""
import argparse
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from db import user_conn                          # noqa: E402
from queries import load_sql, search_patterns     # noqa: E402

LIMIT_MS = 2000
REPORT = ROOT / "reports" / "query_performance.md"

# (label, sql file, params). Parameters are realistic, and the worst cases are
# included: movie 356 (Forrest Gump) has the most ratings of any movie.
CASES = [
    ("(a) top tags: The Matrix",             "a_top_tags_for_movie", {"movie_id": 2571}),
    ("(a) top tags: no genome data",         "a_top_tags_for_movie", {"movie_id": 209171}),
    ("(b) top movies: overall, min 50",      "b_top_movies", {"min_ratings": 50, "release_year": None}),
    ("(b) top movies: 1995, min 50",         "b_top_movies", {"min_ratings": 50, "release_year": 1995}),
    ("(c) popular tags: all genres, top 5",  "c_popular_tags_by_genre", {"top_n": 5, "genre": None}),
    ("(c) popular tags: Drama, top 5",       "c_popular_tags_by_genre", {"top_n": 5, "genre": "Drama"}),
    ("(d) distribution: Forrest Gump",       "d_rating_distribution", {"movie_id": 356}),
    ("(d) distribution: Toy Story",          "d_rating_distribution", {"movie_id": 1}),
    ("(d) movie summary",                    "d_movie_summary", {"movie_id": 356}),
    ("(e) ratings-per-movie histogram",      "e_ratings_per_movie_distribution", None),
    ("(e) ratings-per-movie summary",        "e_ratings_per_movie_summary", None),
    ("(f) top genre: 1995",                  "f_top_genre_for_year", {"release_year": 1995}),
    ("(f) year list",                        "f_years", None),
    ("(g) genre coverage",                   "g_genre_coverage", None),
    ("search: 'the matrix'",                 "movie_search", {**search_patterns("the matrix"), "limit": 20}),
    ("search: 'star' (many hits)",           "movie_search", {**search_patterns("star"), "limit": 20}),
    ("search: 'godfather' (contains)",       "movie_search", {**search_patterns("godfather"), "limit": 20}),
    ("genre list",                           "genres_list", None),
    ("overview metrics",                     "overview_metrics", None),
    ("(a) genome suggestions",               "genome_suggestions", {"limit": 3}),
    ("my ratings: demo_user3, page 1",       "my_ratings", {"user_id": 4, "limit": 25, "offset": 0}),
    ("my rating for one movie",              "my_rating_for_movie", {"user_id": 4, "movie_id": 1}),
]

# For the report only: question (c) computed WITHOUT the materialized view,
# to show why mv_popular_tags_genre exists.
C_DIRECT = """
WITH counts AS (
    SELECT g.name AS genre, t.tag, count(DISTINCT t.user_id) AS users, count(*) AS applications
      FROM tags t
      JOIN movie_genres mg ON mg.movie_id = t.movie_id
      JOIN genres g ON g.genre_id = mg.genre_id
     WHERE NOT EXISTS (SELECT 1 FROM tag_stoplist s WHERE s.tag = t.tag)
     GROUP BY g.name, t.tag
), ranked AS (
    SELECT *, row_number() OVER (PARTITION BY genre ORDER BY users DESC, applications DESC, tag) AS rank
      FROM counts
)
SELECT genre, rank, tag, users, applications FROM ranked WHERE rank <= 5 ORDER BY genre, rank
"""


def time_query(conn, query, params, runs):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        conn.execute(query, params).fetchall()
        times.append((time.perf_counter() - t0) * 1000)
    return times


def explain(conn, query, params):
    rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + query, params).fetchall()
    return "\n".join(r[0] for r in rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    runs = parser.parse_args().runs

    results, failures = [], []
    with user_conn(commit=False) as conn:
        conn.autocommit = True                         # each query on its own, like the app
        for label, name, params in CASES:
            query = load_sql(name)
            times = time_query(conn, query, params, runs)
            med, worst = statistics.median(times), max(times)
            ok = med < LIMIT_MS
            results.append((label, f"`{name}.sql`", med, worst, ok))
            print(f"{label:<42}{med:>9.1f} ms median {worst:>9.1f} ms max  {'PASS' if ok else 'FAIL'}")
            if not ok:
                failures.append((label, explain(conn, query, params)))
        direct = time_query(conn, C_DIRECT, None, runs)
        print(f"{'(c) WITHOUT the materialized view':<42}{statistics.median(direct):>9.1f} ms median")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "# Query performance",
        "",
        f"Generated by `scripts/benchmark_queries.py` on {now}. Every query ran {runs} times "
        "as **movie_app_user** on one warm connection. The time covers execution and fetching "
        f"the rows. PASS = median under {LIMIT_MS / 1000:.0f} s.",
        "",
        "| query | file | median ms | max ms | result |",
        "|---|---|---:|---:|---|",
    ]
    out += [f"| {l} | {f} | {m:.1f} | {w:.1f} | {'PASS' if ok else '**FAIL**'} |"
            for l, f, m, w, ok in results]
    passed = sum(r[4] for r in results)
    out += ["", f"**{passed} of {len(results)} pass.**", "",
            "## Why question (c) uses a materialized view", "",
            f"Computing (c) directly from `tags` × `movie_genres` (count DISTINCT users per genre and tag) "
            f"takes **{statistics.median(direct):,.0f} ms** (median of {runs}). "
            "`mv_popular_tags_genre` stores those counts, so the query only ranks them. "
            "Tags cannot be edited in the app, so precomputing is safe; `etl/load.py` rebuilds the view on every load. "
            "The query then takes each genre's top N from the index `mv_popular_tags_genre_rank_idx` (LATERAL + LIMIT) "
            "instead of sorting all 271k (genre, tag) rows, which spilled to disk and took about 1.5 s.",
            "",
            "## Known issue: question (d) for blockbusters", "",
            "`d_rating_distribution` reads every rating of one movie through `ratings_movie_idx`. Those rows are "
            "spread over the 1.2 GB `ratings` table, because it is stored in user order. A blockbuster's ratings "
            "sit on about 53,000 different pages (about 410 MB). This laptop has 0.8 GB of free RAM and "
            "PostgreSQL's default shared_buffers of 128 MB, so the table cannot stay in memory. Each "
            "blockbuster therefore takes 6–10 s (Forrest Gump, The Matrix, Toy Story), while a movie with a "
            "few hundred ratings stays under 1 s. In Phase 6 the table happened to be in the OS cache, which "
            "gave about 0.4 s. Fix options, each awaiting approval because each touches the 25M-row table or "
            "the (d) definition:",
            "",
            "1. a covering index `ratings (movie_id, rating)` (about 0.5 GB, plus VACUUM after the load so "
            "index-only scans need no heap reads);",
            "2. a 10-value rating histogram per movie in `movie_stats`, kept by the existing trigger, so (d) "
            "reads one row (no new index, the same output);",
            "3. physically ordering `ratings` by movie (COPY sorted by movie_id, or CLUSTER), so one movie's "
            "ratings sit on a few hundred pages.",
            ""]
    for label, plan in failures:
        out += [f"## FAIL: {label}", "", "```", plan, "```", ""]
    REPORT.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)}")
    if failures:
        sys.exit(f"{len(failures)} queries over {LIMIT_MS} ms")


if __name__ == "__main__":
    main()
