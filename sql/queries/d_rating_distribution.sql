-- (d) How are a movie's ratings distributed over the star values?
--
-- Definition: count of the movie's ratings at each of the 10 values
--             0.5, 1.0, ..., 5.0. Every value is always present, with 0 where
--             nobody chose it.
-- Source:     movie_stats.rating_hist, a 10-slot histogram per movie kept
--             current by the ratings trigger (rating_hist[k] = ratings equal
--             to k/2 stars). Reading ONE row replaces counting up to ~80k
--             ratings scattered across the 25M-row table (6-10 s cold -> ~1 ms).
--             A CHECK constraint guarantees sum(rating_hist) = rating_count.
-- Params:     %(movie_id)s
-- Output:     rating, count, pct (share of this movie's ratings, 2 decimals;
--             0 for an unrated movie)
-- movie_stats rule: LEFT JOIN; a missing row counts as 0 ratings.
-- Total and average: d_movie_summary.sql.
SELECT v.rating,
       coalesce(s.rating_hist[(v.rating * 2)::int], 0) AS count,
       coalesce(round(100.0 * s.rating_hist[(v.rating * 2)::int]
                      / nullif(s.rating_count, 0), 2), 0) AS pct
  FROM generate_series(0.5, 5.0, 0.5) AS v(rating)
  LEFT JOIN movie_stats s ON s.movie_id = %(movie_id)s
 ORDER BY v.rating
