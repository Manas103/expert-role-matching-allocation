#!/bin/bash
set -e
cd "/mnt/c/Users/Manas/Downloads/Total Job Application process flow/projects/expert-role-matching-allocation"
.venv/bin/python -m pytest tests/ -v 2>&1
echo "PYTEST_EXIT=$?"
