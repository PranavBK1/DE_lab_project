-- =============================================================================
-- sql/roles.sql : database roles, grants, row-level security, login lookup
--                 (Phase 5)
--
-- Run by etl/setup_security.py as the superuser, AFTER the tables AND the
-- Phase 6 analysis objects (sql/analysis.sql) exist, and after
-- sql/extensions.sql (pgcrypto, used by auth_login).
-- Re-runnable: roles are created only if missing, grants are reset and
-- re-applied, policies are dropped and re-created.
-- Passwords are NOT in this file: setup_security.py sets them from .env.
--
-- Two roles, least privilege:
--   movie_admin     the Admin pages: full control of the data
--   movie_app_user  every logged-in "user": read the data, write only ratings,
--                   and only their OWN ratings (enforced by row-level security)
-- The app never connects as the superuser.
-- =============================================================================

-- ------------------------------------------------------------- roles
-- CREATE ROLE has no IF NOT EXISTS, so check pg_roles first.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'movie_admin') THEN
        CREATE ROLE movie_admin LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'movie_app_user') THEN
        CREATE ROLE movie_app_user LOGIN;
    END IF;
END
$$;

-- movie_admin is not subject to row-level security (it manages all ratings).
ALTER ROLE movie_admin    BYPASSRLS;
-- movie_app_user explicitly IS subject to it (the default, stated for clarity).
ALTER ROLE movie_app_user NOBYPASSRLS;


-- ------------------------------------------------------------- start clean
-- Remove earlier grants so a re-run gives exactly the grants below.
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM movie_admin, movie_app_user;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM movie_admin, movie_app_user;
REVOKE ALL (user_id, username, password_hash, role, created_at) ON users FROM movie_app_user;
REVOKE ALL (user_id, movie_id, rating, rated_at) ON ratings FROM movie_app_user;


-- ------------------------------------------------------------- both roles
-- Both roles may connect to this database and see objects in schema public.
-- (Database name taken from current_database(), so it is not hard-coded.)
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO movie_admin, movie_app_user',
                   current_database());
END
$$;
GRANT USAGE ON SCHEMA public TO movie_admin, movie_app_user;


-- ------------------------------------------------------------- movie_admin
-- Admin: every privilege on every table (incl. DELETE, users.password_hash)
-- and on the sequences (needed to create new users: users_user_id_seq).
GRANT ALL ON ALL TABLES    IN SCHEMA public TO movie_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO movie_admin;
-- Stated explicitly for the Admin page: new movies and new app accounts take
-- their ids from these sequences (already covered by the line above).
GRANT USAGE ON SEQUENCE movies_movie_id_seq, users_user_id_seq TO movie_admin;


-- ------------------------------------------------------------- movie_app_user
-- Read every table EXCEPT users (users gets column-level SELECT just below).
GRANT SELECT ON movies, genres, movie_genres, ratings, tags,
                links, genome_tags, genome_scores, movie_stats
      TO movie_app_user;

-- Phase 6 analysis objects (sql/analysis.sql). Listed explicitly: every new
-- table, view or materialized view the queries read MUST be added here, or
-- movie_app_user gets "permission denied" (a full reload re-runs this file).
GRANT SELECT ON tag_stoplist,             -- junk tags excluded from question (c)
                mv_popular_tags_genre,    -- per (genre, tag) counts for question (c)
                mv_dataset_summary        -- dataset facts for the Overview page
      TO movie_app_user;

-- users: only these 4 columns, so the app role can NEVER read password_hash
-- (SELECT password_hash ... or SELECT * fails with "permission denied").
GRANT SELECT (user_id, username, role, created_at) ON users TO movie_app_user;

-- ratings: the ONLY table this role may write to.
--   INSERT a new rating (these 4 columns), UPDATE only the value and its time.
--   No DELETE, and user_id / movie_id of an existing rating cannot be changed.
GRANT INSERT (user_id, movie_id, rating, rated_at) ON ratings TO movie_app_user;
GRANT UPDATE (rating, rated_at)                    ON ratings TO movie_app_user;

-- No write grants on any other table. movie_stats is still kept current when
-- this role rates a movie: the trigger function is SECURITY DEFINER
-- (sql/triggers.sql), so its write runs with the table owner's rights.


-- ------------------------------------------------------------- row-level security
-- The DATABASE enforces "a user may modify only their own ratings", not just
-- the app. The app sets the logged-in user per transaction:
--     SELECT set_config('app.current_user_id', '<id>', true)
-- current_setting(.., true) returns NULL when unset, and nullif turns the ''
-- left over after a transaction into NULL too. NULL never equals user_id, so
-- with no user set every INSERT / UPDATE is refused.
-- The table owner (superuser) and movie_admin (BYPASSRLS) are not affected.
ALTER TABLE ratings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ratings_select_all ON ratings;
DROP POLICY IF EXISTS ratings_insert_own ON ratings;
DROP POLICY IF EXISTS ratings_update_own ON ratings;

-- Everyone may READ all ratings (the dashboard charts need them).
CREATE POLICY ratings_select_all ON ratings
    FOR SELECT TO movie_app_user
    USING (true);

-- A new rating must belong to the logged-in user.
CREATE POLICY ratings_insert_own ON ratings
    FOR INSERT TO movie_app_user
    WITH CHECK (user_id = nullif(current_setting('app.current_user_id', true), '')::int);

-- Only your own rows are visible to UPDATE (others: 0 rows affected), and the
-- row must still be yours afterwards.
CREATE POLICY ratings_update_own ON ratings
    FOR UPDATE TO movie_app_user
    USING      (user_id = nullif(current_setting('app.current_user_id', true), '')::int)
    WITH CHECK (user_id = nullif(current_setting('app.current_user_id', true), '')::int);

-- No DELETE policy (and no DELETE grant): app users cannot delete ratings.


-- ------------------------------------------------------------- login check
-- The password is checked INSIDE the database with pgcrypto's bcrypt, so the
-- hash never leaves PostgreSQL: the app role can neither SELECT password_hash
-- nor receive it from a function. auth_login returns (user_id, username, role)
-- only when the password is right, and no row otherwise.
-- SECURITY DEFINER: runs as the owner, who may read password_hash.
-- SET search_path = public: a caller cannot substitute their own "users" or
-- "crypt". When there is no usable hash (unknown user, or a MovieLens user
-- with NULL password_hash), a throw-away bcrypt hash of the same cost is still
-- computed, so the response time does not reveal whether the user exists.
DROP FUNCTION IF EXISTS auth_get_user(text);          -- the old design returned the hash

CREATE OR REPLACE FUNCTION auth_login(p_username text, p_password text)
RETURNS TABLE (user_id int, username text, role text)
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public AS $$
DECLARE
    u record;
BEGIN
    SELECT us.user_id, us.username, us.role, us.password_hash
      INTO u
      FROM users us
     WHERE us.username = p_username;

    IF u.password_hash IS NULL THEN                    -- unknown user or no password
        PERFORM crypt(coalesce(p_password, ''), gen_salt('bf', 12));
        RETURN;
    END IF;

    IF u.password_hash = crypt(coalesce(p_password, ''), u.password_hash) THEN
        RETURN QUERY SELECT u.user_id, u.username, u.role;
    END IF;
END;
$$;

-- New functions are executable by PUBLIC by default; allow only the app role.
REVOKE EXECUTE ON FUNCTION auth_login(text, text) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION auth_login(text, text) TO movie_app_user;
