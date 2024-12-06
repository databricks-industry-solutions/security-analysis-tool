#!/bin/bash

# sh <(curl -fsSL https://raw.githubusercontent.com/jgarciaf106/security-analysis-tool/main/install.sh)

# TUI settings
COLUMNS=12

clear

# variables
RUNNING_MODE="remote"
SAT_INSTALLED=0
#REPO="databricks-industry-solutions/security-analysis-tool"
REPO="jgarciaf106/security-analysis-tool"
PREFIX=$(echo "$REPO" | cut -d'/' -f1)
DOWNLOAD_DIR="./"
INSTALLATION_DIR="sat-installer"
PYTHON_BIN="python3.11"
ENV_NAME=".env"

# Functions
running_location(){
  if [[ "$RUNNING_MODE" == "remote" ]]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
      desktop_path="$HOME/Desktop"
      if [[ -d "$desktop_path" ]]; then
          cd "$desktop_path" || { echo "Error: Failed to change directory to $desktop_path on macOS"; exit 1; }
      else
          echo "Error: Desktop directory not found at $desktop_path on macOS"
          exit 1
      fi
    elif [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* ]]; then
        desktop_path="$USERPROFILE/Desktop"
        if [[ -d "$desktop_path" ]]; then
            cd "$desktop_path" || { echo "Error: Failed to change directory to $desktop_path on Windows"; exit 1; }
        else
            echo "Error: Desktop directory not found at $desktop_path on Windows"
            exit 1
        fi
    else
        echo "Error: Unsupported operating system ($OSTYPE)"
        exit 1
    fi
  fi

  pwd
  echo "Running mode: $desktop_path"
}
running_mode() {
  if [[ -d "docs" || -d "images" || -n "$(find . -maxdepth 1 -name '*.md' -o -name 'LICENSE' -o -name 'NOTICE')" ]]; then
    RUNNING_MODE="local"
  fi
}

is_sat_installed(){
  if [[ -n $(find . -type f -name "tfplan" | head -n 1) || -n $(find . -type d -name ".databricks" | head -n 1) ]]; then
    SAT_INSTALLED=1
  fi
}

get_github_project(){
  if [[ "$RUNNING_MODE" == "remote" ]]; then
    if [[ ! -d "config" && ! -d "dabs" && ! -d "dashboards" && ! -d "notebooks" && ! -d "src" && ! -d "terraform" ]]; then
      setup_sat
      cd "$INSTALLATION_DIR" || { echo "Failed to change directory to $INSTALLATION_DIR"; exit 1; }
    fi
  fi
}

download_latest_release() {
    local release_info file_name file_path

    release_info=$(curl --silent "https://api.github.com/repos/$REPO/releases/latest")
    url=$(echo "$release_info" | grep '"zipball_url"' | sed -E 's/.*"([^"]+)".*/\1/')

    if [[ -z "$url" ]]; then
        echo "Failed to fetch the latest release URL for SAT."
        exit 1
    fi

    # shellcheck disable=SC2155
    file_name="$(basename "$url").zip"
    file_path="$DOWNLOAD_DIR/$file_name"
    curl -s -L "$url" -o "$file_path" || { echo "Error: Failed to download $url"; exit 1; }

    echo "$file_path"
}

setup_sat() {
    echo "Downloading the latest release of SAT..."
    local file_path
    file_path=$(download_latest_release)

    mkdir -p "$INSTALLATION_DIR"

    if [[ "$file_path" == *.zip ]]; then
        temp_dir=$(mktemp -d)

        echo "Extracting SAT..."
        unzip -q "$file_path" -d "$temp_dir" || { echo "Error: Failed to extract $file_path"; exit 1; }

        solution_dir=$(find "$temp_dir" -type d -name "$PREFIX*")

        if [[ -d "$solution_dir" ]]; then
            for folder in terraform src notebooks dashboards dabs configs; do
                if [[ -d "$solution_dir/$folder" ]]; then
                    cp -r "$solution_dir/$folder" "$INSTALLATION_DIR"
                fi
            done

            install_file=$(find "$solution_dir" -type f -name "install.sh")
            if [[ -f "$install_file" ]]; then
                echo "Downloading install.sh..."
                cp "$install_file" "$INSTALLATION_DIR"
            else
                echo "Warning: install.sh not found in the release."
            fi
        else
            echo "Error: No 'databricks-industry-solutions' folder found in the extracted contents."
            rm -rf "$temp_dir"
            exit 1
        fi

        rm -rf "$temp_dir"
    fi

    rm "$file_path"
}

