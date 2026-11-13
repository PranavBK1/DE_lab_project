-- =============================================================================
-- sql/migrations/003_rating_histogram.sql
--
-- Question (d) "distribution of users' ratings for a movie" used to count the
-- movie's rows in ratings. For blockbusters (~80k ratings) those rows are spread
-- over ~400 MB of the 1.2 GB table (it is stored in user order), so with little
-- free RAM the first view took 6-10 s.
--
-- Fix: keep a 10-value histogram per movie in movie_stats, maintained by the
-- existing trigger (sql/triggers.sql). (d) then reads ONE row.
-- rating_hist[k] = number of ratings equal to k/2 stars (k = 1..10).
--
-- Re-runnable. A fresh full load (etl/load.py) already produces this state.
-- Run via etl/migrate.py, which re-applies triggers.sql right after this file.
-- =============================================================================

ALTER TABLE movie_stats
    ADD COLUMN IF NOT EXISTS rating_hist INT[] NOT NULL DEFAULT '{0,0,0,0,0,0,0,0,0,0}';

-- (Re)compute every histogram from ratings: one sequential pass over the table.
UPDATE movie_stats s
   SET rating_hist = h.hist
  FROM (SELECT movie_id,
               ARRAY[count(*) FILTER (WHERE rating = 0.5), count(*) FILTER (WHERE rating = 1.0),
                     count(*) FILTER (WHERE rating = 1.5), count(*) FILTER (WHERE rating = 2.0),
                     count(*) FILTER (WHERE rating = 2.5), count(*) FILTER (WHERE rating = 3.0),
                     count(*) FILTER (WHERE rating = 3.5), count(*) FILTER (WHERE rating = 4.0),
                     count(*) FILTER (WHERE rating = 4.5), count(*) FILTER (WHERE rating = 5.0)
               ]::int[] AS hist
          FROM ratings
         GROUP BY movie_id) h
 WHERE h.movie_id = s.movie_id
   AND s.rating_hist IS DISTINCT FROM h.hist;

-- Movies whose last rating was deleted keep a row with count 0: all-zero histogram.
UPDATE movie_stats SET rating_hist = '{0,0,0,0,0,0,0,0,0,0}'
 WHERE rating_count = 0 AND rating_hist <> '{0,0,0,0,0,0,0,0,0,0}';

-- The histogram must always agree with rating_count.
ALTER TABLE movie_stats DROP CONSTRAINT IF EXISTS movie_stats_hist_valid;
ALTER TABLE movie_stats ADD CONSTRAINT movie_stats_hist_valid CHECK (
    cardinality(rating_hist) = 10
    AND rating_hist[1] + rating_hist[2] + rating_hist[3] + rating_hist[4] + rating_hist[5]
      + rating_hist[6] + rating_hist[7] + rating_hist[8] + rating_hist[9] + rating_hist[10]
      = rating_count);
