"""Cached read functions for the pages (the queries themselves are in queries.py).

st.cache_data keeps each result for 10 minutes, shared by every user. That is
safe ONLY for data that is the same for everybody, so per-user reads
(queries.my_ratings, queries.my_rating_for_movie) are deliberately NOT here:
pages call them directly from queries.py.

After ANY successful write (a rating, an admin edit) call clear(): the
ratings trigger updates movie_stats immediately, so cached results for (b),
(d), (e), (g), the overview and search ordering would otherwise be stale.
(a) and (c) do not depend on ratings, but clearing everything is simpler and
always correct.
"""
import streamlit as st

import queries

TTL = 600          # seconds


def _cached(func):
    return st.cache_data(ttl=TTL, show_spinner=False)(func)


overview_metrics = _cached(queries.overview_metrics)
search_movies = _cached(queries.search_movies)
movie_summary = _cached(queries.movie_summary)
list_genres = _cached(queries.list_genres)
list_years = _cached(queries.list_years)
genome_suggestions = _cached(queries.genome_suggestions)

top_tags_for_movie = _cached(queries.top_tags_for_movie)                         # (a)
top_movies = _cached(queries.top_movies)                                         # (b)
popular_tags_by_genre = _cached(queries.popular_tags_by_genre)                   # (c)
rating_distribution = _cached(queries.rating_distribution)                       # (d)
ratings_per_movie_distribution = _cached(queries.ratings_per_movie_distribution)  # (e)
ratings_per_movie_summary = _cached(queries.ratings_per_movie_summary)           # (e)
top_genre_for_year = _cached(queries.top_genre_for_year)                         # (f)
genre_coverage = _cached(queries.genre_coverage)                                 # (g)


def clear():
    """Drop every cached result. Call after every successful write."""
    st.cache_data.clear()
