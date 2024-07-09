import pytest
import os
import subprocess


def run_databricks_job(client, job_id):
    """
    Function to run a Databricks job and wait for its completion.
    """
    run = client.jobs.run_now(job_id=job_id).result()
    run_id = run.run_id

    # Wait for the job to complete
    while True:
        run_status = client.jobs.get_run(run_id=run_id)
        state = run_status.state.result_state.value
        if state == "SUCCESS":
            break
        elif state == "FAILED":
            break
    return state


def terraform_outputs():
    tf_output_vars = ["initializer_job_id", "driver_job_id"]
    output = []
    try:
        # Run the terraform command
        root_dir = os.environ.get("ROOT_DIR")
        terraform_dir = os.environ.get("TERRAFORM_DIR")

        if terraform_dir:
            os.chdir(f"{root_dir}/{terraform_dir}")

        for tf_output_var in tf_output_vars:
            result = subprocess.run(
                ["terraform", "output", "-raw", tf_output_var],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            output.append(result.stdout.strip())
        
        # swith back to the root directory
        if root_dir: 
            os.chdir(root_dir)

        return output
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running terraform: {e.stderr}")
        return None


job_ids = terraform_outputs()


# ------------------------------ TESTS ------------------------------
@pytest.mark.parametrize("job_id", job_ids)
def test_databricks_job_runs(logger, databricks_client, job_id):
    # Run the Databricks initializer job
    job_status = run_databricks_job(databricks_client, job_id)
    assert job_status == "SUCCESS"