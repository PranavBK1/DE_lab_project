"""Phase 6: every analysis query checked against an independent pandas
calculation on data/clean/*.csv.

Run:  pytest -v tests/test_queries.py          (about a minute: loads the CSVs once)
      pytest -m "not slow"                     (skips the CSV comparisons)

The pandas side never uses movie_stats: it recomputes counts and averages from
ratings.csv, so it also checks that the trigger-maintained aggregates are right.
Averages are compared exactly: ratings are counted in half-stars (int), and the
mean is rounded half-up to 3 decimals, as NUMERIC(4,3) does.
"""
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd
import pytest

import queries as q
from db import ROOT, user_conn

CLEAN = ROOT / "data" / "clean"
slow = pytest.mark.slow


# ----------------------------------------------------------------- CSV fixtures (once per session)
def read(name, columns, dtypes):
    return pd.read_csv(CLEAN / f"{name}.csv", usecols=columns, dtype=dtypes, engine="pyarrow")


@pytest.fixture(scope="session")
def movies():
    return read("movies", ["movie_id", "title", "release_year"],
                {"movie_id": "int32", "title": "string", "release_year": "Int16"})


@pytest.fixture(scope="session")
def genres():
    return read("genres", ["genre_id", "name"], {"genre_id": "int16", "name": "string"})


@pytest.fixture(scope="session")
def movie_genres(genres):
    mg = read("movie_genres", ["movie_id", "genre_id"], {"movie_id": "int32", "genre_id": "int16"})
    return mg.merge(genres, on="genre_id").rename(columns={"name": "genre"})


@pytest.fixture(scope="session")
def ratings():
    r = read("ratings", ["movie_id", "rating"], {"movie_id": "int32", "rating": "float32"})
    r["halves"] = (r["rating"] * 2).round().astype("int8")      # 0.5..5.0 -> 1..10, exact
    return r[["movie_id", "halves"]]


@pytest.fixture(scope="session")
def movie_counts(ratings, movies):
    """Per movie: rating count, sum in half-stars, exact rounded average. All movies (0 if unrated)."""
    agg = ratings.groupby("movie_id")["halves"].agg(n="size", halves="sum")
    agg = movies.set_index("movie_id").join(agg).fillna({"n": 0, "halves": 0})
    agg["n"] = agg["n"].astype("int64")
    agg["halves"] = agg["halves"].astype("int64")
    agg["avg"] = [None if n == 0 else
                  (Decimal(int(h)) / Decimal(2 * int(n))).quantize(Decimal("0.001"), ROUND_HALF_UP)
                  for h, n in zip(agg["halves"], agg["n"])]
    return agg


@pytest.fixture(scope="session")
def tags():
    return read("tags", ["user_id", "movie_id", "tag"],
                {"user_id": "int32", "movie_id": "int32", "tag": "string"})


@pytest.fixture(scope="session")
def genome():
    gs = read("genome_scores", ["movie_id", "tag_id", "relevance"],
              {"movie_id": "int32", "tag_id": "int16", "relevance": "float32"})
    gt = read("genome_tags", ["tag_id", "tag"], {"tag_id": "int16", "tag": "string"})
    return gs, gt


@pytest.fixture(scope="session")
def stoplist():
    with user_conn(commit=False) as conn:
        return {r[0] for r in conn.execute("SELECT tag FROM tag_stoplist")}


# ----------------------------------------------------------------- (a)
@slow
def test_a_top_tags_toy_story(genome):
    gs, gt = genome
    expected = (gs[gs.movie_id == 1].merge(gt, on="tag_id")
                .sort_values(["relevance", "tag"], ascending=[False, True]).head(5))
    got = q.top_tags_for_movie(1)
    assert list(got["rank"]) == [1, 2, 3, 4, 5]
    assert list(got["tag"]) == list(expected["tag"])
    assert np.allclose(got["relevance"], expected["relevance"].round(3), atol=1e-3)


@slow
def test_a_movie_without_genome_data_returns_no_rows(genome, movies):
    with_genome = set(genome[0].movie_id.unique())
    movie_id = int(movies.loc[~movies.movie_id.isin(with_genome), "movie_id"].iloc[0])
    assert q.top_tags_for_movie(movie_id).empty


