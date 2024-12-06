#!/bin/bash

# sh <(curl -fsSL https://raw.githubusercontent.com/jgarciaf106/security-analysis-tool/main/install.sh)

# TUI settings
COLUMNS=12

# Configurable options
VERBOSE=true
CLEAR_SCREEN=true

clear_screen() {
  [[ "$CLEAR_SCREEN" == "true" ]] && clear
}

log() {
  [[ "$VERBOSE" == "true" ]] && echo -e "$1"
}

# Variables
RUNNING_MODE="remote"
SAT_INSTALLED=0
REPO="jgarciaf106/security-analysis-tool"
PREFIX=$(echo "$REPO" | cut -d'/' -f1)
DOWNLOAD_DIR="./"
INSTALLATION_DIR="sat-installer"
PYTHON_BIN="python3.11"
ENV_NAME=".env"

# Functions
running_location() {
  if [[ "$RUNNING_MODE" == "remote" ]]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
      desktop_path="$HOME/Desktop"
      if [[ -d "$desktop_path" ]]; then
        cd "$desktop_path" || { echo "Error: Failed to change directory to $desktop_path on macOS"; exit 1; }
      else
        echo "Error: Desktop directory not found at $desktop_path on macOS"; exit 1
      fi
    elif [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* ]]; then
      desktop_path="$USERPROFILE/Desktop"
      if [[ -d "$desktop_path" ]]; then
        cd "$desktop_path" || { echo "Error: Failed to change directory to $desktop_path on Windows"; exit 1; }
      else
        echo "Error: Desktop directory not found at $desktop_path on Windows"; exit 1
      fi
    else
      echo "Error: Unsupported operating system ($OSTYPE)"; exit 1
    fi
  fi
  log "Running location: $(pwd)"
}

running_mode() {
  if [[ -d "docs" || -d "images" || -n "$(find . -maxdepth 1 -name '*.md' -o -name 'LICENSE' -o -name 'NOTICE')" ]]; then
    RUNNING_MODE="local"
  fi
  log "Determined running mode: $RUNNING_MODE"
}

is_sat_installed() {
  if [[ -n $(find . -type f -name "tfplan" | head -n 1) || -n $(find . -type d -name ".databricks" | head -n 1) ]]; then
    SAT_INSTALLED=1
  fi
  log "SAT installed status: $SAT_INSTALLED"
}

download_latest_release() {
  local release_info url file_name file_path

  release_info=$(curl --silent "https://api.github.com/repos/$REPO/releases/latest")
  url=$(echo "$release_info" | grep '"zipball_url"' | sed -E 's/.*"([^"]+)".*/\1/')

  if [[ -z "$url" ]]; then
    echo "Failed to fetch the latest release URL for SAT."; exit 1
  fi

  file_name="$(basename "$url").zip"
  file_path="$DOWNLOAD_DIR/$file_name"
  curl -s -L "$url" -o "$file_path" || { echo "Error: Failed to download $url"; exit 1; }

  echo "$file_path"
}

setup_sat() {
  log "Downloading the latest release of SAT..."
  local file_path temp_dir solution_dir

  file_path=$(download_latest_release)
  mkdir -p "$INSTALLATION_DIR"

  if [[ "$file_path" == *.zip ]]; then
    temp_dir=$(mktemp -d)

    log "Extracting SAT..."
    unzip -q "$file_path" -d "$temp_dir" || { echo "Error: Failed to extract $file_path"; exit 1; }

    solution_dir=$(find "$temp_dir" -type d -name "$PREFIX*")

    if [[ -d "$solution_dir" ]]; then
      for folder in terraform src notebooks dashboards dabs configs; do
        [[ -d "$solution_dir/$folder" ]] && cp -r "$solution_dir/$folder" "$INSTALLATION_DIR"
      done

      install_file=$(find "$solution_dir" -type f -name "install.sh")
      if [[ -f "$install_file" ]]; then
        log "Copying install.sh..."
        cp "$install_file" "$INSTALLATION_DIR"
      else
        log "Warning: install.sh not found in the release."
      fi
    else
      echo "Error: No solution folder found in the extracted contents."; rm -rf "$temp_dir"; exit 1
    fi

    rm -rf "$temp_dir"
  fi

  rm "$file_path"
}

install_sat() {
  if [[ "$RUNNING_MODE" == "remote" ]]; then
    get_github_project || { echo "Failed to setup SAT."; exit 1; }
  fi

  clear_screen

  options=("Terraform" "CLI")
  [[ $SAT_INSTALLED -eq 1 ]] && options+=("Uninstall")

  echo "==============================="
  echo "How do you want to install SAT?"
  echo "==============================="
  select opt in "${options[@]}"; do
    case $opt in
      "Terraform")
        terraform_install || { echo "Failed to install SAT via Terraform."; exit 1; }
        break
        ;;
      "CLI")
        shell_install || { echo "Failed to install SAT via Terminal."; exit 1; }
        break
        ;;
      "Uninstall")
        [[ $SAT_INSTALLED -eq 1 ]] && uninstall || { echo "Failed to uninstall SAT."; exit 1; }
        break
        ;;
      *)
        echo "Invalid option.";
        ;;
    esac
  done
}

main() {
  log "Determining running mode..."
  running_mode || { echo "Failed to determine the running mode."; exit 1; }

  log "Checking running location..."
  running_location || { echo "Failed to determine the running location."; exit 1; }

  log "Checking if SAT is already installed..."
  is_sat_installed || { echo "Failed to determine if SAT is installed."; exit 1; }

  log "Starting SAT installation..."
  install_sat || { echo "Failed to install SAT."; exit 1; }

  log "SAT installation completed successfully."
}

# Run the script
main
