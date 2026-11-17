"""Choose the passwords of the four dashboard logins yourself.

Usage:  python etl/set_passwords.py      (or double-click set_passwords.bat)

Asks for a password for admin, demo_user1, demo_user2 and demo_user3. What you
type is hidden, and each one is asked twice to catch typos. Then it:
  1. writes them to .env as DEMO_ADMIN_PASSWORD, DEMO_USER1_PASSWORD,
     DEMO_USER2_PASSWORD, DEMO_USER3_PASSWORD (.env is git-ignored);
  2. runs setup_security, which stores only bcrypt hashes in PostgreSQL.
Short, easy passwords are allowed here. Nothing is printed back to the screen.
"""
import getpass
import os
import re

from db import ROOT
from setup_security import DEMO_USERS, main as apply_security, password_key

ENV = ROOT / ".env"
OBSOLETE = {"DEMO_USER_PASSWORD", "SHOW_DEMO_LOGINS"}   # the old shared password / login-page box


def ask(username):
    while True:
        first = getpass.getpass(f"  Password for {username:<11}: ")
        problem = check(first)
        if problem:
            print(f"    {problem} Try again.")
            continue
        if getpass.getpass(f"  Type it again          : ") != first:
            print("    The two entries do not match. Try again.")
            continue
        return first


def check(password):
    if not password:
        return "The password cannot be empty."
    if password != password.strip():
        return "The password cannot start or end with a space."
    if "'" in password or "\n" in password:
        return "The password cannot contain ' (a single quote)."
    if password == "change-me":
        return "Choose something other than change-me."
    return None


def write_env(values):
    """Replace (or add) the given keys in .env, keep every other line as it is."""
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    out, done = [], set()
    for line in lines:
        m = re.match(r"\s*([A-Z0-9_]+)\s*=", line)
        key = m.group(1) if m else None
        if key in OBSOLETE:
            continue
        if key in values:
            out.append(f"{key}='{values[key]}'")
            done.add(key)
        else:
            out.append(line)
    out += [f"{k}='{v}'" for k, v in values.items() if k not in done]
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def main():
    if not ENV.exists():
        raise SystemExit(".env not found: copy .env.example to .env and fill in the PostgreSQL settings first.")
    admin = os.environ.get("DEMO_ADMIN_USERNAME") or "admin"
    print("Choose the dashboard passwords (what you type is not shown).\n")
    values = {password_key(name): ask(name) for name in [admin, *DEMO_USERS]}
    write_env(values)
    os.environ.update(values)
    for key in OBSOLETE:
        os.environ.pop(key, None)
    print("\nSaved in .env. Updating the database...")
    apply_security()
    print("\nDone. Log in at http://localhost:8501 with your new passwords "
          "(restart run_app.bat if it is already running).")


if __name__ == "__main__":
    main()
