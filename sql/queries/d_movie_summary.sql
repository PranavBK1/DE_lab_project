-- (d) helper: one movie's title, total number of ratings and average.
--
-- Params:  %(movie_id)s
-- Output:  movie_id, title, release_year, rating_count (0 if never rated),
--          avg_rating (NULL if never rated)
-- movie_stats rule: LEFT JOIN; a missing row counts as rating_count = 0.
SELECT m.movie_id,
       m.title,
       m.release_year,
       coalesce(s.rating_count, 0) AS rating_count,
       s.avg_rating
  FROM movies m
  LEFT JOIN movie_stats s ON s.movie_id = m.movie_id
 WHERE m.movie_id = %(movie_id)s
