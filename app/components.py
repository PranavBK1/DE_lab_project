"""Shared widgets used by several pages."""
import logging

import psycopg
import streamlit as st

import data
import queries
from ratings import VALID_RATINGS, upsert_my_rating

log = logging.getLogger("movielens.app")

MOVIE_KEY = "movie_id"            # the chosen movie, shared by (a), (d) and My Ratings
RATING_STEPS = [float(r) for r in VALID_RATINGS]


# ----------------------------------------------------------------- formatting
def fmt_int(n):
    return f"{int(n):,}"


def fmt_year(year):
    return "" if year is None or year != year else f" ({int(year)})"     # NaN-safe


def movie_label(row):
    """'The Matrix (1999) · 84,545 ratings'"""
    return f"{row['title']}{fmt_year(row['release_year'])} · {fmt_int(row['rating_count'])} ratings"


# ----------------------------------------------------------------- page furniture
def page_header(question, definition):
    """The question as worded in the brief, and how we defined it."""
    st.title(question)
    st.caption(definition)


def flash(message, kind="success"):
    """Show a message on the NEXT run (survives st.rerun)."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flash():
    for kind, message in st.session_state.pop("_flash", []):
        getattr(st, kind)(message)


def error_box(message, exc=None):
    """A friendly error for the user; the details go to the console log only."""
    if exc is not None:
        log.error("%s: %r", message, exc)
    st.error(message)


def metric_row(items):
    """items: list of (label, value) or (label, value, help)."""
    for col, item in zip(st.columns(len(items)), items):
        label, value, *help_ = item
        col.metric(label, value, help=help_[0] if help_ else None, border=True)


def chart_with_table(fig, table, key, column_config=None):
    """The chart, then a "Show data table" toggle with the same rows."""
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=f"{key}_chart")
    if st.toggle("Show data table", key=f"{key}_table"):
        st.dataframe(table, hide_index=True, column_config=column_config)


# ----------------------------------------------------------------- movie picker
def _pick(select_key):
    st.session_state[MOVIE_KEY] = st.session_state[select_key]


def movie_picker(key):
    """Search box + result list. Returns the chosen movie_id (or None).

    The choice is kept in st.session_state["movie_id"], so it carries across
    the pages that use a movie. It changes only when the user picks a movie
    (on_change), so other widgets (e.g. a suggestion button) can set it too.
    """
    text = st.text_input("Search for a movie", key=f"{key}_query",
                         placeholder="Type at least 2 letters, e.g. the matrix")
    if len(text.strip()) >= 2:
        hits = data.search_movies(text)
        if hits.empty:
            st.caption(f"No movie title contains “{text.strip()}”.")
        else:
            options = hits["movie_id"].tolist()
            labels = {r.movie_id: movie_label(r._asdict()) for r in hits.itertuples()}
            current = st.session_state.get(MOVIE_KEY)
            select_key = f"{key}_select"
            st.selectbox(f"{len(options)} matching movies (most-rated first)", options,
                         index=options.index(current) if current in options else None,
                         format_func=labels.get, placeholder="Choose a movie",
                         key=select_key, on_change=_pick, args=(select_key,))
    return st.session_state.get(MOVIE_KEY)


def selected_movie(movie_id):
    """Summary row of the chosen movie (display title, year, count, average) or None."""
    df = data.movie_summary(movie_id)
    return None if df.empty else df.iloc[0]


def set_movie(movie_id):
    """Button callback: choose a movie programmatically."""
    st.session_state[MOVIE_KEY] = movie_id


# ----------------------------------------------------------------- rating a movie
def rating_control(user, movie_id, title, key):
    """'Rate this movie': select_slider 0.5..5.0 + Save.

    Writes through ratings.upsert_my_rating (movie_app_user, row-level security:
    only the logged-in user's own rating). On success: clear the shared cache,
    show the new average, rerun so every chart is recomputed.
    """
    current = queries.my_rating_for_movie(user["user_id"], movie_id)      # per-user: not cached
    st.caption(f"Your current rating: **{current:.1f}**" if current is not None
               else "You have not rated this movie yet.")
    with st.form(f"{key}_form", border=False):
        value = st.select_slider("Your rating (stars)", options=RATING_STEPS,
                                 value=current if current is not None else 3.0,
                                 format_func=lambda v: f"{v:.1f}", key=f"{key}_value")
        saved = st.form_submit_button("Save rating", type="primary")
    if not saved:
        return
    try:
        upsert_my_rating(user["user_id"], movie_id, value)
    except ValueError as exc:                       # invalid value (also checked by the DB)
        error_box(str(exc))
        return
    except psycopg.errors.InsufficientPrivilege as exc:
        error_box("You can only change your own ratings.", exc)
        return
    data.clear()                                    # movie_stats changed: drop stale results
    summary = queries.movie_summary(movie_id).iloc[0]                   # fresh, not cached
    flash(f"Saved {value:.1f} stars for {title}. New average: {summary['avg_rating']:.3f} "
          f"from {fmt_int(summary['rating_count'])} ratings.")
    st.rerun()
