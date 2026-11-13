-- The logged-in user's own rating of one movie (one row, or none).
-- PER-USER DATA: never put the result in a shared cache.
-- Params:  %(user_id)s, %(movie_id)s
-- Output:  rating, rated_at
SELECT r.rating, r.rated_at
  FROM ratings r
 WHERE r.user_id = %(user_id)s AND r.movie_id = %(movie_id)s
