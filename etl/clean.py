"""Clean the raw MovieLens 25M CSVs and write load-ready CSVs to data/clean/.

Usage:  python etl/clean.py
Also writes reports/cleaning_report.md, which lists every check with counts.

Output files (all CSV with a header, empty field = NULL):
    movies.csv         movie_id, title, release_year
    genres.csv         genre_id, name
    movie_genres.csv   movie_id, genre_id
    users.csv          user_id                 (every userId seen in ratings or tags)
    ratings.csv        user_id, movie_id, rating, rated_at
    tags.csv           tag_row_id, user_id, movie_id, tag, tagged_at
    links.csv          movie_id, imdb_id, tmdb_id
    genome_tags.csv    tag_id, tag
    genome_scores.csv  movie_id, tag_id, relevance
"""
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
REPORT = ROOT / "reports" / "cleaning_report.md"

CHUNK = 2_000_000                    # rows per chunk for the two big files
YEAR_RE = r"\((\d{4})\)\s*$"         # "(1995)" at the very end of a title
NO_GENRE = "(no genres listed)"
VALID_RATINGS = {x / 2 for x in range(1, 11)}   # 0.5, 1.0, ..., 5.0

report = []          # markdown lines, written at the end


def section(title):
    report.append(f"\n## {title}\n")
    report.append("| check | count | action |")
    report.append("|---|---:|---|")
    print(f"\n[{title}]")


def log(check, count, action=""):
    """Record one row in the report and echo it to the console."""
    shown = f"{count:,}" if isinstance(count, int) else str(count)
    report.append(f"| {check} | {shown} | {action} |")
    print(f"  {check:<55} {shown:>12}  {action}")


def to_datetime_str(epoch_seconds):
    """Unix seconds -> 'YYYY-MM-DD HH:MM:SS' (UTC), a format PostgreSQL COPY accepts."""
    return pd.to_datetime(epoch_seconds, unit="s").astype(str)


# --------------------------------------------------------------------------- movies
def clean_movies():
    section("movies.csv")
    df = pd.read_csv(RAW / "movies.csv", dtype={"title": str, "genres": str})
    log("raw rows", len(df))

    dup_ids = int(df["movieId"].duplicated().sum())
    log("duplicate movieId", dup_ids, "dropped" if dup_ids else "none found")
    df = df.drop_duplicates("movieId")

    title = df["title"].str.strip()
    year = title.str.extract(YEAR_RE, expand=False)
    df["release_year"] = pd.to_numeric(year).astype("Int64")
    df["title"] = title.str.replace(YEAR_RE, "", regex=True).str.strip()

    no_year = df["release_year"].isna()
    log("titles with no (YYYY) year at the end", int(no_year.sum()), "release_year = NULL")
    examples = "; ".join(df.loc[no_year, "title"].head(3))
    log("examples with no year", examples, "")

    log("release_year range", f"{df['release_year'].min()}–{df['release_year'].max()}", "")
    empty_title = int((df["title"] == "").sum())
    log("empty title after stripping the year", empty_title, "kept as-is" if empty_title else "none found")
    dup_titles = int(df.duplicated(["title", "release_year"], keep=False).sum())
    log("rows sharing a (title, year) with another movie", dup_titles,
        "kept: they are distinct movieIds")

    # genres: "A|B|C" -> one row per (movie, genre)
    no_genre = df["genres"].isna() | (df["genres"].str.strip() == NO_GENRE)
    log(f"movies with '{NO_GENRE}'", int(no_genre.sum()), "no movie_genres rows")
    pairs = (df.loc[~no_genre, ["movieId", "genres"]]
               .assign(name=lambda d: d["genres"].str.split("|"))
               .explode("name"))
    pairs["name"] = pairs["name"].str.strip()
    pairs = pairs[pairs["name"] != ""].drop_duplicates(["movieId", "name"])

    genres = pd.DataFrame({"name": sorted(pairs["name"].unique())})
    genres.insert(0, "genre_id", range(1, len(genres) + 1))
    log("distinct genres", len(genres), ", ".join(genres["name"]))

    movie_genres = (pairs.merge(genres, on="name")
                         .rename(columns={"movieId": "movie_id"})
                         [["movie_id", "genre_id"]]
                         .sort_values(["movie_id", "genre_id"]))
    log("movie–genre pairs", len(movie_genres))

    movies = df.rename(columns={"movieId": "movie_id"})[["movie_id", "title", "release_year"]]
    movies.to_csv(CLEAN / "movies.csv", index=False)
    genres.to_csv(CLEAN / "genres.csv", index=False)
    movie_genres.to_csv(CLEAN / "movie_genres.csv", index=False)
    log("rows written (movies)", len(movies))
    return set(movies["movie_id"])


