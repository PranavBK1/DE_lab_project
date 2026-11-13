"""Analysis queries (a)-(g): the ONLY place the app runs analysis SQL.

Each function loads one file from sql/queries/, runs it as movie_app_user in a
read-only transaction with named parameters, and returns a pandas DataFrame.

Also here: display_title() and the article-aware title search, because
MovieLens stores "The Matrix" as "Matrix, The".
"""
import re
from decimal import Decimal
from functools import lru_cache

import pandas as pd

from db import ROOT, user_conn

QUERY_DIR = ROOT / "sql" / "queries"

DEFAULT_MIN_RATINGS = 50
DEFAULT_TOP_N = 5
DEFAULT_SEARCH_LIMIT = 20


# ----------------------------------------------------------------- running SQL
@lru_cache(maxsize=None)
def load_sql(name):
    """Text of sql/queries/<name>.sql (read once)."""
    return (QUERY_DIR / f"{name}.sql").read_text(encoding="utf-8")


def run_query(name, params=None):
    """Run sql/queries/<name>.sql and return a DataFrame.
    NUMERIC columns come back as Decimal; they are converted to float."""
    with user_conn(commit=False) as conn:
        # Analysis never writes. Transaction-local, so it cannot leak to the
        # next user of this pooled connection.
        conn.execute("SET TRANSACTION READ ONLY")
        cur = conn.execute(load_sql(name), params)
        columns = [c.name for c in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=columns)
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    return df


def _with_display_titles(df):
    if "title" in df.columns:
        df = df.assign(title=df["title"].map(display_title))
    return df


# ----------------------------------------------------------------- titles (GAP 7)
# Articles MovieLens moves to the end: "Matrix, The", "Mariachi, El", "Enfer, L'".
ARTICLES = ["The", "A", "An", "Le", "La", "Les", "L'", "Der", "Die", "Das", "El", "Il"]
_TRAILING_ARTICLE = re.compile(r"^(?P<main>.+), (?P<article>" + "|".join(map(re.escape, ARTICLES)) + r")$")
_LEADING_ARTICLE = re.compile(
    r"^(?P<article>" + "|".join(re.escape(a.lower()) for a in ARTICLES if a != "L'") + r") (?P<rest>.+)$")


def display_title(title):
    """'Matrix, The' -> 'The Matrix'.

    Only the main title is changed, i.e. the part before an alternate title in
    parentheses: 'Postman, The (Postino, Il)' -> 'The Postman (Postino, Il)'.
    "L'" is joined without a space: 'Enfer, L'' -> "L'Enfer".
    A title that already starts with the same word is left alone, so
    'Die, Mommie, Die' is not turned into 'Die Die, Mommie'.
    """
    if not title:
        return title
    main, sep, alternate = title.partition(" (")
    m = _TRAILING_ARTICLE.match(main)
    if not m or main.startswith(m["article"] + ","):
        return title
    article, rest = m["article"], m["main"]
    main = f"{article}{rest}" if article == "L'" else f"{article} {rest}"
    return main + sep + alternate


def stored_form(query):
    """The way MovieLens would store a search text that starts with an article:
    'the matrix' -> 'matrix, the', "l'enfer" -> "enfer, l'". None if no article."""
    q = " ".join(query.lower().split())
    if q.startswith("l'") and len(q) > 2:
        return f"{q[2:]}, l'"
    m = _LEADING_ARTICLE.match(q)
    return f"{m['rest']}, {m['article']}" if m else None


