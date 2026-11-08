"""Compare complete HEAD and working-tree snapshots against bundled opponents.

Run from the project directory: python tools/benchmark_changes.py
Every run gets its own output directory under benchmarks/.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import math
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import tarfile
import platform
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPPONENTS = ("random", "calling_station", "always_half", "always_pot")


def snapshot_hash(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [root / "agent.py", root / "game.py", root / "evaluator.py", root / "requirements.txt", root / "judge_engine.py"]
    paths += (sorted((root / "bot").glob("*.py")) + sorted((root / "data").glob("*.json"))
              + sorted((root / "baseline-bots").glob("*.py")))
    for path in paths:
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def wait_for_port(port: int, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server on port {port} exited: {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"server on port {port} did not start")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ref", default="HEAD")
    parser.add_argument("--baseline-working-tree", action="store_true",
                        help="compare a frozen copy of the working tree against experimental switches")
    parser.add_argument("--deals", type=int, default=1000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[101, 103, 107])
    parser.add_argument("--opponents", nargs="+", choices=OPPONENTS, default=OPPONENTS)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--candidate-table", type=Path,
                        help="install a table in the candidate snapshot for this run")
    parser.add_argument("--candidate-opponent-model", action="store_true")
    parser.add_argument("--candidate-time-budget", action="store_true")
    parser.add_argument("--candidate-adaptive-sampling", action="store_true")
    parser.add_argument("--both-time-budget", action="store_true",
                        help="enable the time budget for both versions")
    parser.add_argument("--both-adaptive-sampling", action="store_true",
                        help="enable adaptive sampling for both versions")
    parser.add_argument("--candidate-disable-forced-raise", action="store_true")
    args = parser.parse_args()
    if args.deals < 1 or len(set(args.seeds)) != len(args.seeds):
        parser.error("deals must be positive and seeds must be unique")
    out = args.out or ROOT / "benchmarks" / ("comparison-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    out.mkdir(parents=True, exist_ok=False)
    for port in (15008, 15009):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    with tempfile.TemporaryDirectory(prefix="poker-benchmark-") as temp:
        new_root = Path(temp) / "new"
        shutil.copytree(ROOT, new_root, ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".venv", "benchmarks"
        ))
        commit = None
        if args.baseline_working_tree:
            old_root = Path(temp) / "old"
            shutil.copytree(new_root, old_root)
        else:
            commit = subprocess.check_output(["git", "rev-parse", "--verify", args.baseline_ref + "^{commit}"], cwd=ROOT, text=True).strip()
            git_root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True).strip())
            project_path = ROOT.relative_to(git_root)
            command = ["git", "archive", commit]
            if str(project_path) != ".":
                command.append(project_path.as_posix())
            archive = subprocess.check_output(command, cwd=git_root)
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(temp, filter="data")
            old_root = Path(temp) / project_path
        if args.candidate_table:
            shutil.copyfile(args.candidate_table, new_root / "data" / "preflop_equity.json")
        shutil.make_archive(str(out / "baseline-snapshot"), "zip", root_dir=old_root)
        shutil.make_archive(str(out / "candidate-snapshot"), "zip", root_dir=new_root)
        metadata = {"baseline_commit": commit, "baseline_working_tree": args.baseline_working_tree,
                    "baseline_sha256": snapshot_hash(old_root),
                    "candidate_sha256": snapshot_hash(new_root), "python": sys.version,
                    "platform": platform.platform(), "processor": platform.processor(),
                    "seeds": args.seeds, "deals_per_half": args.deals,
                    "opponents": list(args.opponents), "command": sys.argv,
                    "candidate_opponent_model": args.candidate_opponent_model,
                    "candidate_time_budget": args.candidate_time_budget,
                    "candidate_adaptive_sampling": args.candidate_adaptive_sampling,
                    "both_time_budget": args.both_time_budget,
                    "both_adaptive_sampling": args.both_adaptive_sampling,
                    "candidate_disable_forced_raise": args.candidate_disable_forced_raise,
                    "packages": {name: importlib.metadata.version(name) for name in ("fastapi", "uvicorn")}}
        (out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"Results: {out}", flush=True)
        for opponent in args.opponents:
            for version, root in (("old", old_root), ("new", new_root)):
                processes = []
                try:
                    for port, path in ((15008, root / "agent.py"),
                                       (15009, new_root / "baseline-bots" / f"baseline_{opponent}.py")):
                        env = dict(os.environ, PORT=str(port))
                        env.pop("POKER_OPPONENT_MODEL", None)
                        env.pop("POKER_DISABLE_FORCED_RAISE", None)
                        env.pop("POKER_TIME_BUDGET", None)
                        env.pop("POKER_ADAPTIVE_SAMPLING", None)
                        if port == 15008:
                            if args.both_time_budget:
                                env["POKER_TIME_BUDGET"] = "1"
                            if args.both_adaptive_sampling:
                                env["POKER_ADAPTIVE_SAMPLING"] = "1"
                        if version == "new" and port == 15008:
                            if args.candidate_opponent_model:
                                env["POKER_OPPONENT_MODEL"] = "1"
                            if args.candidate_time_budget:
                                env["POKER_TIME_BUDGET"] = "1"
                            if args.candidate_adaptive_sampling:
                                env["POKER_ADAPTIVE_SAMPLING"] = "1"
                            if args.candidate_disable_forced_raise:
                                env["POKER_DISABLE_FORCED_RAISE"] = "1"
                        processes.append(subprocess.Popen(
                            [sys.executable, str(path)], cwd=path.parent,
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        ))
                        wait_for_port(port, processes[-1])
                    for seed in args.seeds:
                        output = out / f"{opponent}-{version}-{seed}.json"
                        command = [sys.executable, str(new_root / "judge_engine.py"),
                                   "--agent1", "http://127.0.0.1:15008",
                                   "--agent2", "http://127.0.0.1:15009",
                                   "--deals", str(args.deals), "--seed", str(seed),
                                   "--json", str(output)]
                        result = subprocess.run(command, cwd=new_root, capture_output=True,
                                                text=True, timeout=300)
                        if result.returncode or not output.exists():
                            raise RuntimeError(f"match failed: {command}\n{result.stdout}\n{result.stderr}")
                        data = json.loads(output.read_text())
                        print(f"{opponent} {version} seed={seed}: "
                              f"{data['mean_bb_per_deal']:+.3f} bb/deal; {data['reason']}", flush=True)
                finally:
                    for process in processes:
                        process.terminate()
                    for process in processes:
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()

    print("\nClean paired changes (new minus old), bb/deal:", flush=True)
    for opponent in args.opponents:
        deltas = []
        for seed in args.seeds:
            old = json.loads((out / f"{opponent}-old-{seed}.json").read_text())
            new = json.loads((out / f"{opponent}-new-{seed}.json").read_text())
            if any(stat["timed_out"] or stat["skipped_calls"] or stat["errors"] or stat["forfeited"]
                   for result in (old, new) for halves in result["agent_stats"].values()
                   for stat in halves):
                print(f"{opponent}: excluded seed {seed} due to a fault or timeout", flush=True)
                continue
            deltas.extend(n - o for n, o in zip(new["paired_bb"], old["paired_bb"], strict=True))
        if len(deltas) < 2:
            print(f"{opponent}: insufficient clean deals", flush=True)
            continue
        mean = statistics.mean(deltas)
        margin = 1.96 * statistics.stdev(deltas) / math.sqrt(len(deltas))
        print(f"{opponent}: {mean:+.3f} [{mean-margin:+.3f}, {mean+margin:+.3f}], n={len(deltas)}", flush=True)


if __name__ == "__main__":
    main()
