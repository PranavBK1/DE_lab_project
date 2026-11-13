-- My Ratings page: one user's ratings, newest first, one page at a time.
-- PER-USER DATA: never put the result in a shared cache.
-- Params:  %(user_id)s, %(limit)s (25), %(offset)s
-- Output:  movie_id, title, release_year, my_rating, avg_rating (the movie's
--          average over all users), rated_at (UTC), total (all of this user's
--          ratings, for the page count)
SELECT r.movie_id,
       m.title,
       m.release_year,
       r.rating          AS my_rating,
       s.avg_rating,
       r.rated_at,
       count(*) OVER ()  AS total
  FROM ratings r
  JOIN movies m           ON m.movie_id = r.movie_id
  LEFT JOIN movie_stats s ON s.movie_id = r.movie_id
 WHERE r.user_id = %(user_id)s
 ORDER BY r.rated_at DESC, r.movie_id
 LIMIT %(limit)s OFFSET %(offset)s
