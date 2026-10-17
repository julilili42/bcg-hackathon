CREATE TABLE IF NOT EXISTS pipes (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    aliases text[] NOT NULL DEFAULT '{}',
    village text NOT NULL,
    description text,
    latitude double precision CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision CHECK (longitude BETWEEN -180 AND 180),
    status text NOT NULL DEFAULT 'unknown' CHECK (status IN ('operational','broken','low_flow','under_repair','unsafe','unknown')),
    status_observed_at timestamptz,
    status_updated_at timestamptz NOT NULL DEFAULT now(),
    latest_report_id uuid,
    needs_verification boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS pipe_reports (
    id uuid PRIMARY KEY,
    pipe_id uuid REFERENCES pipes(id),
    user_id text NOT NULL,
    original_text text NOT NULL,
    statement text NOT NULL,
    reported_status text CHECK (reported_status IN ('operational','broken','low_flow','under_repair','unsafe','unknown')),
    observed_at timestamptz,
    reported_at timestamptz NOT NULL,
    applied_to_current_status boolean NOT NULL DEFAULT false,
    resolution_status text NOT NULL CHECK (resolution_status IN ('matched','ambiguous','unmatched')),
    qdrant_indexed boolean NOT NULL DEFAULT false,
    turn_id text NOT NULL,
    fact_index integer NOT NULL,
    asset_name text,
    village text,
    UNIQUE(turn_id,fact_index)
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pipes_latest_report_fk' AND conrelid='pipes'::regclass) THEN
        ALTER TABLE pipes ADD CONSTRAINT pipes_latest_report_fk FOREIGN KEY (latest_report_id) REFERENCES pipe_reports(id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS pipe_reports_history ON pipe_reports(pipe_id, observed_at DESC);
