#!/usr/bin/env python3
"""
hw_collector.py — Hardware telemetry collector for Mac Mini Agent Server
ADR-034 | Phase 1.5 deliverable

Runs under the dev account as a LaunchDaemon.
Polls powermetrics every 60 seconds (configurable via POLL_INTERVAL_SEC).
Writes one row per sample to the hardware_metrics PostgreSQL table.
Requires a single sudoers entry to run powermetrics without a password prompt:
  dev ALL=(root) NOPASSWD: /usr/bin/powermetrics

Dependencies: psycopg2-binary (pip install psycopg2-binary --break-system-packages)
"""

import json
import os
import subprocess
import time
import logging
import signal
import sys
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

# ── Configuration ──────────────────────────────────────────────────────────────
POLL_INTERVAL_SEC = 60          # seconds between samples
POWERMETRICS_SAMPLE_MS = 5000   # powermetrics averaging window in ms
DB_DSN = os.environ.get(
    "HW_COLLECTOR_DSN",
    "host=localhost dbname=agentdb user=dev password=CHANGE_ME"
)
LOG_LEVEL = os.environ.get("HW_COLLECTOR_LOG_LEVEL", "INFO")

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [hw_collector] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Graceful shutdown ──────────────────────────────────────────────────────────
_running = True

def _handle_signal(signum, frame):
    global _running
    log.info("Signal %s received — shutting down gracefully", signum)
    _running = False

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ── powermetrics invocation ────────────────────────────────────────────────────
def collect_powermetrics(sample_ms: int = POWERMETRICS_SAMPLE_MS) -> dict:
    """
    Run powermetrics once, return parsed JSON.
    Requires sudo NOPASSWD entry for /usr/bin/powermetrics.
    Samplers: cpu_power, gpu_power, thermal, ane_power, smc, memory_stats.
    """
    cmd = [
        "sudo", "/usr/bin/powermetrics",
        "--samplers", "cpu_power,gpu_power,thermal,ane_power,smc,memory_stats",
        "--sample-count", "1",
        "--sample-rate", str(sample_ms),
        "--format", "json",
        "--hide-cpu-duty-cycle",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=sample_ms / 1000 + 15
        )
        if result.returncode != 0:
            log.error("powermetrics error: %s", result.stderr[:500])
            return {}
        # powermetrics may emit multiple JSON objects separated by newlines.
        # Take the last complete JSON object.
        raw = result.stdout.strip()
        # Find the last '{' that starts a top-level object
        last_brace = raw.rfind('\n{')
        if last_brace != -1:
            raw = raw[last_brace:].strip()
        return json.loads(raw)
    except subprocess.TimeoutExpired:
        log.error("powermetrics timed out after %ss", sample_ms / 1000 + 15)
        return {}
    except json.JSONDecodeError as e:
        log.error("JSON parse error from powermetrics: %s", e)
        return {}
    except Exception as e:
        log.error("Unexpected error running powermetrics: %s", e)
        return {}


