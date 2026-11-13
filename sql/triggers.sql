-- =============================================================================
-- sql/triggers.sql : keep movie_stats in step with ratings
--
-- ORDER MATTERS: run this only AFTER movie_stats has been bulk-populated from
-- ratings in Phase 4 (INSERT ... SELECT movie_id, count(*), sum(rating) ...).
-- If the trigger existed during the 25M-row COPY it would fire once per row,
-- making the load far slower, and the bulk populate would then double-count.
--
-- Two triggers on ratings:
--   ratings_movie_stats           row-level, INSERT / UPDATE / DELETE
--   ratings_truncate_movie_stats  statement-level, TRUNCATE (row-level triggers
--                                 do not fire on TRUNCATE, so without this one
--                                 movie_stats would silently keep stale totals)
--
-- SECURITY DEFINER: both functions run with the privileges of their OWNER
-- (the superuser that owns the tables), not the caller. The app role
-- movie_app_user may write only to ratings; without this, the trigger's write
-- to movie_stats would fail with "permission denied" on every rating change.
-- SET search_path = public stops a caller from hijacking table names by
-- putting their own schema first on the search path.
-- =============================================================================

CREATE OR REPLACE FUNCTION movie_stats_sync() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public AS $$
DECLARE
    k     INT;      -- histogram slot of a rating: 0.5 -> 1, 1.0 -> 2, ..., 5.0 -> 10
    first INT[];    -- histogram of a movie's very first rating
BEGIN
    -- An UPDATE that changes neither the movie nor the rating (e.g. only
    -- rated_at) does not affect the stats.
    IF TG_OP = 'UPDATE'
       AND NEW.movie_id = OLD.movie_id
       AND NEW.rating   = OLD.rating THEN
        RETURN NULL;
    END IF;

    -- Remove the old rating (DELETE, or the "before" half of an UPDATE).
    IF TG_OP IN ('DELETE', 'UPDATE') THEN
        k := (OLD.rating * 2)::int;
        UPDATE movie_stats
           SET rating_count   = rating_count - 1,
               rating_sum     = rating_sum   - OLD.rating,
               rating_hist[k] = rating_hist[k] - 1
         WHERE movie_id = OLD.movie_id;
    END IF;

    -- Add the new rating (INSERT, or the "after" half of an UPDATE).
    -- Creates the movie_stats row if this movie has never been rated.
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        k := (NEW.rating * 2)::int;
        first := array_fill(0, ARRAY[10]);
        first[k] := 1;
        INSERT INTO movie_stats (movie_id, rating_count, rating_sum, rating_hist)
        VALUES (NEW.movie_id, 1, NEW.rating, first)
        ON CONFLICT (movie_id) DO UPDATE
           SET rating_count   = movie_stats.rating_count + 1,
               rating_sum     = movie_stats.rating_sum   + EXCLUDED.rating_sum,
               rating_hist[k] = movie_stats.rating_hist[k] + 1;
    END IF;

    RETURN NULL;   -- return value is ignored for AFTER triggers
END;
$$;

DROP TRIGGER IF EXISTS ratings_movie_stats ON ratings;
CREATE TRIGGER ratings_movie_stats
    AFTER INSERT OR UPDATE OR DELETE ON ratings
    FOR EACH ROW EXECUTE FUNCTION movie_stats_sync();


-- TRUNCATE ratings removes every rating at once, so every stat is void too.
CREATE OR REPLACE FUNCTION movie_stats_truncate() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public AS $$
BEGIN
    TRUNCATE movie_stats;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS ratings_truncate_movie_stats ON ratings;
CREATE TRIGGER ratings_truncate_movie_stats
    AFTER TRUNCATE ON ratings
    FOR EACH STATEMENT EXECUTE FUNCTION movie_stats_truncate();
