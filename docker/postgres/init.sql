-- ============================================================
-- ITBIS — PostgreSQL Initialization Script
-- ============================================================
-- Runs once when the container is first created.
-- ============================================================

-- Create the main application database if it doesn't already exist
-- (POSTGRES_DB env var creates it; this adds extensions & config)

-- Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create audit schema for audit log tables
CREATE SCHEMA IF NOT EXISTS audit;

-- Create application schema
CREATE SCHEMA IF NOT EXISTS app;

-- Set default search path
ALTER DATABASE itbis_db SET search_path TO app, public;

\echo 'ITBIS PostgreSQL initialization complete.'
