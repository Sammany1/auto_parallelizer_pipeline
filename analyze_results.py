"""
analyze_results.py  –  Parses /usr/bin/time -v output and perf stat output,
then prints a formatted benchmark report with speedup analysis.

Usage:
    python3 analyze_results.py <seq_time_file> <par_time_file> \
                               <perf_out_file>  <seq_src> <par_src> <cores>
"""

import sys
import re
import os

# ── ANSI colours ──────────────────────────────────────────────────────────────
R  = "\033[0;31m"
G  = "\033[0;32m"
Y  = "\033[1;33m"
C  = "\033[0;36m"
B  = "\033[1m"
W  = "\033[0m"

# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_wall_clock(filepath: str) -> float | None:
    """/usr/bin/time -v reports  m:ss.ss  or  h:mm:ss.ss"""
    try:
        text = open(filepath).read()
    except FileNotFoundError:
        return None

    # h:mm:ss.ss
    m = re.search(r"Elapsed \(wall clock\) time.*?:\s+(\d+):(\d+):(\d+\.\d+)", text)
    if m:
        return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])

    # m:ss.ss
    m = re.search(r"Elapsed \(wall clock\) time.*?:\s+(\d+):(\d+\.\d+)", text)
    if m:
        return int(m[1]) * 60 + float(m[2])

    return None


def parse_max_rss(filepath: str) -> int | None:
    try:
        text = open(filepath).read()
    except FileNotFoundError:
        return None
    m = re.search(r"Maximum resident set size.*?:\s+(\d+)", text)
    return int(m[1]) if m else None


def parse_cpu_percent(filepath: str) -> str | None:
    try:
        text = open(filepath).read()
    except FileNotFoundError:
        return None
    m = re.search(r"Percent of CPU this job got:\s+(\S+)", text)
    return m[1] if m else None


