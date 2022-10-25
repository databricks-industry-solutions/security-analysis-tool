
# Security Analysis Tool (SAT) 
<img src="./images/sat_icon.jpg" width="10%" height="10%">


## Introduction

Security Analysis Tool (SAT) analyzes customer's Databricks account and workspace security configurations and provides recommendations that help them follow Databrick's security best practices. When a customer runs SAT, it will compare their workspace configurations against a set of security best practices and delivers a report for their Databricks AWS workspace (Azure, GCP coming soon). These checks identify recommendations to harden Databricks configurations, services, and resources.

Databricks has worked with thousands of customers to securely deploy the Databricks platform, with the appropriate security features that meet their architecture requirements. While many organizations deploy security differently, there are guidelines and features that are commonly used by organizations that need a high level of security. This tool checks for typical security features that are deployed by most high-security organizations, and reviews the largest risks and the risks that customers ask about most often. It will then provide a security configuration reference link to Databricks documentation along with a recommendation. 

## Functionality
Security Analysis Tool (SAT) is an observability tool that aims to improve the security hardening of Databricks deployments by making customers aware of deviations from established security best practices by helping customers monitor the security health of Databricks account workspaces easily. There is a need for a master checklist that prioritizes the checks by severity and running this as a routine scan for all the workspaces helps ensure continuous adherence to best practices. This also helps to build confidence to onboard sensitive datasets.


![SAT Functionality](./images/sat_functionality.png)

SAT is typically run daily as an automated workflow in the customers account that collects details on various settings via REST APIs. The details of these check results are persisted in Delta tables in customer storage so that trends can be analyzed over time. These results are displayed in a centralized Databricks SQL dashboard and are broadly categorized into five distinct sections for others in the organizationorganizaation to view their respective workspace settings. It also provides links to the latest public documentation on how to configure correctly which helps customers educate on Databricks security in tiny increments feature by feature. Forewarned is Forearmed!. Alerts can be configured on critical checks to provide notifications to concerned stakeholders. It also provides additional details on individual checks that fail so that an admin persona can pinpoint and isolate the issue and remediate it quickly.

## SAT Insights

Data across any of the configured workspaces can be surfaced through a single pane of SQL Dashboard which is the primary consumption layer where all the insights are arranged in well defined categories namely: 
* Network Security
* Identity & Access
* Data Protection 
* Governance  
* Informational 

The data in each section is further categorizedcatgorized by severity namely: High, Medium, Low.

![SAT Insights](./images/sat_dashboard_partial.png)

The dashboard is broken into the five sections and each pillar is laid out in a consistent format.

* Workspace Security Summary
    * The high-level summary calls out findings by category, categorized by severity.
* Workspace Stats
    * This section provides usage statistics around the number of users, groups, databases, tables, and service details like tier and region.
* Individual Security Category Details
    * A section for each security category that contains:
      * Security section summary details, such as counts of deviations from recommended best practices
      * A table with security finding details for the security category, sorted by severity. The table describes each security violation and provides  links to documentation that help to fix the finding.

*  Informational Section
    * These are less prescriptive in nature but provide data points that can be scrutinized by data personas to verify thresholds are set correctly for their organization.
* Additional Finding Details
    * This section provides additional details that help to pinpoint the source of a security deviation, including the logic used to detect them. For example, the 'cluster policy not used' will provide a list of the cluster workloads where the policy is not applied, avoiding a needle-in-a-haystack situation.

## Detection example

Security Analysis Tool (SAT) analyzes 37 best practices, with more on the way. In the example below, the SAT scan highlights one finding that surfaces a potential risk, and one that meets Databricks' best practices. The Deprecated runtime versions check is red indicating that there are runtimes that are deprecated. Workloads on unsupported runtime versions may continue to run, but they receive no Databricks support or fixes. The Remediation column in the screenshot describes the risk and links to the documentation of the Databricks runtime versions that are currently supported. 

On the other hand, the Log delivery check is green, confirming that the workspace follows Databricks security best practices. Run these checks regularly to comprehensively view Databricks account workspace security and ensure continuous improvement.

![SAT Insights](./images/sat_detection_partial.png)

Customers can use the "Additional Details" section to display information on what configuration setting or control failed a specific best practice rule. For example, the image below showcases additional details on the "Deprecated runtime versions" risk for administrators to investigate. 

![SAT Insights](./images/additional_details_1.png)

In the example below, the customer can know more about the “Log delivery” by inputting “GOV-3”. 

![SAT Insights](./images/additional_details_2.png)

## Configuration and Usage instructions
Refer to [setup guide](./docs/setup.md)  

## Project support 

Please note that all projects in the /databrickslabs github account are provided for your exploration only, and are not formally supported by Databricks with Service Level Agreements (SLAs). They are provided AS-IS and we do not make any guarantees of any kind. Please do not submit a support ticket relating to any issues arising from the use of these projects.

Any issues discovered through the use of this project should be filed as GitHub Issues on the Repo. They will be reviewed as time permits, but there are no formal SLAs for support. 
