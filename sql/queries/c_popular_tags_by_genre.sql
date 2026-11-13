-- (c) What are the most popular user tags in each genre?
--
-- Definition: popularity = number of DISTINCT users who applied the tag to
--             movies of that genre. Raw counts are skewed: the top 1 percent of
--             taggers wrote 54 percent of all tags (e.g. "woman director": 3,590
--             applications by only 35 users), so one person could dominate.
--             The raw application count is returned too, as a second key.
--             Junk tags ("in netflix queue", "dvd", ...) are excluded via the
--             tag_stoplist table, the ONE place the stop list is kept.
-- Ranking:    ROW_NUMBER() OVER (PARTITION BY genre
--                                ORDER BY users DESC, applications DESC, tag)
-- Params:     %(top_n)s (int, default 5)
--             %(genre)s (genre name, or NULL = all 19 genres)
-- Output:     genre, rank, tag, users, applications
-- Source:     mv_popular_tags_genre (per genre x tag counts; see sql/analysis.sql).
--             Computing it from tags x movie_genres on the fly takes ~10 s;
--             tags are not editable in the app, so a materialized view
--             refreshed by etl/load.py is safe.
-- Speed:      ranking all 271k (genre, tag) rows in one sort spills to disk
--             (~1.5 s). Instead, for each genre (LATERAL) the index
--             mv_popular_tags_genre_rank_idx returns the rows already in
--             rank order and LIMIT stops after top_n: a few ms. The
--             ROW_NUMBER() is computed within one genre, so its result is
--             the same as one big PARTITION BY genre.
SELECT g.name AS genre, t.rank, t.tag, t.users, t.applications
  FROM genres g
 CROSS JOIN LATERAL (
        SELECT row_number() OVER (PARTITION BY p.genre
                                  ORDER BY p.users DESC, p.applications DESC, p.tag) AS rank,
               p.tag, p.users, p.applications
          FROM mv_popular_tags_genre p
         WHERE p.genre = g.name
           AND NOT EXISTS (SELECT 1 FROM tag_stoplist s WHERE s.tag = p.tag)
         ORDER BY p.users DESC, p.applications DESC, p.tag
         LIMIT %(top_n)s
       ) t
 WHERE (%(genre)s::text IS NULL OR g.name = %(genre)s::text)
 ORDER BY g.name, t.rank
