-- Default tenant
INSERT INTO tenants (tenant_id, name)
VALUES ('default', 'Default Tenant')
ON CONFLICT (tenant_id) DO NOTHING;

-- Guardrails & runtime settings
INSERT INTO api_config (key, value, description) VALUES
('rate_limits', '{
  "requests_per_minute": 600,
  "burst_limit": 120,
  "job_enqueue_per_minute": 120
}', 'API rate limiting configuration'),
('cache_settings', '{
  "l1_ttl_seconds": 120,
  "l2_ttl_seconds": 3600,
  "single_flight_timeout": 60
}', 'Caching configuration'),
('data_freshness', '{
  "price_ttl": 300,
  "fundamental_ttl": 3600,
  "news_ttl": 900,
  "options_ttl": 600
}', 'Data freshness TTL settings')
ON CONFLICT (key) DO NOTHING;

-- Optional: forex sessions (safe idempotent inserts)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'weekday_enum') THEN
        CREATE TYPE weekday_enum AS ENUM ('sun','mon','tue','wed','thu','fri','sat');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS forex_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_name TEXT NOT NULL,             -- tokyo, london, new_york
    day_of_week weekday_enum NOT NULL,      -- sun..sat
    open_time TIME NOT NULL,
    close_time TIME NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO forex_sessions (session_name, day_of_week, open_time, close_time, timezone, is_active)
VALUES
  ('tokyo','sun','17:00','24:00','Asia/Tokyo',true),
  ('tokyo','mon','00:00','24:00','Asia/Tokyo',true),
  ('tokyo','tue','00:00','24:00','Asia/Tokyo',true),
  ('tokyo','wed','00:00','24:00','Asia/Tokyo',true),
  ('tokyo','thu','00:00','15:00','Asia/Tokyo',true),
  ('london','sun','17:00','24:00','Europe/London',true),
  ('london','mon','00:00','24:00','Europe/London',true),
  ('london','tue','00:00','24:00','Europe/London',true),
  ('london','wed','00:00','24:00','Europe/London',true),
  ('london','thu','00:00','21:00','Europe/London',true),
  ('new_york','sun','22:00','24:00','America/New_York',true),
  ('new_york','mon','00:00','24:00','America/New_York',true),
  ('new_york','tue','00:00','24:00','America/New_York',true),
  ('new_york','wed','00:00','24:00','America/New_York',true),
  ('new_york','thu','00:00','22:00','America/New_York',true)
ON CONFLICT DO NOTHING;
