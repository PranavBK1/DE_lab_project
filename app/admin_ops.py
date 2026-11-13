"""Admin operations: every write runs through admin_conn (role movie_admin).

All SQL is parameterised. Inputs are validated here, so the Admin page and
the tests share the same rules. Each function is one transaction. Problems
the user can fix raise AdminError with a message to show.
"""
from psycopg import errors

from db import admin_conn
from ratings import validate_rating

MIN_YEAR, MAX_YEAR = 1870, 2030
MIN_PASSWORD = 8
ROLES = ("user", "admin")
APP_USER_ID_START = 200000      # ids below this are MovieLens users


class AdminError(ValueError):
    """A problem the admin can fix (shown as st.error)."""


class HasActivity(AdminError):
    """The account still has ratings and/or tags (foreign keys refuse the delete)."""

    def __init__(self, ratings, tags):
        self.ratings, self.tags = ratings, tags
        super().__init__(f"This user has {ratings:,} ratings and {tags:,} tags. Delete them first?")


# ----------------------------------------------------------------- validation
def clean_title(title):
    title = (title or "").strip()
    if not title:
        raise AdminError("The title must not be empty.")
    if len(title) > 300:
        raise AdminError("The title is too long (300 characters at most).")
    return title


def clean_year(year):
    if year in (None, ""):
        return None
    try:
        year = int(year)
    except (TypeError, ValueError):
        raise AdminError("The release year must be a whole number.") from None
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise AdminError(f"The release year must be between {MIN_YEAR} and {MAX_YEAR}.")
    return year


def clean_username(username):
    username = (username or "").strip()
    if len(username) < 3:
        raise AdminError("The username must have at least 3 characters.")
    if username.isdigit():
        raise AdminError("The username cannot be only digits.")
    return username


def check_password(password):
    if len(password or "") < MIN_PASSWORD:
        raise AdminError(f"The password must have at least {MIN_PASSWORD} characters.")
    return password


def check_role(role):
    if role not in ROLES:
        raise AdminError(f"The role must be one of {', '.join(ROLES)}.")
    return role


# ----------------------------------------------------------------- movies
def movie_detail(movie_id):
    """Movie fields, its genre ids, and how many rows depend on it.
    None if the movie does not exist."""
    with admin_conn() as conn:
        row = conn.execute("SELECT movie_id, title, release_year FROM movies WHERE movie_id = %s",
                           (movie_id,)).fetchone()
        if row is None:
            return None
        counts = conn.execute("""
            SELECT (SELECT count(*) FROM ratings       WHERE movie_id = %(m)s),
                   (SELECT count(*) FROM tags          WHERE movie_id = %(m)s),
                   (SELECT count(*) FROM movie_genres  WHERE movie_id = %(m)s),
                   (SELECT count(*) FROM links         WHERE movie_id = %(m)s),
                   (SELECT count(*) FROM genome_scores WHERE movie_id = %(m)s),
                   (SELECT count(*) FROM movie_stats   WHERE movie_id = %(m)s)""", {"m": movie_id}).fetchone()
        genre_ids = [r[0] for r in conn.execute(
            "SELECT genre_id FROM movie_genres WHERE movie_id = %s ORDER BY genre_id", (movie_id,))]
    keys = ["ratings", "tags", "movie_genres", "links", "genome_scores", "movie_stats"]
    return {"movie_id": row[0], "title": row[1], "release_year": row[2],
            "genre_ids": genre_ids, "counts": dict(zip(keys, counts))}


def _set_genres(conn, movie_id, genre_ids):
    conn.execute("DELETE FROM movie_genres WHERE movie_id = %s", (movie_id,))
    for genre_id in sorted(set(genre_ids)):
        conn.execute("INSERT INTO movie_genres (movie_id, genre_id) VALUES (%s, %s)", (movie_id, genre_id))


def update_movie(movie_id, title, release_year, genre_ids):
    title, release_year = clean_title(title), clean_year(release_year)
    with admin_conn() as conn:
        cur = conn.execute("UPDATE movies SET title = %s, release_year = %s WHERE movie_id = %s",
                           (title, release_year, movie_id))
        if cur.rowcount == 0:
            raise AdminError("This movie no longer exists.")
        _set_genres(conn, movie_id, genre_ids)


def add_movie(title, release_year, genre_ids):
    """Insert a movie; its id comes from the identity column. Returns the new id."""
    title, release_year = clean_title(title), clean_year(release_year)
    with admin_conn() as conn:
        movie_id = conn.execute("INSERT INTO movies (title, release_year) VALUES (%s, %s) RETURNING movie_id",
                                (title, release_year)).fetchone()[0]
        _set_genres(conn, movie_id, genre_ids)
    return movie_id