setup_env(){
    # Check  if Python is installed
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        echo "Python 3.11 not found. Trying to find another Python 3 interpreter..."
        PYTHON_BIN="python3"
        if ! command_exists "$PYTHON_BIN"; then
            echo "No suitable Python interpreter found. Please install Python 3.11 or Python 3."
            exit 1
        fi
        echo "Using $PYTHON_BIN as a fallback."
    fi

    # Create virtual environment
    echo "Creating virtual environment $ENV_NAME..."

    if ! "$PYTHON_BIN" -m venv "$ENV_NAME"; then
        echo "Failed to create virtual environment. Ensure Python 3.11 or Python 3 is properly installed."
        exit 1
    fi

    # Activate the virtual environment
    source "$ENV_NAME/bin/activate" || { echo "Failed to activate virtual env."; exit 1; }

    # Update pip, setuptools, and wheel
    echo "Updating pip, setuptools, and wheel..."
    if ! pip install --upgrade pip setuptools wheel -qqq; then
        echo "Failed to update libraries. Check your network connection and try again."
        exit 1
    fi
}

update_tfvars() {
  local tfvars_file="terraform.tfvars"

  # Loop through the passed arguments and append to the tfvars file
  for var in "$@"; do
    var_name="${var%%=*}"
    var_value="${var#*=}"

    if [[ "$var_name" == "proxies" ]]; then
      echo "${var_name}=${var_value}" >> "$tfvars_file"
    else
      echo "${var_name}=\"${var_value}\"" >> "$tfvars_file"
    fi
  done

}

