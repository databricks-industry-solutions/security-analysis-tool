## Project Versioning Guide

This document provides a comprehensive guide to versioning for our project, using the `x.x.x` format, also known as **Semantic Versioning**. All pull requests will be merged into the latest version branches.

### **Semantic Versioning (SemVer)**

Semantic Versioning is a versioning scheme that uses three numbers separated by dots: `MAJOR.MINOR.PATCH`. Each number has a specific meaning:

#### **Version Number Breakdown**

- **MAJOR**: Changes when you make incompatible API changes. Like changes in the source code or the way SAT is being deployed.
- **MINOR**: Changes when you add functionality in a backward-compatible manner. New functions, new checks.
- **PATCH**: Changes when you make backward-compatible bug fixes. Documentation, code fixes.

For example, version `2.1.3` indicates:
- `2`: Major version, which includes significant changes that may not be backward-compatible.
- `1`: Minor version, which includes new features that are backward-compatible.
- `3`: Patch version, which includes backward-compatible bug fixes.

### **Branching Strategy**

All pull requests will be merged into branches that correspond to the latest version. This ensures that the main branch always reflects the most current stable version of the project.

#### **Branch Naming Convention**

- **Feature Branches**: `feature/description`
- **Bugfix Branches**: `bugfix/description`
- **Release Branches**: `release/x.x.x`
- **Hotfix Branches**: `hotfix/x.x.x`

### **Versioning Workflow**

1. **Initial Release**:
    - Start with version `1.0.0`.
    - Create a `release/1.0.0` branch from the main branch.
    - Merge all initial features and fixes into this branch.

2. **Feature Addition**:
    - Create a new branch from the main branch: `feature/description`.
    - Implement the feature and create a pull request.
    - Merge the pull request into the latest release branch (e.g., `release/1.1.0`).

3. **Bug Fixing**:
    - Create a new branch from the main branch: `bugfix/description`.
    - Implement the fix and create a pull request.
    - Merge the pull request into the latest release branch (e.g., `release/1.0.1`).

4. **Releasing a New Version**:
    - Once all features and bug fixes are merged, update the version number in the `release` branch.
    - Merge the `release` branch into the main branch.
    - Tag the new version in the repository.

### **Best Practices**

- **Release Schedule**: Publish a release schedule to keep users informed about upcoming updates.
- **Documentation**: Document each version change, including new features, bug fixes, and any breaking changes.

By adhering to these guidelines, we ensure a structured and predictable release process, making it easier for users to understand and adopt new versions of our software.