# ── Data extraction helpers ────────────────────────────────────────────────────
def _safe(d: dict, *keys, default=None):
    """Safe nested dict access."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


def extract_metrics(pm: dict) -> dict:
    """
    Pull the fields we care about from the powermetrics JSON blob.
    Returns a flat dict matching the hardware_metrics table columns.
    All values are floats or None — the DB schema uses NUMERIC(10,3) NULLABLE.
    """
    if not pm:
        return {}

    # ── CPU ───────────────────────────────────────────────────────────────────
    cpu = _safe(pm, "processor", default={})
    clusters = _safe(cpu, "clusters", default=[])

    p_core_active = None
    e_core_active = None
    for cluster in clusters:
        name = (cluster.get("name") or "").upper()
        active = cluster.get("active_ratio")      # 0.0–1.0
        if active is None:
            active = cluster.get("cpu_active_ratio")
        if active is not None:
            active_pct = round(active * 100, 2)
            if "E" in name:
                e_core_active = active_pct
            else:
                p_core_active = active_pct

    cpu_power_mw   = _safe(cpu, "package_mW")
    cpu_freq_mhz   = _safe(cpu, "freq_hz")
    if cpu_freq_mhz:
        cpu_freq_mhz = round(cpu_freq_mhz / 1_000_000, 1)

    # ── GPU ───────────────────────────────────────────────────────────────────
    gpu = _safe(pm, "gpu", default={})
    gpu_active_pct = None
    raw_gpu = gpu.get("active_ratio") or gpu.get("gpu_active_ratio")
    if raw_gpu is not None:
        gpu_active_pct = round(raw_gpu * 100, 2)
    gpu_power_mw  = gpu.get("mW") or gpu.get("package_mW")
    gpu_freq_mhz  = gpu.get("freq_hz")
    if gpu_freq_mhz:
        gpu_freq_mhz = round(gpu_freq_mhz / 1_000_000, 1)

    # ── ANE (Neural Engine) ───────────────────────────────────────────────────
    ane_power_mw = _safe(pm, "ane", "mW") or _safe(pm, "ane_power", "mW")

    # ── Thermals ──────────────────────────────────────────────────────────────
    thermal = _safe(pm, "thermal", default={})
    # Thermal pressure: 0=nominal, 1=moderate, 2=heavy, 3=trapping, 4=sleeping
    thermal_pressure = thermal.get("thermal_pressure_level")

    # SMC sensors — Apple Silicon sensor keys vary by SoC generation
    # These keys work on M1 Max; may need adjustment for M2/M3/M4
    smc = _safe(pm, "smc", default={})
    cpu_temp_c = None
    gpu_temp_c = None
    fan_rpm    = None
    system_power_mw = None

    for sensor in smc.get("sensors", []):
        key  = sensor.get("key", "")
        val  = sensor.get("value")
        unit = sensor.get("unit", "")
        if val is None:
            continue
        # CPU die temperature — Tp09 is CPU package on M1 Max
        if key in ("Tp09", "Tp0P", "TC0F", "TC0E"):
            cpu_temp_c = round(float(val), 1)
        # GPU temperature — Tg05 on M1 Max
        if key in ("Tg05", "Tg0D", "TG0P"):
            gpu_temp_c = round(float(val), 1)
        # Fan speed — F0Ac on M1 Max (single fan)
        if key in ("F0Ac", "F0Tg", "FS! "):
            fan_rpm = round(float(val))
        # System total power
        if key in ("PSTR", "PDTR"):
            system_power_mw = round(float(val) * 1000)  # usually in W

    # Fallback: powermetrics sometimes surfaces temps directly
    if cpu_temp_c is None:
        cpu_temp_c = _safe(pm, "processor", "die_temperature_C")
        if cpu_temp_c:
            cpu_temp_c = round(float(cpu_temp_c), 1)

    # ── Memory ────────────────────────────────────────────────────────────────
    mem = _safe(pm, "memory", default={})
    mem_used_bytes    = mem.get("total_used")
    mem_free_bytes    = mem.get("free")
    mem_swap_bytes    = mem.get("swap_used") or mem.get("swapUsed")
    mem_pressure_str  = mem.get("pressure_level") or mem.get("compressionRatio")
    # Normalise pressure to integer: 0=nominal, 1=warn, 2=critical
    pressure_map = {"nominal": 0, "warn": 1, "warning": 1, "critical": 2}
    mem_pressure = None
    if isinstance(mem_pressure_str, str):
        mem_pressure = pressure_map.get(mem_pressure_str.lower())

    # Convert bytes to GB for storage
    def b_to_gb(b):
        if b is None:
            return None
        return round(b / (1024 ** 3), 3)

    # ── Total package power (CPU + GPU + ANE) ─────────────────────────────────
    total_power_mw = None
    parts = [cpu_power_mw, gpu_power_mw, ane_power_mw]
    if any(p is not None for p in parts):
        total_power_mw = sum(p for p in parts if p is not None)

    return {
        "sampled_at":        datetime.now(timezone.utc),
        # CPU
        "cpu_p_core_pct":    p_core_active,
        "cpu_e_core_pct":    e_core_active,
        "cpu_power_mw":      round(cpu_power_mw, 1) if cpu_power_mw else None,
        "cpu_freq_mhz":      cpu_freq_mhz,
        "cpu_temp_c":        cpu_temp_c,
        # GPU
        "gpu_active_pct":    gpu_active_pct,
        "gpu_power_mw":      round(gpu_power_mw, 1) if gpu_power_mw else None,
        "gpu_freq_mhz":      gpu_freq_mhz,
        "gpu_temp_c":        gpu_temp_c,
        # ANE
        "ane_power_mw":      round(ane_power_mw, 1) if ane_power_mw else None,
        # Thermals
        "thermal_pressure":  thermal_pressure,
        "fan_rpm":           fan_rpm,
        "system_power_mw":   system_power_mw or (round(total_power_mw, 1) if total_power_mw else None),
        # Memory
        "mem_used_gb":       b_to_gb(mem_used_bytes),
        "mem_free_gb":       b_to_gb(mem_free_bytes),
        "mem_swap_gb":       b_to_gb(mem_swap_bytes),
        "mem_pressure":      mem_pressure,
    }


# ── Database ───────────────────────────────────────────────────────────────────
INSERT_SQL = """
INSERT INTO hardware_metrics (
    sampled_at,
    cpu_p_core_pct, cpu_e_core_pct, cpu_power_mw, cpu_freq_mhz, cpu_temp_c,
    gpu_active_pct, gpu_power_mw, gpu_freq_mhz, gpu_temp_c,
    ane_power_mw,
    thermal_pressure, fan_rpm, system_power_mw,
    mem_used_gb, mem_free_gb, mem_swap_gb, mem_pressure
) VALUES %s
ON CONFLICT (sampled_at) DO NOTHING
"""

COLUMNS = [
    "sampled_at",
    "cpu_p_core_pct", "cpu_e_core_pct", "cpu_power_mw", "cpu_freq_mhz", "cpu_temp_c",
    "gpu_active_pct", "gpu_power_mw", "gpu_freq_mhz", "gpu_temp_c",
    "ane_power_mw",
    "thermal_pressure", "fan_rpm", "system_power_mw",
    "mem_used_gb", "mem_free_gb", "mem_swap_gb", "mem_pressure",
]


def write_row(conn, row: dict):
    if not row:
        return
    values = tuple(row.get(c) for c in COLUMNS)
    with conn.cursor() as cur:
        execute_values(cur, INSERT_SQL, [values])
    conn.commit()
    log.debug("Wrote sample: cpu_p=%.1f%% gpu=%.1f%% temp=%.1f°C fan=%s RPM mem_used=%.2fGB",
              row.get("cpu_p_core_pct") or 0,
              row.get("gpu_active_pct") or 0,
              row.get("cpu_temp_c") or 0,
              row.get("fan_rpm") or "n/a",
              row.get("mem_used_gb") or 0)


def connect_with_retry(dsn: str, retries: int = 10, delay: int = 6):
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(dsn)
            log.info("Database connected")
            return conn
        except psycopg2.OperationalError as e:
            log.warning("DB connect attempt %d/%d failed: %s", attempt, retries, e)
            if attempt < retries:
                time.sleep(delay)
    log.error("Could not connect to database after %d attempts — exiting", retries)
    sys.exit(1)


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    log.info("hw_collector starting — poll interval %ss", POLL_INTERVAL_SEC)
    conn = connect_with_retry(DB_DSN)

    while _running:
        loop_start = time.monotonic()
        try:
            pm = collect_powermetrics()
            row = extract_metrics(pm)
            if row:
                write_row(conn, row)
            else:
                log.warning("Empty sample — powermetrics returned no usable data")
        except psycopg2.InterfaceError:
            log.warning("DB connection lost — reconnecting")
            conn = connect_with_retry(DB_DSN)
        except Exception as e:
            log.error("Unhandled error in collection loop: %s", e, exc_info=True)

        elapsed = time.monotonic() - loop_start
        sleep_for = max(0, POLL_INTERVAL_SEC - elapsed)
        # Sleep in 1-second chunks so SIGTERM is caught promptly
        for _ in range(int(sleep_for)):
            if not _running:
                break
            time.sleep(1)

    log.info("hw_collector stopped")
    conn.close()


if __name__ == "__main__":
    main()