def _like_escape(text):
    """Escape LIKE wildcards so a user typing % or _ searches for them literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_patterns(query):
    """LIKE patterns for movie_search.sql: the text as typed, and its stored form."""
    q = " ".join(query.lower().split())
    alt = stored_form(q) or q
    q, alt = _like_escape(q), _like_escape(alt)
    return {"prefix": f"{q}%", "alt_prefix": f"{alt}%",
            "contains": f"%{q}%", "alt_contains": f"%{alt}%"}


# ----------------------------------------------------------------- helpers
def search_movies(query, limit=DEFAULT_SEARCH_LIMIT):
    """Title autocomplete for (a) and (d). Prefix matches first, then
    contains-matches; well-known (most-rated) films first.
    Columns: movie_id, title, release_year, rating_count."""
    if not query or not query.strip():
        return pd.DataFrame(columns=["movie_id", "title", "release_year", "rating_count"])
    df = run_query("movie_search", {**search_patterns(query), "limit": limit})
    return _with_display_titles(df)


def list_genres():
    """The 19 genres, for the (c) dropdown. Columns: genre_id, genre."""
    return run_query("genres_list")


def list_years():
    """Release years with movies, newest first, for the (b)/(f) dropdowns.
    Columns: release_year, movie_count."""
    return run_query("f_years")


def overview_metrics():
    """Overview page: movies, users, ratings, tags, genome_movies, genome_pct,
    first_rated_at, last_rated_at (one row)."""
    return run_query("overview_metrics")


def genome_suggestions(limit=3):
    """(a) Well-known movies that have genome data, for the empty state.
    Columns: movie_id, title, release_year, rating_count."""
    return _with_display_titles(run_query("genome_suggestions", {"limit": limit}))


# ----------------------------------------------------------------- per-user (NEVER cache these)
def my_ratings(user_id, limit=25, offset=0):
    """My Ratings page: the user's ratings, newest first, one page.
    Columns: movie_id, title, release_year, my_rating, avg_rating, rated_at, total."""
    return _with_display_titles(
        run_query("my_ratings", {"user_id": user_id, "limit": limit, "offset": offset}))


def my_rating_for_movie(user_id, movie_id):
    """The user's own rating of one movie as a float, or None if not rated."""
    df = run_query("my_rating_for_movie", {"user_id": user_id, "movie_id": movie_id})
    return None if df.empty else float(df.iloc[0]["rating"])


# ----------------------------------------------------------------- (a) - (g)
def top_tags_for_movie(movie_id):
    """(a) Top 5 genome tags of a movie by relevance.
    Columns: rank, tag, relevance. Empty = no genome data for this movie."""
    return run_query("a_top_tags_for_movie", {"movie_id": movie_id})


def top_movies(min_ratings=DEFAULT_MIN_RATINGS, release_year=None):
    """(b) Top 10 movies by average rating with at least min_ratings ratings,
    overall (release_year=None) or for one release year.
    Columns: rank, movie_id, title, release_year, avg_rating, rating_count."""
    df = run_query("b_top_movies", {"min_ratings": min_ratings, "release_year": release_year})
    return _with_display_titles(df)


def popular_tags_by_genre(top_n=DEFAULT_TOP_N, genre=None):
    """(c) Most popular user tags per genre: distinct users who used the tag on
    that genre's movies, stop-list tags excluded. genre=None = all genres.
    Columns: genre, rank, tag, users, applications."""
    return run_query("c_popular_tags_by_genre", {"top_n": top_n, "genre": genre})


def rating_distribution(movie_id):
    """(d) Count and % of a movie's ratings at each value 0.5..5.0 (always 10 rows).
    Columns: rating, count, pct."""
    return run_query("d_rating_distribution", {"movie_id": movie_id})


def movie_summary(movie_id):
    """(d) Title, total ratings and average of one movie (one row, or empty).
    Columns: movie_id, title, release_year, rating_count, avg_rating."""
    return _with_display_titles(run_query("d_movie_summary", {"movie_id": movie_id}))


def ratings_per_movie_distribution():
    """(e) Histogram of ratings per movie over all movies, in log-scale buckets.
    Columns: bucket, sort_order, movie_count, pct."""
    return run_query("e_ratings_per_movie_distribution")


def ratings_per_movie_summary():
    """(e) min / median / mean / max ratings per movie, and the share of all
    ratings received by the top 10% most-rated movies (one row)."""
    return run_query("e_ratings_per_movie_summary")


def top_genre_for_year(release_year):
    """(f) Movies per genre released in a year; ALL genres, with is_top for
    every genre tied at rank 1. Columns: rank, genre, movie_count, is_top."""
    return run_query("f_top_genre_for_year", {"release_year": release_year})


def genre_coverage():
    """(g) Movies and ratings per genre, as counts and % of all movies / ratings,
    plus a '(no genre)' row. The %s add up to more than 100%.
    Columns: genre, movie_count, pct_of_all_movies, rating_count, pct_of_all_ratings."""
    return run_query("g_genre_coverage")
