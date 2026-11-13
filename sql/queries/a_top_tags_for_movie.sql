-- (a) Which genome tags describe a movie best?
--
-- Definition: the 5 genome tags with the highest relevance for the movie
--             (tie-break: tag name). Relevance is the Tag Genome score, 0..1.
-- Params:     %(movie_id)s
-- Output:     rank, tag, relevance (rounded to 3 decimals)
-- Zero rows = "No genome data for this movie": only 13,816 of the 62,423
-- movies have genome scores.
-- Index:      genome_scores_movie_rel_idx (movie_id, relevance DESC)
SELECT row_number() OVER (ORDER BY gs.relevance DESC, gt.tag) AS rank,
       gt.tag,
       round(gs.relevance::numeric, 3)                       AS relevance
  FROM genome_scores gs
  JOIN genome_tags   gt ON gt.tag_id = gs.tag_id
 WHERE gs.movie_id = %(movie_id)s
 ORDER BY gs.relevance DESC, gt.tag
 LIMIT 5
