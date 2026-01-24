#!/usr/bin/env python3
import filecmp
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

# Constants and Paths setup
# Assuming script is in tests/ directory, so root is parent.
TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
DATA_DIR = PROJECT_ROOT / "res" / "testdata"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
FIXTURES_DIR = DATA_DIR / "fixtures"
TEMP_DIR = PROJECT_ROOT / ".tmp"
CACHE_DIR = TEMP_DIR / "offline_cache"
OUTPUT_DIR = TEMP_DIR / "stress_test"

# Env file for expectations
FIXTURES_ENV = TESTS_DIR / "fixtures.env"


def load_expectations():
    """Load EXPECTED_* variables from fixtures.env manually."""
    expectations = {}
    if not FIXTURES_ENV.exists():
        print(f"❌ Fixtures env file missing: {FIXTURES_ENV}")
        sys.exit(1)

    with open(FIXTURES_ENV, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("export "):
                key_val = line.replace("export ", "").split("=")
                if len(key_val) == 2:
                    expectations[key_val[0]] = int(key_val[1])
    return expectations


def setup_cache():
    """Setup offline cache by merging part1 and part2 fixtures."""
    print(f"📂 Setting up offline cache in {CACHE_DIR}...")

    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "requests").mkdir(exist_ok=True)

    if not (FIXTURES_DIR / "part1").exists() or not (FIXTURES_DIR / "part2").exists():
        print("❌ Fixtures missing! Run regular stress test to populate.")
        sys.exit(1)

    # Copy Part 1
    print("ℹ️  Copying part1 fixtures...")
    part1_req = FIXTURES_DIR / "part1" / "requests"
    for item in part1_req.iterdir():
        if item.is_file():
            shutil.copy2(item, CACHE_DIR / "requests" / item.name)

    # Rename part1 redirects
    cache_req = CACHE_DIR / "requests"
    redirects = cache_req / "redirects.sqlite"
    if redirects.exists():
        redirects.rename(cache_req / "redirects_part1.sqlite")
    print("✓ Part 1 copied.")

    # Copy Part 2
    print("ℹ️  Copying part2 fixtures...")
    part2_req = FIXTURES_DIR / "part2" / "requests"
    for item in part2_req.iterdir():
        if item.is_file():
            shutil.copy2(item, CACHE_DIR / "requests" / item.name)

    # Merge redirects
    redirects_p1 = cache_req / "redirects_part1.sqlite"
    redirects_main = cache_req / "redirects.sqlite"

    if redirects_p1.exists() and redirects_main.exists():
        print("ℹ️  Merging redirects.sqlite...")
        conn = sqlite3.connect(redirects_main)
        conn.execute(f"ATTACH '{redirects_p1}' AS p1")
        conn.execute("INSERT OR IGNORE INTO main.redirects SELECT * FROM p1.redirects")
        conn.commit()
        conn.close()
        redirects_p1.unlink()
    elif redirects_p1.exists():
        redirects_p1.rename(redirects_main)

    print("✓ Part 2 copied and redirects merged.")


def check_diff(generated_path, artifact_path, label):
    """Compare generated file with artifact."""
    if not artifact_path.exists():
        print(
            f"⚠️  Artifact {label} not found at {artifact_path}. Skipping verification."
        )
        return True

    print(f"Checking {label}...")

    # Simple binary comparison first (fast)
    if filecmp.cmp(generated_path, artifact_path, shallow=False):
        print(f"✓ {label} matches artifact exactly.")
        return True

    print(f"⚠️  {label} differs from artifact. Showing diff (first 10 lines):")
    print("Diff Stat:")
    subprocess.run(
        [
            "git",
            "diff",
            "--no-index",
            "--stat",
            str(generated_path),
            str(artifact_path),
        ],
        check=False,
    )
    print("...")
    subprocess.run(
        ["diff", "--color=always", str(generated_path), str(artifact_path)], check=False
    )
    print(f"❌ Verified failed for {label}")
    return False