def delete_movie(movie_id):
    """Delete a movie. Its genres, links, genome scores and stats cascade.
    Refused (by the foreign keys) if it has ratings or tags."""
    try:
        with admin_conn() as conn:
            cur = conn.execute("DELETE FROM movies WHERE movie_id = %s", (movie_id,))
            if cur.rowcount == 0:
                raise AdminError("This movie no longer exists.")
    except errors.ForeignKeyViolation:
        raise AdminError("This movie has ratings or tags, so it cannot be deleted. "
                         "User data is never deleted along with a movie.") from None


# ----------------------------------------------------------------- users
def list_accounts():
    """App accounts (username set), with their number of ratings and tags."""
    with admin_conn() as conn:
        cur = conn.execute("""
            SELECT u.user_id, u.username, u.role, u.created_at,
                   (SELECT count(*) FROM ratings r WHERE r.user_id = u.user_id) AS ratings,
                   (SELECT count(*) FROM tags t    WHERE t.user_id = u.user_id) AS tags
              FROM users u
             WHERE u.username IS NOT NULL
             ORDER BY u.role, u.username""")
        columns = [c.name for c in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def create_account(username, password, role):
    """New app account. The bcrypt hash is made INSIDE PostgreSQL, the same
    scheme as etl/setup_security.py and auth_login. Returns the new user_id."""
    username, role = clean_username(username), check_role(role)
    check_password(password)
    try:
        with admin_conn() as conn:
            return conn.execute("""
                INSERT INTO users (username, password_hash, role)
                VALUES (%s, crypt(%s, gen_salt('bf', 12)), %s)
                RETURNING user_id""", (username, password, role)).fetchone()[0]
    except errors.UniqueViolation:
        raise AdminError(f"The username “{username}” is already taken.") from None


def set_role(user_id, role, acting_user_id):
    role = check_role(role)
    if user_id == acting_user_id and role != "admin":
        raise AdminError("You cannot remove the admin role from your own account.")
    with admin_conn() as conn:
        conn.execute("UPDATE users SET role = %s WHERE user_id = %s AND username IS NOT NULL", (role, user_id))


def reset_password(user_id, password):
    check_password(password)
    with admin_conn() as conn:
        conn.execute("UPDATE users SET password_hash = crypt(%s, gen_salt('bf', 12)) "
                     "WHERE user_id = %s AND username IS NOT NULL", (password, user_id))


def delete_account(user_id, acting_user_id, delete_activity=False):
    """Delete an app account.

    Without delete_activity, the foreign keys refuse it while the user has
    ratings or tags: HasActivity tells how many. With delete_activity=True
    (after the admin confirmed), the ratings, tags and the user are deleted in
    ONE transaction; the ratings trigger keeps movie_stats correct.
    """
    if user_id == acting_user_id:
        raise AdminError("You cannot delete your own account.")
    try:
        with admin_conn() as conn:
            if delete_activity:
                conn.execute("DELETE FROM ratings WHERE user_id = %s", (user_id,))
                conn.execute("DELETE FROM tags WHERE user_id = %s", (user_id,))
            cur = conn.execute("DELETE FROM users WHERE user_id = %s AND username IS NOT NULL", (user_id,))
            if cur.rowcount == 0:
                raise AdminError("This account no longer exists.")
    except errors.ForeignKeyViolation:
        with admin_conn() as conn:
            ratings, tags = conn.execute(
                "SELECT (SELECT count(*) FROM ratings WHERE user_id = %(u)s), "
                "       (SELECT count(*) FROM tags WHERE user_id = %(u)s)", {"u": user_id}).fetchone()
        raise HasActivity(ratings, tags) from None


# ----------------------------------------------------------------- ratings
def user_ratings(user_id, limit=200):
    """Any user's ratings (newest first), for the Ratings tab."""
    with admin_conn() as conn:
        cur = conn.execute("""
            SELECT r.movie_id, m.title, m.release_year, r.rating, r.rated_at
              FROM ratings r JOIN movies m ON m.movie_id = r.movie_id
             WHERE r.user_id = %s
             ORDER BY r.rated_at DESC, r.movie_id
             LIMIT %s""", (user_id, limit))
        columns = [c.name for c in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def update_rating(user_id, movie_id, rating):
    value = validate_rating(rating)
    with admin_conn() as conn:
        cur = conn.execute("UPDATE ratings SET rating = %s, rated_at = now() AT TIME ZONE 'UTC' "
                           "WHERE user_id = %s AND movie_id = %s", (value, user_id, movie_id))
        if cur.rowcount == 0:
            raise AdminError("This rating no longer exists.")


def delete_rating(user_id, movie_id):
    with admin_conn() as conn:
        cur = conn.execute("DELETE FROM ratings WHERE user_id = %s AND movie_id = %s", (user_id, movie_id))
        if cur.rowcount == 0:
            raise AdminError("This rating no longer exists.")

