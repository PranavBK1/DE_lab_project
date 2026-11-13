-- =============================================================================
-- sql/schema.sql : MovieLens 25M tables (Phase 3)
--
-- Drops and recreates every table, so it is safe to re-run.
-- Only primary keys, UNIQUE and CHECK constraints are created here.
-- Foreign keys and secondary indexes live in sql/constraints.sql and are
-- applied AFTER the bulk load (Phase 4): loading ~41M rows into tables
-- without FKs/indexes is much faster.
-- The movie_stats trigger lives in sql/triggers.sql.
--
-- All TIMESTAMP columns hold UTC. The cleaned CSVs contain UTC strings
-- ('YYYY-MM-DD HH:MM:SS', converted from Unix epoch seconds), and we store
-- them as TIMESTAMP (without time zone), so read every value as UTC.
-- =============================================================================

-- CASCADE also removes any foreign keys and triggers created by the other files.
DROP TABLE IF EXISTS movie_stats   CASCADE;
DROP TABLE IF EXISTS genome_scores CASCADE;
DROP TABLE IF EXISTS genome_tags   CASCADE;
DROP TABLE IF EXISTS links         CASCADE;
DROP TABLE IF EXISTS tags          CASCADE;
DROP TABLE IF EXISTS ratings       CASCADE;
DROP TABLE IF EXISTS movie_genres  CASCADE;
DROP TABLE IF EXISTS genres        CASCADE;
DROP TABLE IF EXISTS users         CASCADE;
DROP TABLE IF EXISTS movies        CASCADE;
DROP SEQUENCE IF EXISTS users_user_id_seq;
DROP FUNCTION IF EXISTS movie_stats_sync() CASCADE;
DROP FUNCTION IF EXISTS movie_stats_truncate() CASCADE;


-- ----------------------------------------------------------------- movies
CREATE TABLE movies (
    movie_id      INT      PRIMARY KEY,
    title         TEXT     NOT NULL,
    release_year  SMALLINT NULL          -- extracted from "Title (1995)"; NULL if absent
);
COMMENT ON TABLE movies IS
    'One row per MovieLens movie. release_year was extracted from the trailing "(YYYY)" of the raw title.';


-- ----------------------------------------------------------------- genres
CREATE TABLE genres (
    genre_id  SMALLINT PRIMARY KEY,
    name      TEXT     NOT NULL UNIQUE
);
COMMENT ON TABLE genres IS
    'Lookup of the 19 distinct genres split out of the pipe-separated movies.genres field.';


-- ----------------------------------------------------------------- movie_genres
CREATE TABLE movie_genres (
    movie_id  INT,
    genre_id  SMALLINT,
    PRIMARY KEY (movie_id, genre_id)
);
COMMENT ON TABLE movie_genres IS
    'Many-to-many link: one row per (movie, genre). Movies with "(no genres listed)" have no rows.';


-- ----------------------------------------------------------------- users
-- MovieLens users (ids 1..162541) are loaded with explicit ids and have NULL
-- username/password_hash, so they cannot log in. Accounts created by the app
-- take ids from this sequence, which starts at 200000 so they never collide.
CREATE SEQUENCE users_user_id_seq START WITH 200000;

CREATE TABLE users (
    user_id        INT       PRIMARY KEY DEFAULT nextval('users_user_id_seq'),
    username       TEXT      UNIQUE NULL,
    password_hash  TEXT      NULL,                       -- bcrypt hash; NULL = cannot log in
    role           TEXT      NOT NULL DEFAULT 'user'
                             CHECK (role IN ('admin', 'user')),
    created_at     TIMESTAMP NOT NULL DEFAULT now()      -- UTC (see header)
);
ALTER SEQUENCE users_user_id_seq OWNED BY users.user_id;
COMMENT ON TABLE users IS
    'Every MovieLens userId (no login) plus app accounts (username + bcrypt hash, id >= 200000).';


-- ----------------------------------------------------------------- ratings
CREATE TABLE ratings (
    user_id   INT,
    movie_id  INT,
    rating    NUMERIC(2,1) NOT NULL
              CHECK (rating BETWEEN 0.5 AND 5.0 AND rating * 2 = floor(rating * 2)),
    rated_at  TIMESTAMP    NOT NULL DEFAULT now(),       -- UTC
    PRIMARY KEY (user_id, movie_id)
);
COMMENT ON TABLE ratings IS
    'One star rating (0.5..5.0 in half steps) per (user, movie); duplicates resolved to the latest in cleaning.';


-- ----------------------------------------------------------------- tags
CREATE TABLE tags (
    tag_row_id  BIGINT    PRIMARY KEY,                   -- surrogate key
    user_id     INT       NOT NULL,
    movie_id    INT       NOT NULL,
    tag         TEXT      NOT NULL CHECK (tag <> ''),    -- trimmed + lowercased in cleaning
    tagged_at   TIMESTAMP NOT NULL                       -- UTC
);
COMMENT ON TABLE tags IS
    'One free-text tag applied by a user to a movie. Surrogate key because the raw file has no id.';


-- ----------------------------------------------------------------- links
CREATE TABLE links (
    movie_id  INT  PRIMARY KEY,
    imdb_id   TEXT,                  -- text to keep leading zeros
    tmdb_id   INT  NULL
);
COMMENT ON TABLE links IS
    'External identifiers (IMDb, TMDb) for each movie; 1:1 with movies.';


-- ----------------------------------------------------------------- genome_tags
CREATE TABLE genome_tags (
    tag_id  SMALLINT PRIMARY KEY,
    tag     TEXT     NOT NULL
);
COMMENT ON TABLE genome_tags IS
    'The 1,128 curated tags of the MovieLens Tag Genome.';


-- ----------------------------------------------------------------- genome_scores
CREATE TABLE genome_scores (
    movie_id   INT,
    tag_id     SMALLINT,
    relevance  REAL NOT NULL CHECK (relevance BETWEEN 0 AND 1),
    PRIMARY KEY (movie_id, tag_id)
);
COMMENT ON TABLE genome_scores IS
    'Relevance (0..1) of each genome tag to a movie; 13,816 movies x 1,128 tags.';


-- ----------------------------------------------------------------- movie_stats
-- Deliberate denormalisation: per-movie aggregates of ratings, kept current by
-- the trigger in sql/triggers.sql so dashboard queries avoid scanning 25M rows.
CREATE TABLE movie_stats (
    movie_id      INT           PRIMARY KEY,
    rating_count  INT           NOT NULL DEFAULT 0 CHECK (rating_count >= 0),
    rating_sum    NUMERIC(12,1) NOT NULL DEFAULT 0,
    avg_rating    NUMERIC(4,3)  GENERATED ALWAYS AS
                  (CASE WHEN rating_count > 0 THEN rating_sum / rating_count END) STORED
);
COMMENT ON TABLE movie_stats IS
    'Denormalised per-movie rating count/sum/avg, maintained by trigger ratings_movie_stats.';
