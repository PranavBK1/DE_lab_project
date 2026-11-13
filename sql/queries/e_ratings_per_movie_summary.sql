-- (e) helper: summary statistics of rating_count over ALL 62,423 movies
--     (unrated movies count as 0).
--
-- Output:  movies, min, median (percentile_cont), mean, max,
--          top10pct_movies     = ceil(a tenth of all movies), the most-rated ones
--          top10pct_share_pct  = percent of ALL ratings that those movies received
WITH per_movie AS (
    SELECT coalesce(s.rating_count, 0) AS n
      FROM movies m
      LEFT JOIN movie_stats s ON s.movie_id = m.movie_id
),
ranked AS (
    SELECT n, row_number() OVER (ORDER BY n DESC) AS pos, count(*) OVER () AS movies
      FROM per_movie
)
SELECT max(movies)                                         AS movies,
       min(n)                                              AS min,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY n)      AS median,
       round(avg(n), 1)                                    AS mean,
       max(n)                                              AS max,
       ceil(max(movies) * 0.1)::int                        AS top10pct_movies,
       round(100.0 * sum(n) FILTER (WHERE pos <= ceil(movies * 0.1)) / sum(n), 1)
                                                           AS top10pct_share_pct
  FROM ranked