# ----------------------------------------------------------------- (b)
def expected_top(movie_counts, min_ratings, year=None):
    df = movie_counts[movie_counts.n >= min_ratings]
    if year is not None:
        df = df[df.release_year == year]
    df = df.assign(avg_f=df["avg"].astype(float)).reset_index()
    return df.sort_values(["avg_f", "n", "title"], ascending=[False, False, True]).head(10)


@slow
@pytest.mark.parametrize("min_ratings, year", [(50, None), (50, 1995), (1000, 2010)])
def test_b_top_movies(movie_counts, min_ratings, year):
    expected = expected_top(movie_counts, min_ratings, year)
    got = q.top_movies(min_ratings, year)
    assert list(got["movie_id"]) == list(expected["movie_id"])
    assert list(got["rating_count"]) == list(expected["n"])
    assert [Decimal(str(v)).quantize(Decimal("0.001")) for v in got["avg_rating"]] == list(expected["avg"])
    assert list(got["rank"]) == list(range(1, len(got) + 1))


@slow
def test_b_threshold_leaving_fewer_than_10(movie_counts):
    min_ratings = int(movie_counts.n.nlargest(4).iloc[-1])     # exactly 4 movies have this many
    expected = expected_top(movie_counts, min_ratings)
    got = q.top_movies(min_ratings)
    assert 0 < len(got) < 10
    assert list(got["movie_id"]) == list(expected["movie_id"])


# ----------------------------------------------------------------- (c)
@slow
@pytest.mark.parametrize("genre", ["Drama", "Comedy", "Sci-Fi"])
def test_c_popular_tags_match_pandas(tags, movie_genres, stoplist, genre):
    t = tags.merge(movie_genres[movie_genres.genre == genre], on="movie_id")
    t = t[~t.tag.isin(stoplist)]
    expected = (t.groupby("tag").agg(users=("user_id", "nunique"), applications=("tag", "size"))
                .reset_index()
                .sort_values(["users", "applications", "tag"], ascending=[False, False, True])
                .head(5))
    got = q.popular_tags_by_genre(5, genre)
    assert list(got["genre"].unique()) == [genre]
    assert list(got["tag"]) == list(expected["tag"])
    assert list(got["users"]) == list(expected["users"])
    assert list(got["applications"]) == list(expected["applications"])


def test_c_all_genres_no_stoplist_tags(stoplist):
    got = q.popular_tags_by_genre(10)
    assert got["genre"].nunique() == 19
    assert got.groupby("genre")["rank"].max().max() <= 10
    assert not set(got["tag"]) & stoplist
    assert len(stoplist) >= 9


# ----------------------------------------------------------------- (d)
@slow
def test_d_distribution_toy_story(ratings):
    expected = ratings[ratings.movie_id == 1]["halves"].value_counts()
    got = q.rating_distribution(1)
    assert list(got["rating"]) == [h / 2 for h in range(1, 11)]
    assert list(got["count"]) == [int(expected.get(h, 0)) for h in range(1, 11)]
    assert abs(got["pct"].sum() - 100) < 0.1
    summary = q.movie_summary(1).iloc[0]
    assert summary["rating_count"] == expected.sum()
    assert summary["title"] == "Toy Story"


@slow
def test_d_unrated_movie_has_10_zero_rows(movie_counts):
    movie_id = int(movie_counts.index[movie_counts.n == 0][0])
    got = q.rating_distribution(movie_id)
    assert len(got) == 10
    assert (got["count"] == 0).all() and (got["pct"] == 0).all()
    summary = q.movie_summary(movie_id).iloc[0]
    assert summary["rating_count"] == 0 and pd.isna(summary["avg_rating"])


# ----------------------------------------------------------------- (e)
@slow
def test_e_histogram_and_summary(movie_counts):
    n = movie_counts["n"]
    got = q.ratings_per_movie_distribution()
    assert got["movie_count"].sum() == 62_423 == len(n)
    edges = [-1, 0, 1, 5, 10, 50, 100, 500, 1000, 5000, np.inf]
    expected = pd.cut(n, edges).value_counts(sort=False).tolist()
    assert got.sort_values("sort_order")["movie_count"].tolist() == expected

    s = q.ratings_per_movie_summary().iloc[0]
    assert s["movies"] == 62_423
    assert s["min"] == n.min() and s["max"] == n.max()
    assert s["median"] == n.median()
    assert abs(s["mean"] - n.mean()) < 0.05
    top = int(np.ceil(len(n) * 0.1))
    assert s["top10pct_movies"] == top
    assert abs(s["top10pct_share_pct"] - 100 * n.nlargest(top).sum() / n.sum()) < 0.05


