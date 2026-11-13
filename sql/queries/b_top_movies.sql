-- (b) Which movies have the highest average rating, overall and per release year?
--
-- Definition: top 10 by avg_rating among movies with at least min_ratings
--             ratings (default 50), so a film with one 5-star rating cannot
--             top the list. Tie-break: rating_count DESC, then title.
--             Read from movie_stats (kept current by trigger), not from the
--             25M-row ratings table.
-- Params:     %(min_ratings)s  (int, default 50)
--             %(release_year)s (int, or NULL = all years)
-- Output:     rank, movie_id, title, release_year, avg_rating, rating_count
-- movie_stats rule: LEFT JOIN; a missing row counts as rating_count = 0.
SELECT row_number() OVER (ORDER BY s.avg_rating DESC NULLS LAST,
                                   coalesce(s.rating_count, 0) DESC, m.title) AS rank,
       m.movie_id,
       m.title,
       m.release_year,
       s.avg_rating,
       coalesce(s.rating_count, 0) AS rating_count
  FROM movies m
  LEFT JOIN movie_stats s ON s.movie_id = m.movie_id
 WHERE coalesce(s.rating_count, 0) >= %(min_ratings)s
   AND (%(release_year)s::int IS NULL OR m.release_year = %(release_year)s::int)
 ORDER BY rank
 LIMIT 10
