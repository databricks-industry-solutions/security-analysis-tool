#!/bin/bash

folder="dabs"

# Check Python version
version=$(python -c "import sys; print(sys.version_info[:])" 2>&1)
if [[ -z "$version" ]]; then
    echo "Python not found"
    exit 1
fi

major=$(echo $version | cut -d ',' -f 1 | tr -d '(')
minor=$(echo $version | cut -d ',' -f 2)

if [[ $major -lt 3 || ($major -eq 3 && $minor -lt 9) ]]; then
    echo "Python 3.9 or higher is required"
    exit 1
fi

# Create and activate virtual environment
cd $folder
python -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt -q -q -q --exists-action i

# Run the main script
python main.py

# Deactivate virtual environment
deactivate

# Remove the virtual environment
rm -rf venv