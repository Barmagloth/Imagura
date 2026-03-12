"""CPU performance benchmarks for Imagura.

Covers: priority queue throughput, user_config I/O, settings validation.
Run: python -m pytest benchmarks/bench_cpu.py -v --tb=short
  or: python benchmarks/bench_cpu.py
"""
from __future__ import annotations

import sys
import os
import time
import tempfile
import statistics
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from queue import PriorityQueue
from imagura.types import LoadTask, LoadPriority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bench(func, rounds=100, label=""):
    """Run func `rounds` times, return (median_ms, min_ms, max_ms)."""
    times = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        func()
        times.append((time.perf_counter() - t0) * 1000)
    med = statistics.median(times)
    lo, hi = min(times), max(times)
    print(f"  {label:.<50s} median={med:.3f}ms  min={lo:.3f}ms  max={hi:.3f}ms  (n={rounds})")
    return med, lo, hi


# ---------------------------------------------------------------------------
# 1. PriorityQueue throughput
# ---------------------------------------------------------------------------

def bench_priority_queue_insert_1k():
    """Insert 1000 LoadTasks into PriorityQueue."""
    q = PriorityQueue()
    ts = time.time()
    for i in range(1000):
        prio = LoadPriority(i % 3)
        task = LoadTask(path=f"/img/{i}.jpg", priority=prio, callback=lambda *a: None, timestamp=ts + i * 0.001)
        q.put(task)


def bench_priority_queue_insert_and_drain_1k():
    """Insert 1000 tasks then drain all in priority order."""
    q = PriorityQueue()
    ts = time.time()
    for i in range(1000):
        prio = LoadPriority(i % 3)
        q.put(LoadTask(path=f"/img/{i}.jpg", priority=prio, callback=lambda *a: None, timestamp=ts + i * 0.001))
    while not q.empty():
        q.get_nowait()


def bench_priority_queue_insert_10k():
    """Insert 10000 LoadTasks — simulates large gallery."""
    q = PriorityQueue()
    ts = time.time()
    for i in range(10000):
        prio = LoadPriority(i % 3)
        q.put(LoadTask(path=f"/img/{i}.jpg", priority=prio, callback=lambda *a: None, timestamp=ts + i * 0.001))


# ---------------------------------------------------------------------------
# 2. User config I/O
# ---------------------------------------------------------------------------

def bench_user_config_save_load():
    """Save 20 config values then load them back."""
    from imagura.user_config import save_value, load_user_config, get_config_path, _parse_toml_simple

    with tempfile.TemporaryDirectory() as tmpdir:
        # Monkey-patch config dir for this bench
        original_get_dir = __import__("imagura.user_config", fromlist=["get_config_dir"]).get_config_dir
        __import__("imagura.user_config", fromlist=["get_config_dir"]).get_config_dir = lambda: Path(tmpdir)

        try:
            for i in range(20):
                save_value(f"KEY_{i}", i * 10, int)
            config_path = Path(tmpdir) / "config.toml"
            content = config_path.read_text()
            _parse_toml_simple(content)
        finally:
            __import__("imagura.user_config", fromlist=["get_config_dir"]).get_config_dir = original_get_dir


def bench_toml_parse_100_keys():
    """Parse TOML content with 100 keys."""
    from imagura.user_config import _parse_toml_simple

    lines = ["# Imagura config", ""]
    for i in range(100):
        if i % 2 == 0:
            lines.append(f"KEY_{i} = {i}")
        else:
            lines.append(f"KEY_{i} = {i * 0.1:.2f}")
    content = "\n".join(lines)

    _parse_toml_simple(content)


# ---------------------------------------------------------------------------
# 3. Settings validation
# ---------------------------------------------------------------------------

def bench_validate_settings_batch():
    """Validate 500 settings values (mix of valid/invalid)."""
    # Import from imagura2 — it defines validate_settings_value
    # For isolation, replicate the logic here
    def validate(value_str, val_type, min_val, max_val):
        if not value_str.strip():
            return False, None, "Empty"
        try:
            val = val_type(value_str)
        except ValueError:
            return False, None, "Invalid"
        if min_val is not None and val < min_val:
            return False, None, "Below min"
        if max_val is not None and val > max_val:
            return False, None, "Above max"
        return True, val, None

    test_cases = [
        ("120", int, 30, 240),
        ("0.95", float, 0.5, 1.0),
        ("abc", int, 0, 100),
        ("", float, 0, 1),
        ("999", int, 0, 100),
        ("-5", int, 0, 100),
        ("0.001", float, 0.01, 0.5),
        ("50", int, None, None),
    ]
    for _ in range(500 // len(test_cases)):
        for args in test_cases:
            validate(*args)


# ---------------------------------------------------------------------------
# 4. LoadTask comparison throughput
# ---------------------------------------------------------------------------

def bench_loadtask_sort_10k():
    """Sort 10000 LoadTasks — measures __lt__ performance."""
    import random
    ts = time.time()
    tasks = [
        LoadTask(
            path=f"/img/{i}.jpg",
            priority=LoadPriority(random.randint(0, 2)),
            callback=lambda *a: None,
            timestamp=ts + random.random(),
        )
        for i in range(10000)
    ]
    tasks.sort()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Imagura CPU Performance Benchmarks")
    print("=" * 70)

    print("\n[PriorityQueue]")
    _bench(bench_priority_queue_insert_1k, rounds=200, label="Insert 1K tasks")
    _bench(bench_priority_queue_insert_and_drain_1k, rounds=200, label="Insert+drain 1K tasks")
    _bench(bench_priority_queue_insert_10k, rounds=50, label="Insert 10K tasks (large gallery)")

    print("\n[LoadTask sorting]")
    _bench(bench_loadtask_sort_10k, rounds=50, label="Sort 10K tasks")

    print("\n[User config I/O]")
    _bench(bench_user_config_save_load, rounds=100, label="Save 20 keys + load")
    _bench(bench_toml_parse_100_keys, rounds=500, label="Parse 100-key TOML")

    print("\n[Settings validation]")
    _bench(bench_validate_settings_batch, rounds=200, label="Validate 500 values")

    print("\n" + "=" * 70)
    print("Done.")


if __name__ == "__main__":
    main()