# functions to validate the inputs
validate_proxies() {
  [[ "$1" == "{}" || "$1" =~ ^\{\s*\"http\":\s*\"http://[^\"]+\",\s*\"https\":\s*\"http://[^\"]+\"\s*\}$ ]]
}

validate_workspace_id() {
  [[ "$1" =~ ^[0-9]+$ ]]
}

validate_analysis_schema_name() {
  [[ "$1" =~ ^([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+|hive_metastore\.[a-zA-Z0-9_]+)$ ]]
}

validate_guid() {
    [[ "$1" =~ ^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$ && "${#1}" -eq 36 ]]
}

validate_client_secret() {
  [[ "${#1}" -eq 40 ]] || \
  [[ "${#1}" -eq 36 && "$1" == *dose* ]]
}

validate_databricks_url() {
    [[ "$1" =~ ^https://.*\.azuredatabricks\.net(/.*)?$ || \
       "$1" =~ ^https://.*\.cloud\.databricks\.com(/.*)?$ || \
       "$1" =~ ^https://.*\.gcp\.databricks\.com(/.*)?$ ]]
}

validate_gcp_sa() {
 [[ "$1" =~ ^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.iam\.gserviceaccount\.com$ ]]
}

validate_gcp_json_path() {
 [[ -f "$1" && "$1" == *.json ]]
}

# Prompt user for AWS inputs and validate
# shellcheck disable=SC2162
aws_validation() {
  local DATABRICKS_ACCOUNT_ID
  local DATABRICKS_CLIENT_ID
  local DATABRICKS_CLIENT_SECRET
  local DATABRICKS_URL
  local DATABRICKS_WORKSPACE_ID
  local ANALYSIS_SCHEMA_NAME
  local AWS_PROXIES

  clear

  cd aws || { echo "Failed to change directory to aws"; exit 1; }

  echo "================================================================="
  echo "Setting up AWS environment, Please provide the following details:"
  echo "================================================================="
  echo

  # Prompt user and validate inputs
   read -p "Enter Databricks Account ID: " DATABRICKS_ACCOUNT_ID
  while ! validate_guid "$DATABRICKS_ACCOUNT_ID"; do
    echo "Invalid Databricks Account ID."
    read -p "Enter Databricks Account ID: " DATABRICKS_ACCOUNT_ID
  done

  read -p "Enter Databricks Client ID: " DATABRICKS_CLIENT_ID
  while ! validate_guid "$DATABRICKS_CLIENT_ID"; do
    echo "Invalid Client ID."
    read -p "Enter Databricks Client ID: " DATABRICKS_CLIENT_ID
  done

  read -sp "Enter Databricks Client Secret: " DATABRICKS_CLIENT_SECRET
  while ! validate_client_secret "$DATABRICKS_CLIENT_SECRET"; do
    printf "\nInvalid Client Secret.\n"
    read -sp "Enter Databricks Client Secret: " DATABRICKS_CLIENT_SECRET
  done
  printf "\n"

  read -p "Enter Databricks URL: " DATABRICKS_URL
  while ! validate_databricks_url "$DATABRICKS_URL"; do
    echo "Invalid Databricks URL."
    read -p "Enter Databricks URL: " DATABRICKS_URL
  done

  read -p "Enter AWS Workspace ID: " DATABRICKS_WORKSPACE_ID
  while ! validate_workspace_id "$DATABRICKS_WORKSPACE_ID"; do
    echo "Invalid Workspace ID."
    read -p "Enter AWS Workspace ID: " DATABRICKS_WORKSPACE_ID
  done

  read -p "Enter Analysis Schema Name (e.g., 'catalog.schema' or 'hive_metastore.schema'): " ANALYSIS_SCHEMA_NAME
  while ! validate_analysis_schema_name "$ANALYSIS_SCHEMA_NAME"; do
      echo "Invalid Analysis Schema Name. It must be either 'catalog.schema' or 'hive_metastore.schema'."
      read -p "Enter Analysis Schema Name (e.g.,'catalog.schema' or 'hive_metastore.schema'): " ANALYSIS_SCHEMA_NAME
  done

  read -p "Enter Proxy Details ({} or JSON with 'http' and 'https' keys): " AWS_PROXIES
  while ! validate_proxies "$AWS_PROXIES"; do
    echo "Invalid Proxy format. Use '{}' or a valid JSON format like:"
    echo '{ "http": "http://proxy.example.com:8080", "https": "http://proxy.example.com:8080" }'
    read -p "Enter Proxy Details ({} or JSON with 'http' and 'https' keys): " AWS_PROXIES
  done

  # Set variables for AWS arguments
  AWS_VAR_ARGS=(
    "client_id=$DATABRICKS_CLIENT_ID"
    "client_secret=$DATABRICKS_CLIENT_SECRET"
    "account_console_id=$DATABRICKS_ACCOUNT_ID"
    "databricks_url=$DATABRICKS_URL"
    "workspace_id=$DATABRICKS_WORKSPACE_ID"
    "analysis_schema_name=$ANALYSIS_SCHEMA_NAME"
    "proxies=$AWS_PROXIES"
  )

  update_tfvars "${AWS_VAR_ARGS[@]}"
}

# Prompt user for Azure inputs and validate
# shellcheck disable=SC2162
azure_validation() {
  local AZURE_SUBSCRIPTION_ID
  local AZURE_TENANT_ID
  local AZURE_CLIENT_ID
  local AZURE_CLIENT_SECRET
  local DATABRICKS_ACCOUNT_ID
  local AZURE_DATABRICKS_URL
  local AZURE_WORKSPACE_ID
  local ANALYSIS_SCHEMA_NAME
  local AZURE_PROXIES

  clear

  cd azure || { echo "Failed to change directory to azure"; exit 1; }

  echo "==================================================================="
  echo "Setting up Azure environment, Please provide the following details:"
  echo "==================================================================="
  echo

  # Prompt user and validate inputs
  read -p "Enter Azure Subscription ID: " AZURE_SUBSCRIPTION_ID
  while ! validate_guid "$AZURE_SUBSCRIPTION_ID"; do
    echo "Invalid Subscription ID."
    read -p "Enter Azure Subscription ID: " AZURE_SUBSCRIPTION_ID
  done

  read -p "Enter Azure Tenant ID: " AZURE_TENANT_ID
  while ! validate_guid "$AZURE_TENANT_ID"; do
    echo "Invalid Tenant ID."
    read -p "Enter Azure Tenant ID: " AZURE_TENANT_ID
  done

  read -p "Enter Azure Client ID: " AZURE_CLIENT_ID
  while ! validate_guid "$AZURE_CLIENT_ID"; do
    echo "Invalid Client ID."
    read -p "Enter Azure Client ID: " AZURE_CLIENT_ID
  done

  read -sp "Enter Azure Client Secret: " AZURE_CLIENT_SECRET
  while ! validate_client_secret "$AZURE_CLIENT_SECRET"; do
    printf "\nInvalid Client Secret.\n"
    read -p "Enter Azure Client Secret: " AZURE_CLIENT_SECRET
  done
  printf "\n"

  read -p "Enter Databricks Account ID: " DATABRICKS_ACCOUNT_ID
  while ! validate_guid "$DATABRICKS_ACCOUNT_ID"; do
    echo "Invalid Databricks Account ID."
    read -p "Enter Databricks Account ID: " DATABRICKS_ACCOUNT_ID
  done

  read -p "Enter Databricks URL: " AZURE_DATABRICKS_URL
  while ! validate_databricks_url "$AZURE_DATABRICKS_URL"; do
    echo "Invalid Databricks URL."
    read -p "Enter Databricks URL: " AZURE_DATABRICKS_URL
  done

  read -p "Enter Azure Workspace ID: " AZURE_WORKSPACE_ID
  while ! validate_workspace_id "$AZURE_WORKSPACE_ID"; do
    echo "Invalid Workspace ID."
    read -p "Enter Azure Workspace ID: " AZURE_WORKSPACE_ID
  done

  read -p "Enter Analysis Schema Name (e.g., 'catalog.schema' or 'hive_metastore.schema'): " ANALYSIS_SCHEMA_NAME
  while ! validate_analysis_schema_name "$ANALYSIS_SCHEMA_NAME"; do
      echo "Invalid Analysis Schema Name. It must be either 'catalog.schema' or 'hive_metastore.schema'."
      read -p "Enter Analysis Schema Name (e.g.,'catalog.schema' or 'hive_metastore.schema'): " ANALYSIS_SCHEMA_NAME
  done

  read -p "Enter Proxy Details ({} or JSON with 'http' and 'https' keys): " AZURE_PROXIES
  while ! validate_proxies "$AZURE_PROXIES"; do
    echo "Invalid Proxy format. Use '{}' or a valid JSON format like:"
    echo '{ "http": "http://proxy.example.com:8080", "https": "http://proxy.example.com:8080" }'
    read -p "Enter Proxy Details ({} or JSON with 'http' and 'https' keys): " AZURE_PROXIES
  done

  # Set variables for Azure arguments
  AZURE_VAR_ARGS=(
    "subscription_id=$AZURE_SUBSCRIPTION_ID"
    "tenant_id=$AZURE_TENANT_ID"
    "client_id=$AZURE_CLIENT_ID"
    "client_secret=$AZURE_CLIENT_SECRET"
    "account_console_id=$DATABRICKS_ACCOUNT_ID"
    "databricks_url=$AZURE_DATABRICKS_URL"
    "workspace_id=$AZURE_WORKSPACE_ID"
    "analysis_schema_name=$ANALYSIS_SCHEMA_NAME"
    "proxies=$AZURE_PROXIES"
  )

  update_tfvars "${AZURE_VAR_ARGS[@]}"
}

# Prompt user for GCP inputs and validate
# shellcheck disable=SC2162
gcp_validation() {
  local DATABRICKS_ACCOUNT_ID
  local DATABRICKS_CLIENT_ID
  local DATABRICKS_CLIENT_SECRET
  local DATABRICKS_URL
  local DATABRICKS_WORKSPACE_ID
  local ANALYSIS_SCHEMA_NAME
  local GCP_PATH_TO_JSON
  local GCP_IMPERSONATE_SA
  local GCP_PROXIES

  clear

  cd gcp || { echo "Failed to change directory to gcp"; exit 1; }

  echo "================================================================="
  echo "Setting up GCP environment, Please provide the following details:"
  echo "================================================================="
  echo

  # Prompt user and validate inputs
  read -p "Enter Databricks Account ID: " DATABRICKS_ACCOUNT_ID
  while ! validate_guid "$DATABRICKS_ACCOUNT_ID"; do
    echo "Invalid Databricks Account ID."
    read -p "Enter Databricks Account ID: " DATABRICKS_ACCOUNT_ID
  done

  read -p "Enter Databricks Client ID: " DATABRICKS_CLIENT_ID
  while ! validate_guid "$DATABRICKS_CLIENT_ID"; do
    echo "Invalid Client ID."
    read -p "Enter Databricks Client ID: " DATABRICKS_CLIENT_ID
  done

  read -sp "Enter Databricks Client Secret: " DATABRICKS_CLIENT_SECRET
  while ! validate_client_secret "$DATABRICKS_CLIENT_SECRET"; do
    printf "\nInvalid Client Secret.\n"
    read -p "Enter Databricks Client Secret: " DATABRICKS_CLIENT_SECRET
  done
  printf "\n"

  read -p "Enter Databricks URL: " DATABRICKS_URL
  while ! validate_databricks_url "$DATABRICKS_URL"; do
    echo "Invalid Databricks URL."
    read -p "Enter Databricks URL: " DATABRICKS_URL
  done

  read -p "Enter GCP Workspace ID: " DATABRICKS_WORKSPACE_ID
  while ! validate_workspace_id "$DATABRICKS_WORKSPACE_ID"; do
    echo "Invalid Workspace ID."
    read -p "Enter GCP Workspace ID: " DATABRICKS_WORKSPACE_ID
  done

  read -p "Enter Analysis Schema Name (e.g., 'catalog.schema' or 'hive_metastore.schema'): " ANALYSIS_SCHEMA_NAME
  while ! validate_analysis_schema_name "$ANALYSIS_SCHEMA_NAME"; do
      echo "Invalid Analysis Schema Name. It must be either 'catalog.schema' or 'hive_metastore.schema'."
      read -p "Enter Analysis Schema Name (e.g.,'catalog.schema' or 'hive_metastore.schema'): " ANALYSIS_SCHEMA_NAME
  done

  read -p "Enter GCP Key json path: " GCP_PATH_TO_JSON
  while ! validate_gcp_json_path "$GCP_PATH_TO_JSON"; do
    echo "Invalid Path."
    read -p "Enter GCP Key json path: " GCP_PATH_TO_JSON
  done

  read -p "Enter GCP Impersonate Service Account: " GCP_IMPERSONATE_SA
  while ! validate_gcp_sa "$GCP_IMPERSONATE_SA"; do
    echo "Invalid Service Account."
    read -p "Enter GCP Impersonate Service Account: " GCP_IMPERSONATE_SA
  done

  read -p "Enter Proxy Details ({} or JSON with 'http' and 'https' keys): " AWS_PROXIES
  while ! validate_proxies "$AWS_PROXIES"; do
    echo "Invalid Proxy format. Use '{}' or a valid JSON format like:"
    echo '{ "http": "http://proxy.example.com:8080", "https": "http://proxy.example.com:8080" }'
    read -p "Enter Proxy Details ({} or JSON with 'http' and 'https' keys): " AWS_PROXIES
  done

  # Set variables for GCP arguments
  GCP_VAR_ARGS=(
    "client_id=$DATABRICKS_CLIENT_ID"
    "client_secret=$DATABRICKS_CLIENT_SECRET"
    "account_console_id=$DATABRICKS_ACCOUNT_ID"
    "databricks_url=$DATABRICKS_URL"
    "workspace_id=$DATABRICKS_WORKSPACE_ID"
    "analysis_schema_name=$ANALYSIS_SCHEMA_NAME"
    "gs_path_to_json=$GCP_PATH_TO_JSON"
    "impersonate_service_account=$GCP_IMPERSONATE_SA"
    "proxies=$GCP_PROXIES"
  )

  update_tfvars "${GCP_VAR_ARGS[@]}"
}

# shellcheck disable=SC2120
terraform_actions() {
  clear

  PLAN_FILE="tfplan"
  COMMON_ARGS=(
      -no-color
      -input=false
  )

  # Execute Terraform commands
  case $1 in
    "aws")
      aws_validation
      ;;
    "azure")
      azure_validation
      ;;
    "gcp")
      gcp_validation
      ;;
    *)
      echo "Invalid option."
      ;;
  esac

  terraform init "${COMMON_ARGS[@]}" || { echo "Failed to initialize Terraform."; exit 1; }
  terraform plan -out="$PLAN_FILE" "${COMMON_ARGS[@]}" || { echo "Failed to create a Terraform plan."; exit 1; }
  terraform apply -auto-approve "$PLAN_FILE" || { echo "Failed to apply the Terraform plan."; exit 1; }
}

terraform_install(){
  clear

  cd terraform || { echo "Failed to change directory to terraform"; exit 1; }
  options=("AWS" "Azure" "GCP" "Quit")
  echo "========================="
  echo "Please select your cloud:"
  echo "========================="
  echo
  select opt in "${options[@]}"
  do
    case $opt in
      "AWS")
        terraform_actions "aws"
        ;;
      "Azure")
        terraform_actions "azure"
        ;;
      "GCP")
        terraform_actions "gcp"
        ;;
      "Quit")
        echo "Exiting SAT Installation..."
        break
        ;;
      *)
        echo "Invalid option."
        ;;
    esac
  done
}

