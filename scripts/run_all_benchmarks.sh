#!/bin/bash
set -e
cd "/mnt/c/Users/Manas/Downloads/Total Job Application process flow/projects/expert-role-matching-allocation"
echo "=== generate data ==="
.venv/bin/python scripts/generate_data.py
echo "=== fill rate benchmark ==="
.venv/bin/python scripts/run_fill_rate_benchmark.py
echo "=== load test ==="
.venv/bin/python scripts/run_load_test.py
echo "=== concurrency test ==="
.venv/bin/python scripts/run_concurrency_test.py