# ----------------------------------------------------------------- (f)
def expected_genre_counts(movies, movie_genres, genres, year):
    ids = movies.loc[movies.release_year == year, "movie_id"]
    counts = movie_genres[movie_genres.movie_id.isin(ids)].genre.value_counts()
    return {g: int(counts.get(g, 0)) for g in genres["name"]}


@slow
@pytest.mark.parametrize("year", [1995, 2010])
def test_f_top_genre_for_year(movies, movie_genres, genres, year):
    expected = expected_genre_counts(movies, movie_genres, genres, year)
    got = q.top_genre_for_year(year)
    assert len(got) == 19
    assert dict(zip(got["genre"], got["movie_count"])) == expected
    best = max(expected.values())
    assert set(got.loc[got.is_top, "genre"]) == {g for g, c in expected.items() if c == best}


@slow
def test_f_tie_for_top_genre_is_shown(movies, movie_genres, genres):
    per_year = (movie_genres.merge(movies[["movie_id", "release_year"]], on="movie_id")
                .dropna(subset=["release_year"])
                .groupby(["release_year", "genre"]).size())
    tie_years = [int(y) for y, s in per_year.groupby(level=0) if (s == s.max()).sum() >= 2]
    assert tie_years, "no year with a tie found"
    year = tie_years[-1]                                    # the most recent tie
    expected = expected_genre_counts(movies, movie_genres, genres, year)
    best = max(expected.values())
    tied = {g for g, c in expected.items() if c == best}
    got = q.top_genre_for_year(year)
    assert len(tied) >= 2
    assert set(got.loc[got.is_top, "genre"]) == tied
    assert (got.loc[got.is_top, "rank"] == 1).all()


def test_f_years_list():
    years = q.list_years()
    assert years["release_year"].is_monotonic_decreasing
    assert years["movie_count"].sum() == 62_423 - 412          # 412 movies have no year


# ----------------------------------------------------------------- (g)
@slow
def test_g_genre_coverage(movie_genres, movie_counts):
    got = q.genre_coverage().set_index("genre")
    genres_only = got.drop(index="(no genre)")
    assert genres_only["movie_count"].sum() == 107_245 == len(movie_genres)
    assert got.loc["(no genre)", "movie_count"] == 5_062
    assert got["pct_of_all_movies"].sum() > 100                # movies have several genres

    expected = movie_genres.groupby("genre")["movie_id"].count()
    assert genres_only["movie_count"].to_dict() == expected.to_dict()
    rc = movie_genres.merge(movie_counts["n"], left_on="movie_id", right_index=True)
    assert genres_only["rating_count"].to_dict() == rc.groupby("genre")["n"].sum().to_dict()
    assert abs(got.loc["Drama", "pct_of_all_movies"] - 100 * expected["Drama"] / 62_423) < 0.01


# ----------------------------------------------------------------- search (GAP 7)
@pytest.mark.parametrize("text", ["matrix", "the matrix", "The Matrix", "MATRIX, THE"])
def test_search_finds_the_matrix(text):
    got = q.search_movies(text)
    assert got.iloc[0]["movie_id"] == 2571
    assert got.iloc[0]["title"] == "The Matrix"


def test_search_toy_story_ranks_1995_first():
    got = q.search_movies("toy story")
    assert got.iloc[0]["movie_id"] == 1
    assert got.iloc[0]["release_year"] == 1995
    assert {"Toy Story 2", "Toy Story 3"} <= set(got["title"])


def test_search_contains_fallback():
    got = q.search_movies("godfather")              # prefix "Godfather, The" + contains matches
    assert got.iloc[0]["movie_id"] == 858
    assert got.iloc[0]["title"] == "The Godfather"


def test_search_wildcards_are_literal():
    assert q.search_movies("%%%").empty
    assert q.search_movies("   ").empty


def test_genres_list():
    g = q.list_genres()
    assert len(g) == 19 and "Sci-Fi" in set(g["genre"])
