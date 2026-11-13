"""Write path for ratings: the only data a normal user may change."""
from decimal import Decimal, InvalidOperation

from db import user_conn

VALID_RATINGS = [Decimal(n) / 2 for n in range(1, 11)]     # 0.5, 1.0, ..., 5.0


def validate_rating(rating):
    """Return the rating as a Decimal, or raise ValueError.
    The database CHECK constraint enforces the same rule; this gives a clear
    message before the query is sent."""
    try:
        value = Decimal(str(rating))
    except InvalidOperation:
        raise ValueError(f"rating must be a number, got {rating!r}") from None
    if value not in VALID_RATINGS:
        raise ValueError(f"rating must be 0.5 to 5.0 in half steps, got {rating}")
    return value


def upsert_my_rating(user_id, movie_id, rating, commit=True):
    """Add or change the logged-in user's rating of one movie.

    Runs as movie_app_user with app.current_user_id = user_id, so row-level
    security rejects any attempt to write another user's rating. rated_at is
    left to its UTC default. The movie_stats trigger updates the aggregates.
    Returns (user_id, movie_id, rating, rated_at).
    """
    value = validate_rating(rating)
    with user_conn(user_id, commit=commit) as conn:
        return conn.execute("""
            INSERT INTO ratings (user_id, movie_id, rating)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, movie_id) DO UPDATE
               SET rating = EXCLUDED.rating, rated_at = EXCLUDED.rated_at
            RETURNING user_id, movie_id, rating, rated_at""",
            (user_id, movie_id, value)).fetchone()
