#!/usr/bin/env bash

folder="dabs"
venv_dir=".venv"

# Find a suitable Python 3.9+ interpreter
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3 python; do
  if command -v $cmd &>/dev/null; then
    version=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    major=$(echo "$version" | cut -d '.' -f 1)
    minor=$(echo "$version" | cut -d '.' -f 2)
    if [[ "$major" -ge 3 && "$minor" -ge 9 ]]; then
      PYTHON_CMD=$cmd
      break
    fi
  fi
done

if [[ -z "$PYTHON_CMD" ]]; then
  echo "Python 3.9 or higher is required but not found."
  echo "Please install Python 3.9+ and ensure it's in your PATH."
  exit 1
fi

echo "Using Python: $PYTHON_CMD ($(${PYTHON_CMD} --version))"

# Create virtual environment if it doesn't exist
if [[ ! -d "$venv_dir" ]]; then
  echo "Creating virtual environment in $venv_dir..."
  $PYTHON_CMD -m venv $venv_dir
fi

# Activate virtual environment and install dependencies
# shellcheck source=/dev/null
source "$venv_dir/bin/activate"
echo "Virtual environment activated"

cd $folder || exit
pip install -r requirements.txt
python main.py
