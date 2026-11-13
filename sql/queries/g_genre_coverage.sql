-- (g) How many movies (and ratings) does each genre cover?
--
-- Definition: per genre, the number of movies and the percent of ALL 62,423 movies,
--             plus the ratings those movies received and the percent of all ratings.
--             A "(no genre)" row covers the 5,062 movies listed as
--             "(no genres listed)".
-- NOTE:       the percentages add up to MORE than 100 percent, because a movie with
--             several genres is counted once in each of them (107,245
--             movie-genre pairs for 62,423 movies).
-- Params:     none
-- Output:     genre, movie_count, pct_of_all_movies, rating_count, pct_of_all_ratings
-- movie_stats rule: LEFT JOIN; a missing row counts as rating_count = 0.
WITH per_movie AS (
    SELECT m.movie_id, coalesce(s.rating_count, 0) AS n
      FROM movies m
      LEFT JOIN movie_stats s ON s.movie_id = m.movie_id
),
totals AS (
    SELECT count(*) AS movies, sum(n) AS ratings FROM per_movie
),
genre_rows AS (
    SELECT g.name AS genre,
           count(p.movie_id)     AS movie_count,
           coalesce(sum(p.n), 0) AS rating_count
      FROM genres g
      LEFT JOIN movie_genres mg ON mg.genre_id = g.genre_id
      LEFT JOIN per_movie    p  ON p.movie_id  = mg.movie_id
     GROUP BY g.name
    UNION ALL
    SELECT '(no genre)', count(*), coalesce(sum(p.n), 0)
      FROM per_movie p
     WHERE NOT EXISTS (SELECT 1 FROM movie_genres mg WHERE mg.movie_id = p.movie_id)
)
SELECT r.genre,
       r.movie_count,
       round(100.0 * r.movie_count  / t.movies,  2) AS pct_of_all_movies,
       r.rating_count,
       round(100.0 * r.rating_count / t.ratings, 2) AS pct_of_all_ratings
  FROM genre_rows r CROSS JOIN totals t
 ORDER BY (r.genre = '(no genre)'), r.movie_count DESC, r.genre