# --------------------------------------------------------------------------- ratings
def clean_ratings(movie_ids):
    """Chunked. ratings.csv is sorted by userId, so all of a user's rows are
    contiguous; we hold back the last user of each chunk and prepend it to the
    next chunk, so duplicate (user, movie) pairs can never straddle a chunk."""
    section("ratings.csv (chunked)")
    out_path = CLEAN / "ratings.csv"
    stats = dict(raw=0, null=0, bad_value=0, orphan=0, dup=0, written=0)
    users = set()
    ts_min, ts_max = None, None
    prev_last_user = -1
    carry = None
    first_write = True

    def process(df):
        nonlocal first_write, ts_min, ts_max
        df = df.sort_values("timestamp").drop_duplicates(["userId", "movieId"], keep="last")
        df = df.sort_values(["userId", "movieId"])
        ts_min = df["timestamp"].min() if ts_min is None else min(ts_min, df["timestamp"].min())
        ts_max = df["timestamp"].max() if ts_max is None else max(ts_max, df["timestamp"].max())
        users.update(df["userId"].unique().tolist())
        out = pd.DataFrame({
            "user_id": df["userId"].astype("int32"),
            "movie_id": df["movieId"].astype("int32"),
            "rating": df["rating"],
            "rated_at": to_datetime_str(df["timestamp"]),
        })
        out.to_csv(out_path, index=False, mode="w" if first_write else "a", header=first_write)
        first_write = False
        stats["written"] += len(out)

    for chunk in pd.read_csv(RAW / "ratings.csv", chunksize=CHUNK):
        stats["raw"] += len(chunk)

        # file must be sorted by userId for the carry-over trick to be valid
        if chunk["userId"].iloc[0] < prev_last_user or not chunk["userId"].is_monotonic_increasing:
            raise SystemExit("ratings.csv is not sorted by userId; carry-over dedup is invalid")
        prev_last_user = chunk["userId"].iloc[-1]

        null = chunk.isna().any(axis=1)
        stats["null"] += int(null.sum())
        chunk = chunk[~null]

        bad = ~chunk["rating"].isin(VALID_RATINGS)
        stats["bad_value"] += int(bad.sum())
        chunk = chunk[~bad]

        orphan = ~chunk["movieId"].isin(movie_ids)
        stats["orphan"] += int(orphan.sum())
        chunk = chunk[~orphan]

        if carry is not None:
            chunk = pd.concat([carry, chunk])
        last_user = chunk["userId"].iloc[-1]
        carry = chunk[chunk["userId"] == last_user]
        body = chunk[chunk["userId"] != last_user]

        before = len(body)
        if before:
            n_before = stats["written"]
            process(body)
            stats["dup"] += before - (stats["written"] - n_before)
        print(f"  ... {stats['raw']:,} rows read")

    if carry is not None and len(carry):
        n_before = stats["written"]
        process(carry)
        stats["dup"] += len(carry) - (stats["written"] - n_before)

    log("raw rows", stats["raw"])
    log("rows with a missing value", stats["null"], "dropped")
    log("rating not in {0.5, 1.0, …, 5.0}", stats["bad_value"], "dropped")
    log("movieId not in movies", stats["orphan"], "dropped")
    log("duplicate (userId, movieId)", stats["dup"], "kept latest timestamp")
    log("timestamp range (UTC)",
        f"{pd.to_datetime(ts_min, unit='s')} → {pd.to_datetime(ts_max, unit='s')}",
        "converted to datetime")
    log("distinct users", len(users))
    log("rows written", stats["written"])
    return users


# --------------------------------------------------------------------------- tags
def clean_tags(movie_ids):
    section("tags.csv")
    df = pd.read_csv(RAW / "tags.csv", dtype={"tag": str}, keep_default_na=False)
    log("raw rows", len(df))

    stripped = df["tag"].str.strip()
    log("tags with leading/trailing whitespace", int((stripped != df["tag"]).sum()), "trimmed")
    df["tag"] = stripped.str.lower()
    log("tags that changed when lowercased", int((df["tag"] != stripped).sum()), "lowercased")

    empty = df["tag"] == ""
    log("empty tag after trimming", int(empty.sum()), "dropped")
    df = df[~empty]

    orphan = ~df["movieId"].isin(movie_ids)
    log("movieId not in movies", int(orphan.sum()), "dropped")
    df = df[~orphan]

    df = df.sort_values("timestamp")
    dup = df.duplicated(["userId", "movieId", "tag"], keep="first")
    log("duplicate (userId, movieId, tag) after lowercasing", int(dup.sum()), "kept earliest")
    df = df[~dup].sort_values(["userId", "movieId", "timestamp"])

    out = pd.DataFrame({
        "tag_row_id": range(1, len(df) + 1),
        "user_id": df["userId"].values,
        "movie_id": df["movieId"].values,
        "tag": df["tag"].values,
        "tagged_at": to_datetime_str(df["timestamp"]).values,
    })
    log("distinct tags", int(out["tag"].nunique()))
    log("rows written", len(out))
    out.to_csv(CLEAN / "tags.csv", index=False)
    return set(out["user_id"].unique().tolist())


