# Query results: questions (a)–(g)

All queries are in [sql/queries/](../sql/queries/). They run as `movie_app_user`
through [app/queries.py](../app/queries.py), and each is checked against an
independent pandas calculation on the cleaned CSVs
([tests/test_queries.py](../tests/test_queries.py)). Every query runs in under 2 s;
see [query_performance.md](query_performance.md). Titles are shown with the
article moved back to the front: MovieLens stores "Matrix, The", the app shows
"The Matrix".

**Rule for every query:** `LEFT JOIN movie_stats`, and a missing row counts as
`rating_count = 0`. 3,376 of the 62,423 movies have no ratings, and an inner join
would silently drop them.

---

## (a) Top genome tags for a movie

**Question:** the top-5 genome tags for a movie, by relevance.

**Definition:** the Tag Genome gives each of 13,816 movies a relevance score (0–1)
for each of 1,128 curated tags. We take the 5 highest, breaking ties by tag name.
Zero rows means **"No genome data for this movie"**: 78% of movies have no genome
scores, mostly the obscure ones.

```sql
SELECT row_number() OVER (ORDER BY gs.relevance DESC, gt.tag) AS rank, gt.tag,
       round(gs.relevance::numeric, 3) AS relevance
  FROM genome_scores gs JOIN genome_tags gt ON gt.tag_id = gs.tag_id
 WHERE gs.movie_id = %(movie_id)s
 ORDER BY gs.relevance DESC, gt.tag LIMIT 5
```

| The Matrix (1999) | relevance | Toy Story (1995) | relevance |
|---|---:|---|---:|
| dystopic future | 0.996 | toys | 0.999 |
| scifi | 0.993 | computer animation | 0.999 |
| cyberpunk | 0.992 | pixar animation | 0.996 |
| sci fi | 0.989 | kids and family | 0.986 |
| science fiction | 0.988 | animation | 0.984 |

**Insight:** the genome describes films very precisely (scores above 0.98), but it
repeats synonyms: the Matrix gets "scifi", "sci fi" and "science fiction".

---

## (b) Top 10 movies by average rating

**Question:** top-10 by average rating, overall and per release year, with an
adjustable minimum number of ratings.

**Definition:** `avg_rating` comes from `movie_stats`, kept current by a trigger, so
the query never scans the 25M ratings. A movie needs **at least 50 ratings** by
default (the slider changes this). Without a minimum, the top 10 is made of obscure
films with two or three 5-star ratings. Ties are broken by rating_count DESC, then
title.

```sql
FROM movies m LEFT JOIN movie_stats s ON s.movie_id = m.movie_id
WHERE coalesce(s.rating_count, 0) >= %(min_ratings)s
  AND (%(release_year)s::int IS NULL OR m.release_year = %(release_year)s::int)
ORDER BY s.avg_rating DESC NULLS LAST, coalesce(s.rating_count, 0) DESC, m.title
```

Overall, min 50:

| # | title | year | avg | ratings |
|---:|---|---:|---:|---:|
| 1 | Planet Earth II | 2016 | 4.483 | 1,124 |
| 2 | Planet Earth | 2006 | 4.465 | 1,747 |
| 3 | The Shawshank Redemption | 1994 | 4.414 | 81,482 |
| 4 | Band of Brothers | 2001 | 4.399 | 1,356 |
| 5 | Cosmos | – | 4.327 | 277 |
| 6 | The Godfather | 1972 | 4.324 | 52,498 |
| 7 | Blue Planet II | 2017 | 4.290 | 659 |
| 8 | The Usual Suspects | 1995 | 4.284 | 55,366 |

1995, min 50: The Usual Suspects 4.284 · Wallace & Gromit: A Close Shave 4.104 ·
Seven 4.079 · Persuasion 4.030 · Braveheart 4.002.

With min 1, the top 10 is all 5.000 averages from 2–3 ratings (Awaken, Borrowed
Time, …), which is why a threshold is needed.

**Insight:** TV documentaries and mini-series (Planet Earth, Band of Brothers)
outrank every feature film. Their small, devoted audiences rate them highly.
Shawshank is the best-rated film with a mass audience.

