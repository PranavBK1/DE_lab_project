-- =============================================================================
-- sql/extensions.sql : PostgreSQL extensions (run by etl/setup_security.py
-- before sql/roles.sql). Re-runnable.
-- =============================================================================

-- pgcrypto: crypt() + gen_salt('bf', 12) hash and verify passwords with bcrypt
-- INSIDE the database, so a password hash never leaves PostgreSQL
-- (see auth_login in sql/roles.sql).
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
