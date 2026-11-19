-- Overview page: headline numbers of the dataset (one row).
--
-- Live (the app can change them, and they are cheap):
--   movies, users (MovieLens users + app accounts), ratings (sum of
--   movie_stats.rating_count, kept current by the trigger)
-- From mv_dataset_summary (built at load; a live scan of 25M rows takes ~5 s):
--   tags, genome_movies, first_rated_at, last_rated_at (MovieLens rating period)
-- Also live: genome_tags (the 1,128-tag Tag Genome vocabulary). Not to be confused
-- with tags = the 1,093,350 free-text tags users applied to movies.
-- Output: movies, users, ratings, tags, genome_tags, genome_movies, genome_pct,
--         first_rated_at, last_rated_at
SELECT (SELECT count(*) FROM movies)                               AS movies,
       (SELECT count(*) FROM users)                                AS users,
       (SELECT coalesce(sum(rating_count), 0) FROM movie_stats)    AS ratings,
       d.tags,
       (SELECT count(*) FROM genome_tags)                          AS genome_tags,
       d.genome_movies,
       round(100.0 * d.genome_movies / (SELECT count(*) FROM movies), 1) AS genome_pct,
       d.first_rated_at,
       d.last_rated_at
  FROM mv_dataset_summary d