# --------------------------------------------------------------------------- links
def clean_links(movie_ids):
    section("links.csv")
    df = pd.read_csv(RAW / "links.csv", dtype={"imdbId": str, "tmdbId": "Int64"})
    log("raw rows", len(df))
    orphan = ~df["movieId"].isin(movie_ids)
    log("movieId not in movies", int(orphan.sum()), "dropped")
    df = df[~orphan]
    log("missing tmdbId", int(df["tmdbId"].isna().sum()), "kept as NULL")
    log("imdbId with leading zero", int(df["imdbId"].str.startswith("0").sum()),
        "kept as text to preserve zeros")
    log("duplicate tmdbId (non-null)", int(df["tmdbId"].dropna().duplicated().sum()),
        "kept: info only")
    out = df.rename(columns={"movieId": "movie_id", "imdbId": "imdb_id", "tmdbId": "tmdb_id"})
    out.to_csv(CLEAN / "links.csv", index=False)
    log("rows written", len(out))


# --------------------------------------------------------------------------- genome
def clean_genome(movie_ids):
    section("genome-tags.csv")
    gt = pd.read_csv(RAW / "genome-tags.csv", dtype={"tag": str})
    log("raw rows", len(gt))
    log("duplicate tagId", int(gt["tagId"].duplicated().sum()), "")
    gt["tag"] = gt["tag"].str.strip()
    gt = gt.rename(columns={"tagId": "tag_id"})
    gt.to_csv(CLEAN / "genome_tags.csv", index=False)
    log("rows written", len(gt))
    tag_ids = set(gt["tag_id"])

    section("genome-scores.csv (chunked)")
    out_path = CLEAN / "genome_scores.csv"
    stats = dict(raw=0, null=0, out_of_range=0, orphan_movie=0, orphan_tag=0,
                 dup=0, written=0)
    per_movie = pd.Series(dtype="int64")
    last_key = (-1, -1)
    first = True
    for chunk in pd.read_csv(RAW / "genome-scores.csv", chunksize=CHUNK):
        stats["raw"] += len(chunk)
        null = chunk.isna().any(axis=1)
        stats["null"] += int(null.sum())
        chunk = chunk[~null]

        bad = ~chunk["relevance"].between(0, 1)
        stats["out_of_range"] += int(bad.sum())
        chunk = chunk[~bad]

        om = ~chunk["movieId"].isin(movie_ids)
        ot = ~chunk["tagId"].isin(tag_ids)
        stats["orphan_movie"] += int(om.sum())
        stats["orphan_tag"] += int(ot.sum())
        chunk = chunk[~om & ~ot]

        # file is sorted by (movieId, tagId): a key not strictly greater than the
        # previous one is a duplicate (also catches duplicates across chunks).
        key = chunk["movieId"].astype("int64") * 10_000 + chunk["tagId"]
        prev = key.shift(fill_value=last_key[0] * 10_000 + last_key[1])
        dup = key <= prev
        stats["dup"] += int(dup.sum())
        chunk = chunk[~dup]
        if len(chunk):
            last_key = (int(chunk["movieId"].iloc[-1]), int(chunk["tagId"].iloc[-1]))

        per_movie = per_movie.add(chunk["movieId"].value_counts(), fill_value=0)
        out = chunk.rename(columns={"movieId": "movie_id", "tagId": "tag_id"})
        out.to_csv(out_path, index=False, mode="w" if first else "a", header=first)
        first = False
        stats["written"] += len(out)
        print(f"  ... {stats['raw']:,} rows read")

    log("raw rows", stats["raw"])
    log("rows with a missing value", stats["null"], "dropped")
    log("relevance outside [0, 1]", stats["out_of_range"], "dropped")
    log("movieId not in movies", stats["orphan_movie"], "dropped")
    log("tagId not in genome-tags", stats["orphan_tag"], "dropped")
    log("duplicate or out-of-order (movieId, tagId)", stats["dup"], "dropped")
    log("movies with genome scores", len(per_movie),
        f"{len(per_movie) / len(movie_ids):.1%} of all movies")
    incomplete = int((per_movie != len(tag_ids)).sum())
    log(f"movies without exactly {len(tag_ids)} tag scores", incomplete, "info only")
    log("rows written", stats["written"])


# --------------------------------------------------------------------------- main
def main():
    t0 = time.time()
    CLEAN.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report.append("# Cleaning report: MovieLens 25M\n")
    report.append("Generated by `etl/clean.py`. Every check and its count is listed below. "
                  "\"none found\" or 0 means the check passed.")

    movie_ids = clean_movies()
    rating_users = clean_ratings(movie_ids)
    tag_users = clean_tags(movie_ids)
    clean_links(movie_ids)
    clean_genome(movie_ids)

    section("users (derived)")
    all_users = sorted(rating_users | tag_users)
    pd.DataFrame({"user_id": all_users}).to_csv(CLEAN / "users.csv", index=False)
    log("users in ratings", len(rating_users))
    log("users in tags", len(tag_users))
    log("users only in tags (no ratings)", len(tag_users - rating_users))
    log("rows written (union)", len(all_users))

    elapsed = time.time() - t0
    report.append(f"\n_Total cleaning time: {elapsed:.0f} s._\n")
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print(f"\nDone in {elapsed:.0f} s. Report: {REPORT}")


if __name__ == "__main__":
    main()
