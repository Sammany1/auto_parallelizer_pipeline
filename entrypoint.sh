#!/bin/bash
# =============================================================================
#  Auto-Parallelizer Pipeline  –  entrypoint.sh
#  Usage (inside Docker): ./entrypoint.sh <file.cpp>
# =============================================================================
set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m';  GREEN='\033[0;32m';  YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m';      RESET='\033[0m'

banner()  { echo -e "\n${CYAN}${BOLD}╔══════════════════════════════════════════════╗"; \
            printf "${CYAN}${BOLD}║  %-44s║\n" "$1"; \
            echo -e "╚══════════════════════════════════════════════╝${RESET}"; }
ok()      { echo -e "  ${GREEN}✔${RESET}  $*"; }
info()    { echo -e "  ${CYAN}➜${RESET}  $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
die()     { echo -e "  ${RED}✘  ERROR: $*${RESET}"; exit 1; }

# ── Args & paths ──────────────────────────────────────────────────────────
CPP_FILE="${1:-}"
[ -z "$CPP_FILE" ] && die "No C++ file specified.\n\n  docker run -v \$(pwd):/workspace <image> <file.cpp>"

WORKSPACE="/workspace"
SRC_PATH="$WORKSPACE/$CPP_FILE"
[ -f "$SRC_PATH" ] || die "File '$CPP_FILE' not found in /workspace (did you mount it with -v?)"

# Working copies live in /pipeline/work
WORK="/pipeline/work"
mkdir -p "$WORK"

BASENAME="${CPP_FILE%.cpp}"
PARALLEL_CPP="PARALLEL_${CPP_FILE}"
SEQ_BIN="$WORK/seq_run"
PAR_BIN="$WORK/par_run"
SEQ_TIME="$WORK/seq_time.txt"
PAR_TIME="$WORK/par_time.txt"
PERF_OUT="$WORK/perf_out.txt"
PATCH_FILE="$WORK/$PARALLEL_CPP"

cp "$SRC_PATH" "$WORK/$CPP_FILE"

# ── STEP 1 – Auto-Parallelise ─────────────────────────────────────────────
banner "STEP 1 · AST Auto-Parallelization"
python3 /pipeline/auto_parallelizer.py "$WORK/$CPP_FILE"

[ -f "$WORK/$PARALLEL_CPP" ] || die "Parallelizer produced no output – check your C++ source."

# Copy the generated parallel source back to the user's workspace
cp "$WORK/$PARALLEL_CPP" "$WORKSPACE/$PARALLEL_CPP"
ok "Parallel source written → $PARALLEL_CPP"

# ── STEP 2 – Compile ─────────────────────────────────────────────────────
banner "STEP 2 · Compilation"

info "Compiling sequential (g++ -O3)…"
if g++ -O3 "$WORK/$CPP_FILE" -o "$SEQ_BIN" 2>"$WORK/seq_compile.log"; then
    ok "seq_run compiled"
else
    cat "$WORK/seq_compile.log"
    die "Sequential compilation failed"
fi

info "Compiling parallel  (g++ -O3 -fopenmp)…"
if g++ -O3 -fopenmp "$WORK/$PARALLEL_CPP" -o "$PAR_BIN" 2>"$WORK/par_compile.log"; then
    ok "par_run compiled"
else
    cat "$WORK/par_compile.log"
    die "Parallel compilation failed"
fi

# ── STEP 3 – Benchmark ───────────────────────────────────────────────────
banner "STEP 3 · Benchmarking"

NUM_CORES=$(nproc)
info "Logical CPU cores available: $NUM_CORES"
export OMP_NUM_THREADS=$NUM_CORES

info "Running sequential binary…"
/usr/bin/time -v "$SEQ_BIN" >"$WORK/seq_stdout.txt" 2>"$SEQ_TIME" || true

info "Running parallel  binary…"
/usr/bin/time -v "$PAR_BIN" >"$WORK/par_stdout.txt" 2>"$PAR_TIME" || true

# ── Hardware counters – optional (needs --cap-add SYS_ADMIN or --privileged)
if command -v perf &>/dev/null; then
    info "Collecting hardware counters via perf…"
    perf stat -e cycles,instructions,cache-misses,task-clock "$PAR_BIN" \
        >"$WORK/perf_stdout.txt" 2>"$PERF_OUT" || warn "perf failed – try --privileged flag"
else
    warn "perf not available; skipping hardware counters."
    touch "$PERF_OUT"
fi

# ── STEP 4 – Analysis ────────────────────────────────────────────────────
banner "STEP 4 · Final Analysis"
python3 /pipeline/analyze_results.py \
    "$SEQ_TIME" "$PAR_TIME" "$PERF_OUT" \
    "$CPP_FILE" "$PARALLEL_CPP" "$NUM_CORES"
