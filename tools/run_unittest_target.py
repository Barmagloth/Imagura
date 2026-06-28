from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_child(target: str, run_id: str) -> int:
    os.environ["IMAGURA_CODEX_RUN"] = "1"
    os.environ["IMAGURA_CODEX_RUN_ID"] = run_id
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    suite = unittest.defaultTestLoader.loadTestsFromName(target)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def run_parent(target: str, timeout_s: float, run_id: str) -> int:
    env = os.environ.copy()
    env["IMAGURA_CODEX_RUN"] = "1"
    env["IMAGURA_CODEX_RUN_ID"] = run_id

    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--codex-run-id",
        run_id,
        target,
    ]

    print(f"[RUNNER] run_id={run_id} target={target} timeout_s={timeout_s}", flush=True)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            timeout=timeout_s,
            text=True,
            capture_output=True,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        print(f"[RUNNER][TIMEOUT] run_id={run_id} target={target} elapsed_s={elapsed:.2f}", flush=True)
        if exc.stdout:
            print(exc.stdout[-2000:], end="" if exc.stdout.endswith("\n") else "\n")
        if exc.stderr:
            print(exc.stderr[-4000:], end="" if exc.stderr.endswith("\n") else "\n", file=sys.stderr)
        return 124

    elapsed = time.monotonic() - started
    print(f"[RUNNER] exit={proc.returncode} elapsed_s={elapsed:.2f}", flush=True)
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one unittest target in a marked child process.")
    parser.add_argument("target", help="Unittest target, e.g. tests.test_smoke.ViewMathSmokeTests")
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout in seconds.")
    parser.add_argument("--codex-run-id", default=f"codex-{os.getpid()}-{time.time_ns()}")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child:
        return run_child(args.target, args.codex_run_id)
    return run_parent(args.target, args.timeout, args.codex_run_id)


if __name__ == "__main__":
    raise SystemExit(main())
