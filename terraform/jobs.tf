resource "databricks_job" "initializer" {
  name = "Execute Initializer Notebook (one-time)"
  new_cluster {
    num_workers   = 5
    spark_version = data.databricks_spark_version.latest_lts.id
    node_type_id  = data.databricks_node_type.smallest.id
    runtime_engine = "PHOTON"
  }

  library {
    pypi {
      package = "dbl-sat-sdk"
    }
  }

  notebook_task {
    notebook_path   = "/Repos/${data.databricks_current_user.me.user_name}/security-analysis-tool.git/notebooks/security_analysis_initializer"
  }

}

resource "databricks_job" "driver" {
  name = "Execute Driver Notebook"
  new_cluster {
    num_workers   = 5
    spark_version = data.databricks_spark_version.latest_lts.id
    node_type_id  = data.databricks_node_type.smallest.id
    runtime_engine = "PHOTON"
  }

  library {
    pypi {
      package = "dbl-sat-sdk"
    }
  }

  notebook_task {
    notebook_path = "/Repos/${data.databricks_current_user.me.user_name}/security-analysis-tool.git/notebooks/security_analysis_driver"
  }

  schedule {
    #E.G. At 08:00:00am, on every Monday, Wednesday and Friday, every month; For more: http://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html
    quartz_cron_expression = "0 0 8 ? * Mon,Wed,Fri"
    # The system default is UTC; For more: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
    timezone_id = "America/New_York"
  }
}