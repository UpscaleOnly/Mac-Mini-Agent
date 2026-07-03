# ══════════════════════════════════════════════════════════════════════════════
# ADR-034 — Hardware Telemetry Collector · Setup Files
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. sudoers entry ──────────────────────────────────────────────────────────
#
# Add via visudo ONLY. Never edit /etc/sudoers directly.
# Run as admin account:
#
#   sudo visudo -f /etc/sudoers.d/hw_collector
#
# Paste this single line:
#
#   dev ALL=(root) NOPASSWD: /usr/bin/powermetrics
#
# This grants the dev account the ability to run /usr/bin/powermetrics as root
# with no password prompt. No other commands are permitted by this entry.
# Every invocation is logged automatically to /var/log/sudo.log and the macOS
# unified log (log show --predicate 'process == "sudo"').
#
# NIST rationale: AC-6 least privilege — minimum elevation for specific function.
# Fully auditable via AU-12 (macOS unified log captures all sudo events).

# ── 2. Environment file ───────────────────────────────────────────────────────
# Create /etc/hw_collector.env (readable by dev account only, chmod 600):
#
#   HW_COLLECTOR_DSN=host=localhost dbname=agentdb user=dev password=YOUR_PW
#   HW_COLLECTOR_LOG_LEVEL=INFO
#   POLL_INTERVAL_SEC=60

# ── 3. LaunchDaemon plist ─────────────────────────────────────────────────────
# Path: /Library/LaunchDaemons/com.agentserver.hwcollector.plist
# Install as root, run as dev account.
# Load with: sudo launchctl load /Library/LaunchDaemons/com.agentserver.hwcollector.plist

LAUNCHDAEMON_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentserver.hwcollector</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/opt/agentserver/hw_collector.py</string>
    </array>

    <!-- Run as dev account, not root -->
    <key>UserName</key>
    <string>dev</string>

    <!-- Environment -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>HW_COLLECTOR_DSN</key>
        <string>host=localhost dbname=agentdb user=dev password=CHANGE_ME</string>
        <key>HW_COLLECTOR_LOG_LEVEL</key>
        <string>INFO</string>
    </dict>

    <!-- Keep alive — restart on crash -->
    <key>KeepAlive</key>
    <true/>

    <!-- Wait for network before starting -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Log stdout/stderr to files -->
    <key>StandardOutPath</key>
    <string>/var/log/hw_collector.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/hw_collector_error.log</string>

    <!-- Throttle restart on crash — 30 second minimum between restarts -->
    <key>ThrottleInterval</key>
    <integer>30</integer>
</dict>
</plist>"""

# ── 4. Setup day commands (run in order as admin account) ─────────────────────
SETUP_COMMANDS = """
# Step 1 — Copy collector to permanent location
sudo mkdir -p /opt/agentserver
sudo cp hw_collector.py /opt/agentserver/hw_collector.py
sudo chown dev:staff /opt/agentserver/hw_collector.py
sudo chmod 750 /opt/agentserver/hw_collector.py

# Step 2 — Install dependency (as dev account)
pip3 install psycopg2-binary --break-system-packages

# Step 3 — Create PostgreSQL table (as dev account)
psql agentdb < hardware_metrics.sql

# Step 4 — Add sudoers entry (as admin)
sudo visudo -f /etc/sudoers.d/hw_collector
# Paste: dev ALL=(root) NOPASSWD: /usr/bin/powermetrics
# Save and exit visudo

# Step 5 — Smoke test (as dev account — should return JSON, no password prompt)
sudo /usr/bin/powermetrics \
  --samplers cpu_power,gpu_power,thermal,ane_power,smc,memory_stats \
  --sample-count 1 --sample-rate 5000 --format json | head -20

# Step 6 — Run collector manually for 3 cycles to verify DB writes
python3 /opt/agentserver/hw_collector.py &
sleep 200
# Then check DB:
psql agentdb -c "SELECT sampled_at, cpu_p_core_pct, gpu_active_pct, cpu_temp_c, fan_rpm FROM hardware_metrics ORDER BY sampled_at DESC LIMIT 3;"
kill %1

# Step 7 — Install and load LaunchDaemon
sudo cp com.agentserver.hwcollector.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.agentserver.hwcollector.plist
sudo chmod 644 /Library/LaunchDaemons/com.agentserver.hwcollector.plist
sudo launchctl load /Library/LaunchDaemons/com.agentserver.hwcollector.plist

# Step 8 — Verify daemon is running
sudo launchctl list | grep hwcollector
tail -f /var/log/hw_collector.log
"""

# ── 5. Presentation SQL queries (pre-written, paste-ready) ───────────────────
DEMO_QUERIES = """
-- Query 1: Last 5 samples (live status)
SELECT
    sampled_at AT TIME ZONE 'America/New_York' AS local_time,
    cpu_p_core_pct   AS "P-cores %",
    cpu_e_core_pct   AS "E-cores %",
    gpu_active_pct   AS "GPU %",
    ane_power_mw     AS "ANE mW",
    cpu_temp_c       AS "CPU °C",
    fan_rpm          AS "Fan RPM",
    ROUND(system_power_mw/1000,1) AS "System W",
    mem_used_gb      AS "Mem used GB",
    mem_swap_gb      AS "Swap GB"
FROM hardware_metrics
ORDER BY sampled_at DESC LIMIT 5;

-- Query 2: 24-hour hourly averages (presentation arc)
SELECT
    date_trunc('hour', sampled_at AT TIME ZONE 'America/New_York') AS hour,
    ROUND(AVG(cpu_p_core_pct)::numeric, 1)        AS cpu_p_avg,
    ROUND(AVG(gpu_active_pct)::numeric, 1)         AS gpu_avg,
    ROUND(AVG(ane_power_mw)::numeric, 0)           AS ane_mw_avg,
    ROUND(AVG(cpu_temp_c)::numeric, 1)             AS temp_avg,
    ROUND(AVG(system_power_mw/1000)::numeric, 1)   AS power_w_avg,
    MAX(fan_rpm)                                   AS fan_peak,
    SUM(CASE WHEN mem_swap_gb > 0 THEN 1 ELSE 0 END) AS swap_events
FROM hardware_metrics
WHERE sampled_at > NOW() - INTERVAL '24 hours'
GROUP BY 1 ORDER BY 1;

-- Query 3: Alert summary (zero should be your baseline)
SELECT COUNT(*) AS alert_samples,
       MAX(cpu_temp_c)     AS peak_cpu_temp,
       MAX(gpu_temp_c)     AS peak_gpu_temp,
       MAX(fan_rpm)        AS peak_fan_rpm,
       SUM(CASE WHEN mem_swap_gb > 0 THEN 1 ELSE 0 END) AS swap_events
FROM hardware_metrics
WHERE sampled_at > NOW() - INTERVAL '24 hours'
  AND (cpu_temp_c > 85 OR gpu_temp_c > 80 OR fan_rpm > 3000
       OR mem_swap_gb > 0 OR thermal_pressure >= 2);
"""
