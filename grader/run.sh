#!/bin/sh
# Runs as root inside the container. Sets up the working directory, drops
# to the unprivileged `ag` user for the actual grading (which execs
# untrusted student code), then prints whatever result JSON the grading
# run produced.
set -e

mkdir -p /grade/work /grade/results
cp /submission/student_code.py /grade/work/student_code.py
cp /submission/setup_code.py /grade/work/setup_code.py
cp /submission/test_code.py /grade/work/test_code.py

SECRET=$(python3 -c "import uuid; print(uuid.uuid4().hex)")

chown -R ag:ag /grade/work /grade/results

su -s /bin/sh ag -c "PL_RESULT_FILENAME='$SECRET' python3 /opt/harness/runner.py"

if [ ! -f "/grade/results/$SECRET" ]; then
  echo '{"error": "grading job crashed: no result file produced", "test_results": [], "passed_count": 0, "total_count": 0}'
fi
