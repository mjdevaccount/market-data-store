-- Seed data for market-data-store control-plane
-- This file contains default configuration and initial data

-- Insert default tenant
INSERT INTO tenants (tenant_id, name) VALUES ('default', 'Default Tenant')
ON CONFLICT (tenant_id) DO NOTHING;

-- Insert API configuration guardrails
INSERT INTO api_config (key, value, description) VALUES 
('rate_limits', '{"requests_per_minute": 1000, "burst_limit": 100}', 'API rate limiting configuration'),
('cache_settings', '{"ttl_seconds": 300, "max_size_mb": 1024}', 'Cache configuration for API responses'),
('data_freshness', '{"max_age_hours": 24, "alert_threshold_hours": 6}', 'Data freshness monitoring settings')
ON CONFLICT (key) DO UPDATE SET 
    value = EXCLUDED.value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- Insert forex session configuration (optional)
INSERT INTO api_config (key, value, description) VALUES 
('forex_sessions', '{
    "tokyo": {"open": "00:00", "close": "09:00", "timezone": "Asia/Tokyo"},
    "london": {"open": "08:00", "close": "17:00", "timezone": "Europe/London"},
    "new_york": {"open": "13:00", "close": "22:00", "timezone": "America/New_York"}
}', 'Forex trading session hours configuration')
ON CONFLICT (key) DO UPDATE SET 
    value = EXCLUDED.value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- Insert system configuration
INSERT INTO api_config (key, value, description) VALUES 
('system_config', '{
    "max_retries": 3,
    "job_timeout_seconds": 300,
    "cleanup_retention_days": 30
}', 'System-wide configuration settings')
ON CONFLICT (key) DO UPDATE SET 
    value = EXCLUDED.value,
    description = EXCLUDED.description,
    updated_at = NOW();
