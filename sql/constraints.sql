-- =============================================================================
-- sql/constraints.sql : foreign keys + secondary indexes (Phase 4, after load)
--
-- Run AFTER the bulk COPY. Re-runnable: each FK is dropped if present and
-- re-added; indexes use IF NOT EXISTS.
--
-- ON DELETE CASCADE only where the child row has no meaning without its movie
-- (movie_genres, links, genome_scores, movie_stats). ratings and tags keep the
-- default (NO ACTION / RESTRICT-like): deleting a movie or user that still has
-- ratings or tags is refused, so user-generated data is never silently lost.
-- =============================================================================

-- ------------------------------------------------------------- foreign keys
ALTER TABLE movie_genres  DROP CONSTRAINT IF EXISTS movie_genres_movie_fk;
ALTER TABLE movie_genres  ADD  CONSTRAINT movie_genres_movie_fk
    FOREIGN KEY (movie_id) REFERENCES movies (movie_id) ON DELETE CASCADE;

ALTER TABLE movie_genres  DROP CONSTRAINT IF EXISTS movie_genres_genre_fk;
ALTER TABLE movie_genres  ADD  CONSTRAINT movie_genres_genre_fk
    FOREIGN KEY (genre_id) REFERENCES genres (genre_id);

ALTER TABLE ratings       DROP CONSTRAINT IF EXISTS ratings_user_fk;
ALTER TABLE ratings       ADD  CONSTRAINT ratings_user_fk
    FOREIGN KEY (user_id) REFERENCES users (user_id);

ALTER TABLE ratings       DROP CONSTRAINT IF EXISTS ratings_movie_fk;
ALTER TABLE ratings       ADD  CONSTRAINT ratings_movie_fk
    FOREIGN KEY (movie_id) REFERENCES movies (movie_id);

ALTER TABLE tags          DROP CONSTRAINT IF EXISTS tags_user_fk;
ALTER TABLE tags          ADD  CONSTRAINT tags_user_fk
    FOREIGN KEY (user_id) REFERENCES users (user_id);

ALTER TABLE tags          DROP CONSTRAINT IF EXISTS tags_movie_fk;
ALTER TABLE tags          ADD  CONSTRAINT tags_movie_fk
    FOREIGN KEY (movie_id) REFERENCES movies (movie_id);

ALTER TABLE links         DROP CONSTRAINT IF EXISTS links_movie_fk;
ALTER TABLE links         ADD  CONSTRAINT links_movie_fk
    FOREIGN KEY (movie_id) REFERENCES movies (movie_id) ON DELETE CASCADE;

ALTER TABLE genome_scores DROP CONSTRAINT IF EXISTS genome_scores_movie_fk;
ALTER TABLE genome_scores ADD  CONSTRAINT genome_scores_movie_fk
    FOREIGN KEY (movie_id) REFERENCES movies (movie_id) ON DELETE CASCADE;

ALTER TABLE genome_scores DROP CONSTRAINT IF EXISTS genome_scores_tag_fk;
ALTER TABLE genome_scores ADD  CONSTRAINT genome_scores_tag_fk
    FOREIGN KEY (tag_id) REFERENCES genome_tags (tag_id);

ALTER TABLE movie_stats   DROP CONSTRAINT IF EXISTS movie_stats_movie_fk;
ALTER TABLE movie_stats   ADD  CONSTRAINT movie_stats_movie_fk
    FOREIGN KEY (movie_id) REFERENCES movies (movie_id) ON DELETE CASCADE;


-- ------------------------------------------------------------- indexes
-- ratings PK is (user_id, movie_id): good for "my ratings"; this one serves per-movie lookups.
CREATE INDEX IF NOT EXISTS ratings_movie_idx        ON ratings (movie_id);
CREATE INDEX IF NOT EXISTS tags_movie_idx           ON tags (movie_id);
CREATE INDEX IF NOT EXISTS tags_lower_tag_idx       ON tags (lower(tag));
CREATE INDEX IF NOT EXISTS movie_genres_genre_idx   ON movie_genres (genre_id);
CREATE INDEX IF NOT EXISTS movies_release_year_idx  ON movies (release_year);
-- text_pattern_ops lets  lower(title) LIKE 'abc%'  use the index (title autocomplete).
CREATE INDEX IF NOT EXISTS movies_lower_title_idx   ON movies (lower(title) text_pattern_ops);
-- top-N genome tags for one movie, already sorted by relevance.
CREATE INDEX IF NOT EXISTS genome_scores_movie_rel_idx ON genome_scores (movie_id, relevance DESC);


-- ------------------------------------------------------------- planner stats
ANALYZE;
