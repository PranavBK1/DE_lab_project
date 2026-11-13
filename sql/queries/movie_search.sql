-- Helper for (a) and (d): title autocomplete.
--
-- Titles are stored with the article moved to the end ("Matrix, The"), so the
-- app also passes the stored form of the query: "the matrix" -> "matrix, the"
-- (app/queries.py: search_patterns). LIKE wildcards in the user's text are
-- escaped in Python.
--   1. prefix match on lower(title): can use movies_lower_title_idx
--      (text_pattern_ops)
--   2. contains match: runs only if step 1 found fewer than `limit` movies
-- Results: prefix matches first, then by rating_count DESC (well-known films
-- first), then title.
-- Params:  %(prefix)s, %(alt_prefix)s       e.g. 'the matrix%%', 'matrix, the%%'
--          %(contains)s, %(alt_contains)s   e.g. '%%the matrix%%', '%%matrix, the%%'
--          %(limit)s                        default 20
-- Output:  movie_id, title, release_year, rating_count
WITH prefix AS (
    SELECT m.movie_id, 1 AS match
      FROM movies m
     WHERE lower(m.title) LIKE %(prefix)s
        OR lower(m.title) LIKE %(alt_prefix)s
),
fallback AS (
    SELECT m.movie_id, 2 AS match
      FROM movies m
     WHERE (SELECT count(*) FROM prefix) < %(limit)s
       AND (lower(m.title) LIKE %(contains)s OR lower(m.title) LIKE %(alt_contains)s)
       AND m.movie_id NOT IN (SELECT movie_id FROM prefix)
),
hits AS (
    SELECT * FROM prefix
    UNION ALL
    SELECT * FROM fallback
)
SELECT m.movie_id, m.title, m.release_year, coalesce(s.rating_count, 0) AS rating_count
  FROM hits h
  JOIN movies m ON m.movie_id = h.movie_id
  LEFT JOIN movie_stats s ON s.movie_id = m.movie_id
 ORDER BY h.match, coalesce(s.rating_count, 0) DESC, m.title
 LIMIT %(limit)s
