-- hardware_metrics.sql
-- ADR-034 · Hardware Telemetry Collector
-- Run as: dev account · psql agentdb < hardware_metrics.sql
--
-- Retention policy (matches ADR-029 pattern):
--   Full 1-minute resolution: 90 days
--   After 90 days: summarised to hourly in hardware_metrics_hourly (Phase 2)
--   Managed by compliance_monitor cron or manual pg_cron job

CREATE TABLE IF NOT EXISTS hardware_metrics (
    id              BIGSERIAL PRIMARY KEY,
    sampled_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- CPU · Apple Silicon M1 Max · 8 P-cores + 2 E-cores
    cpu_p_core_pct  NUMERIC(6,2),   -- Performance core utilization 0–100%
    cpu_e_core_pct  NUMERIC(6,2),   -- Efficiency core utilization 0–100%
    cpu_power_mw    NUMERIC(10,1),  -- CPU package power in milliwatts
    cpu_freq_mhz    NUMERIC(8,1),   -- CPU frequency in MHz
    cpu_temp_c      NUMERIC(6,1),   -- CPU die temperature °C · alert >85

    -- GPU · Integrated M1 Max 24-core
    gpu_active_pct  NUMERIC(6,2),   -- GPU utilization 0–100%
    gpu_power_mw    NUMERIC(10,1),  -- GPU power in milliwatts
    gpu_freq_mhz    NUMERIC(8,1),   -- GPU frequency in MHz
    gpu_temp_c      NUMERIC(6,1),   -- GPU die temperature °C · alert >80

    -- ANE · Apple Neural Engine (16-core on M1 Max)
    ane_power_mw    NUMERIC(10,1),  -- ANE power draw in milliwatts

    -- Thermals
    thermal_pressure SMALLINT,      -- 0=nominal 1=moderate 2=heavy 3=trapping 4=sleeping
    fan_rpm          INTEGER,        -- Single fan RPM on Mac Studio M1 Max · alert >3000
    system_power_mw  NUMERIC(10,1), -- Total system power draw in milliwatts · alert >80000

    -- Unified Memory (32GB total on M1 Max)
    mem_used_gb     NUMERIC(6,3),   -- Used memory in GB · alert >28
    mem_free_gb     NUMERIC(6,3),   -- Free memory in GB
    mem_swap_gb     NUMERIC(6,3),   -- Swap in GB · any > 0 = alert (SI-4(5))
    mem_pressure    SMALLINT,       -- 0=nominal 1=warn 2=critical (macOS memory pressure)

    -- Uniqueness: one sample per timestamp (ON CONFLICT DO NOTHING in collector)
    CONSTRAINT hardware_metrics_sampled_at_unique UNIQUE (sampled_at)
);

-- Indexes optimised for the dashboard query patterns
CREATE INDEX IF NOT EXISTS idx_hw_sampled_at
    ON hardware_metrics (sampled_at DESC);

CREATE INDEX IF NOT EXISTS idx_hw_alerts
    ON hardware_metrics (sampled_at DESC)
    WHERE cpu_temp_c > 85
       OR gpu_temp_c > 80
       OR fan_rpm > 3000
       OR mem_swap_gb > 0
       OR thermal_pressure >= 2
       OR system_power_mw > 80000;

-- ── Alert threshold view ───────────────────────────────────────────────────────
-- Used by compliance_monitor queries and Telegram natural-language reports.
CREATE OR REPLACE VIEW hardware_alerts AS
SELECT
    sampled_at,
    CASE WHEN cpu_temp_c > 85         THEN true ELSE false END AS cpu_temp_alert,
    CASE WHEN gpu_temp_c > 80         THEN true ELSE false END AS gpu_temp_alert,
    CASE WHEN fan_rpm > 3000          THEN true ELSE false END AS fan_alert,
    CASE WHEN mem_swap_gb > 0         THEN true ELSE false END AS swap_alert,
    CASE WHEN thermal_pressure >= 2   THEN true ELSE false END AS thermal_alert,
    CASE WHEN system_power_mw > 80000 THEN true ELSE false END AS power_alert,
    cpu_temp_c, gpu_temp_c, fan_rpm, mem_swap_gb, thermal_pressure, system_power_mw
FROM hardware_metrics
WHERE cpu_temp_c > 85
   OR gpu_temp_c > 80
   OR fan_rpm > 3000
   OR mem_swap_gb > 0
   OR thermal_pressure >= 2
   OR system_power_mw > 80000
ORDER BY sampled_at DESC;

-- ── Retention policy function ──────────────────────────────────────────────────
-- Call manually or via pg_cron weekly (Phase 2).
-- Deletes rows older than 90 days.
CREATE OR REPLACE FUNCTION purge_hardware_metrics_90d()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM hardware_metrics
    WHERE sampled_at < NOW() - INTERVAL '90 days';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- ── Quick verification query ───────────────────────────────────────────────────
-- Run after first few collection cycles to confirm data is flowing:
--   SELECT sampled_at, cpu_p_core_pct, gpu_active_pct, cpu_temp_c,
--          fan_rpm, mem_used_gb, mem_swap_gb, thermal_pressure
--   FROM hardware_metrics
--   ORDER BY sampled_at DESC LIMIT 5;

-- ── Presentation query — 24h sparkline ────────────────────────────────────────
-- Used in live demo SQL pull:
--   SELECT date_trunc('hour', sampled_at) AS hour,
--          ROUND(AVG(cpu_p_core_pct)::numeric, 1)  AS cpu_p_avg,
--          ROUND(AVG(gpu_active_pct)::numeric, 1)   AS gpu_avg,
--          ROUND(AVG(cpu_temp_c)::numeric, 1)       AS temp_avg,
--          ROUND(AVG(system_power_mw)/1000, 1)      AS power_w_avg,
--          MAX(fan_rpm)                              AS fan_peak,
--          SUM(CASE WHEN mem_swap_gb > 0 THEN 1 ELSE 0 END) AS swap_events
--   FROM hardware_metrics
--   WHERE sampled_at > NOW() - INTERVAL '24 hours'
--   GROUP BY 1
--   ORDER BY 1 DESC;
