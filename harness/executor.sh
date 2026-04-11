#!/bin/bash
# Python 하네스로 라우팅. 원본: executor.sh.bak
exec python3 "$(dirname "$0")/executor.py" "$@"
