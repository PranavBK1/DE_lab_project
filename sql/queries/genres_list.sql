-- Helper for (c): the 19 genres, for the genre dropdown.
-- Output:  genre_id, genre
SELECT genre_id, name AS genre
  FROM genres
 ORDER BY name