def test_offline():
    # 1. Load Expectations
    expectations = load_expectations()
    exp_ada = expectations.get("EXPECTED_ADA_LINES", 0)
    exp_marie = expectations.get("EXPECTED_MARIE_LINES", 0)

    # 2. Setup Cache
    setup_cache()

    # 3. Prepare Output Dir
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 4. Define Command Environment
    env = os.environ.copy()
    # Explicitly set COVERAGE_FILE for subprocesses to avoid conflicts
    # They will append to unique files based on pid automagically if parallel=True is set (which -p flag does)
    # But we need to point them to the right directory
    env["COVERAGE_FILE"] = str(PROJECT_ROOT / ".tmp" / ".coverage")

    env["GMA_CACHE_DIR"] = str(CACHE_DIR)
    env["GMA_I_RESPECT_FAMILYSEARCH_PLEASE_SUPPRESS_LICENSE_PROMPT"] = "1"
    env["FAMILYSEARCH_USER"] = env.get("FAMILYSEARCH_USER", "offline_test_user")
    env["FAMILYSEARCH_PASS"] = env.get("FAMILYSEARCH_PASS", "dummy_password")
    env["GMA_OFFLINE_MODE"] = "1"
    env["GMA_DEBUG"] = "1"
    if "NO_CACHE" in env:
        del env["NO_CACHE"]

    # Constants
    timestamp = "2026-01-20T22:30:10"
    date_flag = ["--creation-date", timestamp]
    id1 = "29HC-P5H"  # Ada
    id2 = "LC5H-V1Z"  # Marie
    anc_gen = "3"
    desc_gen = "2"

    part1 = OUTPUT_DIR / "part1_ada_a3.ged"
    part2 = OUTPUT_DIR / "part2_marie_a3.ged"
    merged = OUTPUT_DIR / "merged_scientists.ged"

    log1 = OUTPUT_DIR / "part1.log"
    log2 = OUTPUT_DIR / "part2.log"
    log_merge = OUTPUT_DIR / "merge.log"

    print("🚀 Running Stress Test in OFFLINE mode (using fixtures)...")

    # 5. Run Ada Extraction
    print("Running Ada Lovelace extraction...")
    cmd1 = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "-p",
        "-m",
        "getmyancestors",
        "--verbose",
        "-u",
        env["FAMILYSEARCH_USER"],
        "-p",
        env["FAMILYSEARCH_PASS"],
        "-i",
        id1,
        "-a",
        anc_gen,
        "-d",
        desc_gen,
        "--rate-limit",
        "5",
        "--cache",
        "--no-cache-control",
        *date_flag,
        "-o",
        str(part1),
    ]
    with open(log1, "w", encoding="utf-8") as log:
        subprocess.run(cmd1, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    # 6. Run Marie Extraction
    print("Running Marie Curie extraction...")
    cmd2 = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "-p",
        "-m",
        "getmyancestors",
        "--verbose",
        "-u",
        env["FAMILYSEARCH_USER"],
        "-p",
        env["FAMILYSEARCH_PASS"],
        "-i",
        id2,
        "-a",
        anc_gen,
        "-d",
        desc_gen,
        "--rate-limit",
        "5",
        "--cache",
        "--no-cache-control",
        *date_flag,
        "-o",
        str(part2),
    ]
    with open(log2, "w", encoding="utf-8") as log:
        subprocess.run(cmd2, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    # 7. Run Merge
    print("Merging parts...")
    cmd_merge = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "-p",
        "-m",
        "getmyancestors.mergemyanc",
        "-i",
        str(part1),
        "-i",
        str(part2),
        "-o",
        str(merged),
        "--creation-date",
        timestamp,
    ]
    with open(log_merge, "w", encoding="utf-8") as log:
        subprocess.run(
            cmd_merge, env=env, stdout=log, stderr=subprocess.STDOUT, check=True
        )

    # 8. Validation
    if not merged.exists() or merged.stat().st_size == 0:
        print("❌ Merge Failed or output empty.")
        with open(log_merge, "r", encoding="utf-8") as f:
            print(f.read())
        sys.exit(1)

    print("✅ Stress Test Validated!")

    # Line Counts
    def count_lines(p):
        with open(p, "rb") as f:
            return sum(1 for _ in f)

    l_part1 = count_lines(part1)
    l_part2 = count_lines(part2)
    l_merged = count_lines(merged)

    print(f"Lines: {l_merged}")
    print("--- Assertion Results ---")

    failed = False

    if l_part1 != exp_ada:
        print(f"❌ Assertion Failed: Ada (Part 1) line count {l_part1} != {exp_ada}")
        failed = True
    else:
        print(f"✓ Ada (Part 1) lines verified exactly ({l_part1}).")

    if l_part2 != exp_marie:
        print(
            f"❌ Assertion Failed: Marie Curie (Part 2) line count {l_part2} != {exp_marie}"
        )
        failed = True
    else:
        print(f"✓ Marie Curie (Part 2) lines verified ({l_part2}).")

    # Check merged file with exact diff (no line count tolerance)
    diff_result = subprocess.run(
        [
            "git",
            "diff",
            "--no-index",
            "--exit-code",
            "--color=always",
            str(merged),
            str(ARTIFACTS_DIR / "merged_scientists.ged"),
        ],
        check=False,
    )
    if diff_result.returncode != 0:
        print("❌ Merged file differs from artifact (see diff above)")
        print("Diff Stat:")
        subprocess.run(
            [
                "git",
                "diff",
                "--no-index",
                "--stat",
                str(merged),
                str(ARTIFACTS_DIR / "merged_scientists.ged"),
            ],
            check=False,
        )
        failed = True
    else:
        print(f"✓ Merged file matches artifact exactly ({l_merged} lines).")

    if failed:
        sys.exit(1)

    # 9. Artifact Verification
    print("\n=== Artifact Verification ===")

    # Allow loose comparison for minor diffs? No, strict mode requested.
    all_matched = True
    all_matched &= check_diff(
        part1, ARTIFACTS_DIR / f"part1_ada_a{anc_gen}.ged", "Ada (Part 1)"
    )
    all_matched &= check_diff(
        part2, ARTIFACTS_DIR / f"part2_marie_a{anc_gen}.ged", "Marie (Part 2)"
    )
    all_matched &= check_diff(
        merged, ARTIFACTS_DIR / "merged_scientists.ged", "Merged Result"
    )

    if not all_matched:
        print("❌ Offline Test Failed due to artifact mismatch")
        sys.exit(1)

    print("✅ Offline Test Complete!")


if __name__ == "__main__":
    test_offline()
