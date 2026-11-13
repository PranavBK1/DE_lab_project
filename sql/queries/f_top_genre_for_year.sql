-- (f) Which genre had the most releases in a given year?
--
-- Definition: number of movies released that year in each genre (a movie
--             with 3 genres counts once in each). ALL 19 genres are returned,
--             ranked with RANK(), so ties share rank 1 and every tied genre
--             has is_top = true: ties are shown, not hidden.
--             A year with no movies has no top genre (is_top false everywhere).
-- Params:     %(release_year)s (int; the dropdown list comes from f_years.sql)
-- Output:     rank, genre, movie_count, is_top
WITH year_genres AS (
    SELECT mg.genre_id
      FROM movies m
      JOIN movie_genres mg ON mg.movie_id = m.movie_id
     WHERE m.release_year = %(release_year)s
),
counts AS (
    SELECT g.name AS genre, count(y.genre_id) AS movie_count
      FROM genres g
      LEFT JOIN year_genres y ON y.genre_id = g.genre_id
     GROUP BY g.name
)
SELECT rank() OVER (ORDER BY movie_count DESC)                         AS rank,
       genre,
       movie_count,
       (rank() OVER (ORDER BY movie_count DESC) = 1 AND movie_count > 0) AS is_top
  FROM counts
 ORDER BY rank, genre
