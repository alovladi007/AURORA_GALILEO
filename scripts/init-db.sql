-- GALILEO V2.0 Database Initialization Script
-- Runs automatically on first PostgreSQL container start.
--
-- The database and user are created by the container entrypoint from
-- POSTGRES_USER / POSTGRES_DB env vars (default: galileo / galileo),
-- and this script executes connected to POSTGRES_DB as POSTGRES_USER.
-- CREATE DATABASE is not allowed inside DO blocks, and the entrypoint
-- runs with ON_ERROR_STOP=1, so keep this script to extensions and
-- defaults only. (Tables are managed by Alembic migrations.)

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Default privileges for objects created later in public schema
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO CURRENT_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO CURRENT_USER;
