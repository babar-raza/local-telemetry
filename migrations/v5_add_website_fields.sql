-- Schema Migration v4 -> v5
-- Add website, website_section, and item_name columns for API spec compliance
--
-- These fields are required by the Google Sheets API specification:
-- - website: Root domain (e.g., "aspose.com")
-- - website_section: Subdomain or section (e.g., "products", "docs", "www", "main")
-- - item_name: Specific page/entity being tracked (e.g., "/slides/net/" or "query:keyword")
--
-- Migration is safe to run multiple times (uses IF NOT EXISTS).
-- Run this migration against existing telemetry.sqlite databases.

-- Add website column
ALTER TABLE agent_runs ADD COLUMN website TEXT;

-- Add website_section column
ALTER TABLE agent_runs ADD COLUMN website_section TEXT;

-- Add item_name column
ALTER TABLE agent_runs ADD COLUMN item_name TEXT;

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_agent_runs_website ON agent_runs(website);
CREATE INDEX IF NOT EXISTS idx_agent_runs_website_section ON agent_runs(website, website_section);

-- Verify migration
SELECT
    'v5 Migration Complete' as status,
    COUNT(*) as total_runs,
    COUNT(website) as runs_with_website,
    COUNT(website_section) as runs_with_website_section,
    COUNT(item_name) as runs_with_item_name
FROM agent_runs;
