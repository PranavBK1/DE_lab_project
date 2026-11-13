-- (d) How are a movie's ratings distributed over the star values?
--
-- Definition: count of the movie's ratings at each of the 10 values
--             0.5, 1.0, ..., 5.0. generate_series LEFT JOIN, so every value is
--             always present, with 0 where nobody chose it.
-- Params:     %(movie_id)s
-- Output:     rating, count, pct (share of this movie's ratings, 2 decimals;
--             0 for an unrated movie)
-- Index:      ratings_movie_idx (movie_id)
-- Total and average: d_movie_summary.sql.
WITH counts AS (
    SELECT r.rating, count(*) AS n
      FROM ratings r
     WHERE r.movie_id = %(movie_id)s
     GROUP BY r.rating
)
SELECT v.rating,
       coalesce(c.n, 0) AS count,
       coalesce(round(100.0 * coalesce(c.n, 0) / nullif(sum(coalesce(c.n, 0)) OVER (), 0), 2), 0) AS pct
  FROM generate_series(0.5, 5.0, 0.5) AS v(rating)
  LEFT JOIN counts c ON c.rating = v.rating
 ORDER BY v.rating
