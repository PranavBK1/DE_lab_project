-- (e) How many ratings does a movie get? (histogram of rating_count per movie)
--
-- Definition: ALL 62,423 movies, bucketed by their number of ratings. Movies
--             with no ratings count as 0 (LEFT JOIN movie_stats). The buckets
--             widen roughly 10x each step (a log scale), because the
--             distribution is extremely skewed.
-- Params:     none
-- Output:     bucket, sort_order, movie_count, pct (share of all movies)
-- Summary statistics: e_ratings_per_movie_summary.sql.
WITH per_movie AS (
    SELECT coalesce(s.rating_count, 0) AS n
      FROM movies m
      LEFT JOIN movie_stats s ON s.movie_id = m.movie_id
),
buckets (sort_order, bucket, lo, hi) AS (
    VALUES ( 1, '0',            0,     0),
           ( 2, '1',            1,     1),
           ( 3, '2–5',          2,     5),
           ( 4, '6–10',         6,    10),
           ( 5, '11–50',       11,    50),
           ( 6, '51–100',      51,   100),
           ( 7, '101–500',    101,   500),
           ( 8, '501–1,000',  501,  1000),
           ( 9, '1,001–5,000', 1001, 5000),
           (10, '5,001+',    5001, NULL)
)
SELECT b.bucket,
       b.sort_order,
       count(p.n)                                             AS movie_count,
       round(100.0 * count(p.n) / sum(count(p.n)) OVER (), 2) AS pct
  FROM buckets b
  LEFT JOIN per_movie p ON p.n >= b.lo AND (b.hi IS NULL OR p.n <= b.hi)
 GROUP BY b.sort_order, b.bucket
 ORDER BY b.sort_order