---

## (c) Most popular user tags per genre

**Question:** the most popular user tags per genre, excluding junk tags.

**Definition:**
- **Popularity = number of distinct users** who applied the tag to movies of that genre, with the raw application count as a tie-break. Raw counts are dominated by a few people: the top 1% of taggers wrote 54% of all tags. "bd-r" has 3,966 applications from only 11 users, and "woman director" 3,590 from 35.
- **Stop list:** the table `tag_stoplist` (19 tags), the one place junk is defined: viewing status ("in netflix queue", "to see", "seen"), media and ownership ("dvd", "bd-r", "vhs", "owned") and list membership ("imdb top 250").
- A movie with 3 genres counts in all 3.
- The counts come from the materialized view `mv_popular_tags_genre`, because computing them live takes about 10 s.

```sql
FROM genres g CROSS JOIN LATERAL (
    SELECT row_number() OVER (PARTITION BY p.genre
                              ORDER BY p.users DESC, p.applications DESC, p.tag) AS rank, ...
      FROM mv_popular_tags_genre p
     WHERE p.genre = g.name
       AND NOT EXISTS (SELECT 1 FROM tag_stoplist s WHERE s.tag = p.tag)
     ORDER BY p.users DESC, p.applications DESC, p.tag LIMIT %(top_n)s) t
```

| rank | Drama | Comedy | Sci-Fi | Horror |
|---:|---|---|---|---|
| 1 | surreal (1,374 users) | comedy (1,658) | sci-fi (2,460) | horror (787) |
| 2 | atmospheric (1,356) | funny (1,448) | dystopia (1,177) | atmospheric (570) |
| 3 | twist ending (1,297) | dark comedy (1,185) | space (1,140) | zombies (536) |
| 4 | thought-provoking (1,233) | quirky (1,026) | time travel (1,081) | twist ending (469) |
| 5 | psychology (1,129) | black comedy (870) | thought-provoking (1,064) | suspense (448) |

**Insight:** users often re-tag the genre itself ("comedy", "sci-fi", "horror"), but
the tags just below show what audiences value: twists in Drama, dark humour in
Comedy, dystopias and time travel in Sci-Fi.

---

## (d) Rating distribution of a movie

**Question:** the distribution of a movie's ratings, with every value 0.5–5.0,
including zero counts.

**Definition:** `generate_series(0.5, 5.0, 0.5)` LEFT JOIN the movie's ratings, so
all 10 values are always present. An unrated movie shows 10 rows of 0. The
percentage is the share of that movie's ratings.

```sql
FROM generate_series(0.5, 5.0, 0.5) AS v(rating)
LEFT JOIN (SELECT rating, count(*) AS n FROM ratings
            WHERE movie_id = %(movie_id)s GROUP BY rating) c ON c.rating = v.rating
```

Forrest Gump (1994), 81,491 ratings, average 4.048 (the most-rated movie):

| rating | 0.5 | 1.0 | 1.5 | 2.0 | 2.5 | 3.0 | 3.5 | 4.0 | 4.5 | 5.0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| count | 424 | 1,159 | 450 | 2,449 | 1,569 | 10,380 | 6,185 | 23,348 | 9,609 | 25,918 |
| % | 0.5 | 1.4 | 0.6 | 3.0 | 1.9 | 12.7 | 7.6 | 28.7 | 11.8 | 31.8 |

**Insight:** whole stars are far more common than half stars (4.0 gets 28.7%, 3.5
only 7.6%). Users think in whole stars and use halves to fine-tune.

---

## (e) How many ratings does a movie get?

**Question:** a histogram of rating_count per movie, on a log scale.

**Definition:** all 62,423 movies, with unrated movies counted as 0. The buckets
grow about 10× per step (0 | 1 | 2–5 | 6–10 | 11–50 | … | 5,001+), which is a log
scale. A linear histogram would be a single bar at 0.

