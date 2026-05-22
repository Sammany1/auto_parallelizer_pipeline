# Auto-Parallelizer Docker Pipeline

Turns any sequential C++ file into an OpenMP-parallelised binary,
benchmarks both, and prints a full analysis — in a **single command**.

## Quick Start

```bash
# 1. Build the image (once)
docker build -t auto-parallelizer .

# 2. Run the pipeline – mount the folder containing your .cpp file
docker run --rm -v "$(pwd):/workspace" auto-parallelizer my_file.cpp
```

The pipeline will:
1. **Auto-parallelise** – walk the AST, inject `#pragma omp` pragmas
2. **Compile** – build both sequential and parallel binaries with `-O3`
3. **Benchmark** – measure wall-clock time with `/usr/bin/time -v`
4. **Analyse** – print speedup, memory, and recommendations

The generated `PARALLEL_my_file.cpp` is written back to your working directory.

## Hardware counters (perf)

Add `--privileged` to enable `perf stat` hardware counter collection:

```bash
docker run --rm --privileged -v "$(pwd):/workspace" auto-parallelizer my_file.cpp
```

## Control thread count

```bash
docker run --rm -e OMP_NUM_THREADS=4 -v "$(pwd):/workspace" auto-parallelizer my_file.cpp
```

## Files

| File                  | Purpose                                        |
|-----------------------|------------------------------------------------|
| `Dockerfile`          | Container image definition                     |
| `entrypoint.sh`       | Orchestrates all 4 pipeline steps              |
| `auto_parallelizer.py`| AST walker – detects & injects OpenMP pragmas  |
| `analyze_results.py`  | Parses timing/perf output, prints final report |
