#!/bin/bash

# Security Analysis Tool Installation Script
# This script detects Python installation and sets up the environment

set -e  # Exit on any error

folder="dabs"
PYTHON_CMD=""
PIP_CMD=""

# Function to check Python version
check_python_version() {
    local python_cmd=$1
    local version_output
    
    # Get Python version info
    version_output=$($python_cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    
    if [[ -z "$version_output" ]]; then
        return 1
    fi
    
    local major=$(echo $version_output | cut -d '.' -f 1)
    local minor=$(echo $version_output | cut -d '.' -f 2)
    
    # Check if version is 3.9 or higher
    if [[ $major -eq 3 && $minor -ge 9 ]] || [[ $major -gt 3 ]]; then
        echo "Found Python $version_output at $python_cmd"
        return 0
    else
        echo "Python $version_output found at $python_cmd, but version 3.9+ is required"
        return 1
    fi
}

# Function to detect Python command
detect_python() {
    echo "Detecting Python installation..."
    
    # Try different Python commands in order of preference
    for cmd in python3 python python3.12 python3.11 python3.10 python3.9; do
        if command -v $cmd >/dev/null 2>&1; then
            echo "Testing $cmd..."
            if check_python_version $cmd; then
                PYTHON_CMD=$cmd
                return 0
            fi
        fi
    done
    
    return 1
}

# Function to detect pip command
detect_pip() {
    echo "Detecting pip installation..."
    
    # Try different pip commands based on the Python command found
    local pip_candidates=()
    
    if [[ $PYTHON_CMD == "python3"* ]]; then
        pip_candidates=("pip3" "pip" "$PYTHON_CMD -m pip")
    else
        pip_candidates=("pip" "pip3" "$PYTHON_CMD -m pip")
    fi
    
    for pip_cmd in "${pip_candidates[@]}"; do
        if eval "command -v ${pip_cmd%% *}" >/dev/null 2>&1 || [[ $pip_cmd == *"-m pip" ]]; then
            # Test if pip command works
            if eval "$pip_cmd --version" >/dev/null 2>&1; then
                echo "Found pip: $pip_cmd"
                PIP_CMD=$pip_cmd
                return 0
            fi
        fi
    done
    
    return 1
}

# Main installation process
main() {
    echo "=== Security Analysis Tool Installation ==="
    echo
    
    # Detect Python
    if ! detect_python; then
        echo "ERROR: Python 3.9 or higher is required but not found."
        echo "Please install Python 3.9+ and try again."
        echo "Visit https://www.python.org/downloads/ for installation instructions."
        exit 1
    fi
    
    # Detect pip
    if ! detect_pip; then
        echo "ERROR: pip not found."
        echo "Please install pip for your Python installation."
        exit 1
    fi
    
    echo
    echo "Using Python: $PYTHON_CMD"
    echo "Using pip: $PIP_CMD"
    echo
       
    # Change to dabs directory
    echo "Changing to $folder directory..."
    cd "$folder"
    
    # Install requirements
    echo "Installing Python dependencies..."
    if ! eval "$PIP_CMD install -r requirements.txt"; then
        echo "ERROR: Failed to install requirements."
        echo "You may need to run: $PIP_CMD install --user -r requirements.txt"
        exit 1
    fi
    
    # Run the main script
    echo
    echo "Starting Security Analysis Tool..."
    echo "Running: $PYTHON_CMD main.py"
    echo
    exec $PYTHON_CMD main.py
}

# Run main function
main "$@"