```sql
SELECT coalesce(s.rating_count, 0) AS n
  FROM movies m LEFT JOIN movie_stats s ON s.movie_id = m.movie_id
-- joined to a VALUES list of (sort_order, bucket, lo, hi)
```

| ratings | 0 | 1 | 2–5 | 6–10 | 11–50 | 51–100 | 101–500 | 501–1,000 | 1,001–5,000 | 5,001+ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| movies | 3,376 | 10,298 | 18,542 | 6,850 | 10,270 | 2,796 | 4,911 | 1,590 | 2,567 | 1,223 |
| % | 5.4 | 16.5 | 29.7 | 11.0 | 16.5 | 4.5 | 7.9 | 2.5 | 4.1 | 2.0 |

Summary: median **5** ratings, mean **400.5**, maximum 81,491. **The top 10% of
movies (6,243) received 94.5% of all ratings.**

**Insight:** a classic long tail. Half of all movies have 5 ratings or fewer, while
1,223 blockbusters (2%) each have more than 5,000. This is why (b) needs a
minimum-ratings threshold.

---

## (f) Genre with the most releases in a year

**Question:** the genre with the most releases in a selected year, showing all
genres and handling ties.

**Definition:** the number of movies released that year in each genre (a movie
counts once in each of its genres). `RANK()` gives tied genres the same rank 1, and
**every** genre at rank 1 is flagged `is_top`, so a tie is shown, not hidden. All 19
genres are returned, including those with 0.

```sql
SELECT rank() OVER (ORDER BY movie_count DESC) AS rank, genre, movie_count,
       (rank() OVER (ORDER BY movie_count DESC) = 1 AND movie_count > 0) AS is_top
```

| 1995 | movies | 2010 | movies |
|---|---:|---|---:|
| **Drama** (top) | 297 | **Drama** (top) | 719 |
| Comedy | 168 | Comedy | 459 |
| Action | 120 | Thriller | 273 |
| Thriller | 98 | Documentary | 248 |

Ties happen in 4 early years: 1916 (Comedy = Drama, 14 each), 1907 and 1904
(Comedy = Fantasy), 1901 (Comedy = Documentary).

**Insight:** Drama is the top genre (or tied for it) in 104 of the 132 years, and in
every year since 1930 except 1941. Ties only occur in the silent era, when a year
has just a handful of movies.

---

## (g) Count and % of movies per genre

**Question:** the count and % of movies per genre.

**Definition:** the denominator is **all 62,423 movies**. A `(no genre)` row covers
the 5,062 movies listed as "(no genres listed)". We also show each genre's share of
all ratings. **The percentages add up to more than 100%** (179.9% for movies)
because a movie with several genres counts in each one: there are 107,245
movie–genre pairs.

```sql
SELECT g.name, count(p.movie_id), round(100.0 * count(p.movie_id) / t.movies, 2), ...
  FROM genres g LEFT JOIN movie_genres mg ... LEFT JOIN per_movie p ...
UNION ALL SELECT '(no genre)', ... WHERE NOT EXISTS (SELECT 1 FROM movie_genres ...)
```

| genre | movies | % of movies | ratings | % of ratings |
|---|---:|---:|---:|---:|
| Drama | 25,606 | 41.0 | 10,962,833 | 43.9 |
| Comedy | 16,870 | 27.0 | 8,926,230 | 35.7 |
| Thriller | 8,654 | 13.9 | 6,763,272 | 27.1 |
| Romance | 7,719 | 12.4 | 4,497,291 | 18.0 |
| Action | 7,348 | 11.8 | 7,446,918 | 29.8 |
| Documentary | 5,605 | 9.0 | 322,449 | 1.3 |
| Adventure | 4,145 | 6.6 | 5,832,424 | 23.3 |
| IMAX | 195 | 0.3 | 1,063,279 | 4.3 |
| (no genre) | 5,062 | 8.1 | 26,627 | 0.1 |

**Insight:** supply and demand differ. Action and Adventure have far more than their
share of ratings (Adventure: 6.6% of movies, 23.3% of ratings), while Documentary is
9% of movies but 1.3% of ratings. IMAX has 195 films that collect 4.3% of all ratings.