def parse_perf(filepath: str) -> dict:
    result = {}
    try:
        text = open(filepath).read()
    except FileNotFoundError:
        return result

    patterns = {
        "cycles":        r"([\d,]+)\s+cycles",
        "instructions":  r"([\d,]+)\s+instructions",
        "cache_misses":  r"([\d,]+)\s+cache-misses",
        "task_clock_ms": r"([\d,.]+)\s+msec\s+task-clock",
        "ipc":           r"([\d.]+)\s+insn per cycle",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            val = m[1].replace(",", "")
            result[key] = float(val) if "." in val else int(val)

    return result


# ── Formatters ────────────────────────────────────────────────────────────────

def fmt_time(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.1f} ms"
    return f"{seconds:.4f} s"


def fmt_int(n: int) -> str:
    return f"{n:,}"


def rating(speedup: float, cores: int) -> tuple[str, str]:
    efficiency = speedup / cores * 100
    if efficiency >= 80:
        colour, label = G, "Excellent"
    elif efficiency >= 50:
        colour, label = Y, "Good"
    elif efficiency >= 25:
        colour, label = Y, "Moderate"
    else:
        colour, label = R, "Poor"
    return colour, f"{label}  ({efficiency:.1f}% parallel efficiency)"


def divider(char="─", width=54):
    print(C + char * width + W)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 7:
        print("Usage: analyze_results.py <seq_time> <par_time> <perf_out> "
              "<seq_src> <par_src> <cores>")
        sys.exit(1)

    seq_tf, par_tf, perf_tf = sys.argv[1], sys.argv[2], sys.argv[3]
    seq_src, par_src        = sys.argv[4], sys.argv[5]
    cores                   = int(sys.argv[6])

    seq_t = parse_wall_clock(seq_tf)
    par_t = parse_wall_clock(par_tf)
    seq_rss = parse_max_rss(seq_tf)
    par_rss = parse_max_rss(par_tf)
    par_cpu = parse_cpu_percent(par_tf)
    perf    = parse_perf(perf_tf)

    print()
    divider("═")
    print(f"{B}{C}  BENCHMARK REPORT{W}")
    divider("═")

    # ── Sources
    print(f"\n  {B}Source files{W}")
    print(f"    Sequential : {seq_src}")
    print(f"    Parallel   : {par_src}")
    print(f"    OMP cores  : {cores}")

    # ── Timing
    print(f"\n  {B}Wall-clock timing{W}")
    divider()
    if seq_t is not None:
        print(f"    Sequential time : {B}{fmt_time(seq_t)}{W}")
    else:
        print(f"    Sequential time : {R}unavailable{W}")

    if par_t is not None:
        print(f"    Parallel   time : {B}{fmt_time(par_t)}{W}")
    else:
        print(f"    Parallel   time : {R}unavailable{W}")

    # ── Speedup
    if seq_t and par_t and par_t > 0:
        speedup  = seq_t / par_t
        time_saved = seq_t - par_t
        col, rating_str = rating(speedup, cores)

        print()
        print(f"    Speedup         : {col}{B}{speedup:.2f}×{W}")
        print(f"    Time saved      : {col}{fmt_time(time_saved)}{W}")
        print(f"    Rating          : {col}{rating_str}{W}")

        # Amdahl bound: theoretical max with 'cores' threads assuming efficiency
        amdahl = cores  # upper bound
        print(f"    Theoretical max : {amdahl:.0f}× (Amdahl upper bound for {cores} cores)")
    else:
        print(f"\n    {Y}Could not compute speedup – timing data unavailable.{W}")

    # ── Memory
    if seq_rss or par_rss:
        print(f"\n  {B}Memory usage (max RSS){W}")
        divider()
        if seq_rss:
            print(f"    Sequential : {fmt_int(seq_rss)} kB")
        if par_rss:
            overhead = ""
            if seq_rss:
                delta = par_rss - seq_rss
                sign  = "+" if delta >= 0 else ""
                overhead = f"  ({sign}{fmt_int(delta)} kB vs sequential)"
            print(f"    Parallel   : {fmt_int(par_rss)} kB{overhead}")
        if par_cpu:
            print(f"    CPU usage  : {par_cpu}  (parallel run)")

    # ── Hardware counters
    if perf:
        print(f"\n  {B}Hardware counters  (parallel run){W}")
        divider()
        if "cycles"       in perf: print(f"    Cycles            : {fmt_int(perf['cycles'])}")
        if "instructions" in perf: print(f"    Instructions      : {fmt_int(perf['instructions'])}")
        if "ipc"          in perf: print(f"    IPC               : {perf['ipc']:.2f}")
        if "cache_misses" in perf:
            cm = perf["cache_misses"]
            ins = perf.get("instructions", None)
            miss_rate = f"  ({cm/ins*100:.3f}% of instructions)" if ins else ""
            print(f"    Cache misses      : {fmt_int(int(cm))}{miss_rate}")
        if "task_clock_ms" in perf:
            print(f"    Task-clock        : {perf['task_clock_ms']:.1f} ms")
    else:
        print(f"\n  {Y}No perf data – run with --privileged for hardware counters.{W}")

    # ── Recommendations
    print(f"\n  {B}Recommendations{W}")
    divider()

    if seq_t and par_t:
        speedup = seq_t / par_t
        efficiency = speedup / cores * 100

        if efficiency < 25 and cores > 1:
            print(f"    {Y}⚠{W}  Low efficiency – check for false sharing, load imbalance,")
            print(f"         or synchronisation overhead in the generated pragmas.")
        if efficiency >= 80:
            print(f"    {G}✔{W}  Strong scaling – the workload is well-suited for OpenMP.")

    if perf and perf.get("cache_misses", 0) > 1_000_000:
        print(f"    {Y}⚠{W}  High cache miss count – consider improving data locality")
        print(f"         (loop tiling, structure-of-arrays, prefetching).")

    if perf and perf.get("ipc", 99) < 1.0:
        print(f"    {Y}⚠{W}  IPC < 1.0 – pipeline stalls detected; memory-bound workload.")

    print(f"    {C}ℹ{W}  Re-run with --privileged to enable full perf stat profiling.")
    print(f"    {C}ℹ{W}  Tune OMP_NUM_THREADS to match your physical (not logical) cores.")
    print(f"    {C}ℹ{W}  Try schedule(dynamic) for loops with uneven iteration costs.")

    divider("═")
    print()


if __name__ == "__main__":
    main()
