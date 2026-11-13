-- (a) helper: well-known movies that DO have genome data, suggested when the
-- chosen movie has none. The most-rated movies come first.
-- Params:  %(limit)s (default 3)
-- Output:  movie_id, title, release_year, rating_count
SELECT m.movie_id, m.title, m.release_year, s.rating_count
  FROM movie_stats s
  JOIN movies m ON m.movie_id = s.movie_id
 WHERE EXISTS (SELECT 1 FROM genome_scores g WHERE g.movie_id = s.movie_id)
 ORDER BY s.rating_count DESC, m.title
 LIMIT %(limit)s
