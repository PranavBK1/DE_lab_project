-- =============================================================================
-- sql/analysis.sql : objects used by the Phase 6 analysis queries
--
-- Run by etl/load.py after constraints.sql and triggers.sql, and BEFORE
-- etl/setup_security.py, which grants SELECT on these objects to
-- movie_app_user (sql/roles.sql lists them explicitly). Re-runnable.
--
--   tag_stoplist           junk tags excluded from question (c), kept in ONE place
--   mv_popular_tags_genre  per (genre, tag): distinct users + applications
-- =============================================================================

-- ------------------------------------------------------------- tag_stoplist
-- Tags that say nothing about the movie: viewing status, media format, owner.
-- Stored trimmed + lowercased, like tags.tag. Edit this list here only.
CREATE TABLE IF NOT EXISTS tag_stoplist (
    tag  TEXT PRIMARY KEY CHECK (tag = lower(btrim(tag)) AND tag <> '')
);
COMMENT ON TABLE tag_stoplist IS
    'Junk user tags (viewing status, media format, ownership) excluded from question (c).';

INSERT INTO tag_stoplist (tag) VALUES
    -- required by the brief
    ('in netflix queue'), ('netflix queue'), ('to see'), ('seen'), ('watched'),
    ('owned'), ('dvd'), ('bd-r'), ('imdb top 250'),
    -- found by reviewing the most-used tags (10 more, ranked by distinct users)
    ('seen more than once'), ('netflix'), ('movie to see'), ('favorite'), ('library'),
    ('vhs'), ('seen at the cinema'), ('betamax'), ('own'), ('favorites')
ON CONFLICT (tag) DO NOTHING;


-- ------------------------------------------------------------- mv_popular_tags_genre
-- Question (c) needs count(DISTINCT user_id) per (genre, tag) over the
-- ~2.4M rows of tags x movie_genres, which takes several seconds. This
-- materialized view holds the result. It is safe to precompute because tags
-- cannot be edited in the app; etl/load.py rebuilds it on every load.
-- The stop list is NOT applied here, only in the query, so editing
-- tag_stoplist takes effect without a refresh.
DROP MATERIALIZED VIEW IF EXISTS mv_popular_tags_genre;
CREATE MATERIALIZED VIEW mv_popular_tags_genre AS
SELECT g.name                    AS genre,
       t.tag,
       count(DISTINCT t.user_id) AS users,
       count(*)                  AS applications
  FROM tags t
  JOIN movie_genres mg ON mg.movie_id = t.movie_id
  JOIN genres       g  ON g.genre_id  = mg.genre_id
 GROUP BY g.name, t.tag;

-- Unique index: allows REFRESH MATERIALIZED VIEW CONCURRENTLY later.
CREATE UNIQUE INDEX mv_popular_tags_genre_key ON mv_popular_tags_genre (genre, tag);
-- Serves the per-genre ranking (ORDER BY users DESC, applications DESC, tag).
CREATE INDEX mv_popular_tags_genre_rank_idx
    ON mv_popular_tags_genre (genre, users DESC, applications DESC, tag);

ANALYZE tag_stoplist;
ANALYZE mv_popular_tags_genre;
