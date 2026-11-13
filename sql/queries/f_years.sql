-- (f) helper: release years that have at least one movie, for the year dropdown.
--
-- Output:  release_year, movie_count   (newest first; 412 movies have no year)
SELECT release_year, count(*) AS movie_count
  FROM movies
 WHERE release_year IS NOT NULL
 GROUP BY release_year
 ORDER BY release_year DESC
