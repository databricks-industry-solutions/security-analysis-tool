import pytest
import os
import subprocess
import json

def set_terraform_dir(path):
    os.environ['TERRAFORM_DIR'] = path

def get_terraform_output(tf_output_var):
    try:
        # Run the terraform command
        root_dir = os.environ.get('GITHUB_ACTION_PATH')
        terraform_dir = os.environ.get('TERRAFORM_DIR')


        if terraform_dir:
            os.chdir(f"{root_dir}/{terraform_dir}")

        result = subprocess.run(
            ["terraform", "output", "-raw", tf_output_var],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        output = result.stdout.strip()
        return output
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running terraform: {e.stderr}")
        return None

def run_databricks_job(tf_output_var):
    job_id = get_terraform_output(tf_output_var)
    try:
        # Run the databricks command
        result = subprocess.run(
            ["databricks", "jobs", "run-now", job_id],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        json_output = result.stdout.strip()
        return json.loads(json_output)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running the databricks job: {e.stderr}")
        return None
    
def check_job_status(json_output):
    if "Error" in json.dumps(json_output):
        return "FAILED"
    
    result_state = json_output.get("state", {}).get("result_state")
    if result_state == "SUCCESS":
        return "SUCCESS"
    else:
        return "FAILED"

# ------------------------------ TESTS ------------------------------
def test_databricks_initializer_job_run(logger):
    # Run the Databricks initializer job
    job_output = run_databricks_job("initializer_job_id")
    job_status = check_job_status(job_output)
    assert job_status == "SUCCESS"

def test_databricks_driver_job_run(logger):
    # Run the Databricks driver job
    job_output = run_databricks_job("driver_job_id")
    job_status = check_job_status(job_output)
    assert job_status == "SUCCESS"