FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# ── System deps ──────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    build-essential \
    libomp-dev \
    python3-clang \
    libclang-dev \
    python3-pip \
    time \
    # perf – best-effort: may not match the host kernel, handled gracefully
    linux-tools-common \
    linux-tools-generic \
    && rm -rf /var/lib/apt/lists/*

# ── Pipeline scripts ──────────────────────────────────────────────────────────
WORKDIR /pipeline

COPY auto_parallelizer.py  .
COPY entrypoint.sh         .
COPY analyze_results.py    .

RUN chmod +x entrypoint.sh

# ── Usage: docker run -v $(pwd):/workspace <image> <file.cpp> ─────────────────
ENTRYPOINT ["./entrypoint.sh"]
