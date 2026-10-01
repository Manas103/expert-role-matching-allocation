#!/bin/bash
set -e
cd "/mnt/c/Users/Manas/Downloads/Total Job Application process flow/projects/expert-role-matching-allocation"
PGPASSWORD=erm_app_pw_local_dev psql -h 127.0.0.1 -U erm_app -d expert_matching -f app/schema.sql
PGPASSWORD=erm_app_pw_local_dev psql -h 127.0.0.1 -U erm_app -d expert_matching -c "\dt"