shell_install(){
  clear

  cd dabs || { echo "Failed to change directory to dabs"; exit 1; }
  setup_env || { echo "Failed to setup virtual environment."; exit 1; }

  echo "Installing SAT dependencies..."
  pip install -r requirements.txt -qqq || { echo "Failed to install Python dependencies."; exit 1; }
  python main.py || { echo "Failed to run the main script."; exit 1; }
}

uninstall() {
  local tfplan_path bundle_path

  # Find a file named "tfplan" and get its root directory
  tfplan_path=$(find . -type f -name "tfplan" -exec dirname {} \; | head -n 1)

  if [[ -n "$tfplan_path" ]]; then
    # If a tfplan file is found
    cd "$tfplan_path" || { echo "Failed to change directory to $tfplan_path"; exit 1; }
    clear
    echo "Uninstalling Terraform resources..."
    terraform destroy -auto-approve -lock=false || { echo "Failed to destroy the Terraform resources."; exit 1; }

    # Remove Terraform files
    terraform_files=(
      ".terraform"
      ".terraform.lock.hcl"
      ".terraform.tfstate.lock.info"
      "terraform.tfstate"
      "terraform.tfstate.backup"
      "terraform.tfvars"
      "crash.log"
      ".terraform.rc"
      "terraform.rc"
      "tfplan"
    )
    for item in "${terraform_files[@]}"; do
      rm -rf "$item"
    done
  fi

  # If no tfplan file is found, search for a folder named ".databricks"
  bundle_path=$(find . -type d -name ".databricks" | head -n 1)

  if [[ -n "$bundle_path" ]]; then
    # If a .databricks folder is found

    # shellcheck disable=SC2015
    cd "$bundle_path" && cd .. || { echo "Failed to change directory to $bundle_path"; exit 1; }

    # shellcheck disable=SC2207
    options=($(databricks auth profiles | awk 'NR > 1 {print $1}'))

    echo "========================================"
    echo "Select the Profile used to installed SAT"
    echo "========================================"
    echo

    select opt in "${options[@]}"
    do
      if [[ -n "$opt" ]]; then
        selected_profile="$opt"
        clear
        echo "Uninstalling Databricks resources"
        databricks bundle destroy --auto-approve --force-lock -p "$selected_profile" || {
          echo "Failed to destroy the Databricks resources. Please check the confirm you are using the correct Profile."
          exit 1
        }
        cd ../ && rm -rf tmp .env
        break
      else
        echo "Invalid option. Select an option from 1 to ${#options[@]}."
      fi
    done
  fi

  echo "SAT successfully uninstalled."
}

install_sat(){

  if [[ "$RUNNING_MODE" == "remote" ]]; then
    get_github_project || { echo "Failed to setup SAT."; exit 1; }
  fi

  clear

  options=("Terraform" "CLI")
  echo "==============================="
  echo "How do you want to install SAT?"
  echo "==============================="
  echo

  if [[ $SAT_INSTALLED -eq 1 ]]; then
    options=("Terraform" "CLI" "Uninstall")
  fi

  select opt in "${options[@]}"
  do
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
        if [[ $SAT_INSTALLED -eq 1 ]]; then
          uninstall || { echo "Failed to uninstall SAT."; exit 1; }
        else
          echo "Uninstall option is not available."
        fi
        break
        ;;
      *)
        echo "Invalid option."
        ;;
    esac
  done
}

main(){
    running_mode || { echo "Failed to determine the running mode."; exit 1; }
    running_location || { echo "Failed to determine the running location."; exit 1; }
    is_sat_installed || { echo "Failed to determine if SAT is installed."; exit 1; }
    install_sat || { echo "Failed to install SAT."; exit 1; }
}

# run script
main
