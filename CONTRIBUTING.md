# Contributing to Security Analysis Tool (SAT)

Thank you for your interest in contributing to the Databricks Security Analysis Tool! We welcome contributions from the community, and we accept PRs pursuant to a CLA.

## Getting Started

Before you begin:

1. **Check existing issues**: Look through [GitHub Issues](https://github.com/databricks-industry-solutions/security-analysis-tool/issues) to see if your bug report or feature request already exists
2. **Read the documentation**: Familiarize yourself with [SAT Documentation](https://databricks-industry-solutions.github.io/security-analysis-tool/)
3. **Understand the project structure**: Review the codebase organization

### Project Structure

```
security-analysis-tool/
├── src/                           # Python SDK source code
│   ├── securityanalysistoolproject/  # Main SAT SDK
│   └── brickhound/                # Permissions & Resources Analysis
├── notebooks/                     # Databricks notebooks
│   ├── Setup/                     # Installation and configuration
│   ├── Includes/                  # Helper modules
│   └── brickhound/               # Permissions & Resources Analysis notebooks
├── app/brickhound/               # Permissions & Resources Analysis web UI
├── terraform/                    # Infrastructure as Code SAT Installation
├── dabs/                        # Databricks Asset Bundles SAT Installation
├── configs/                     # Configuration files
├── dashboards/                  # AI/BI dashboard
└── docs/                        # Documentation site
```

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Access to a Databricks workspace (for testing)
- Git

### Local Setup

1. **Clone the repository**:
```bash
git clone https://github.com/databricks-industry-solutions/security-analysis-tool.git
cd security-analysis-tool
```

2. **Set up Python environment**:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install SDK in development mode
cd src/securityanalysistoolproject
pip install -e .
```

3. **Install development dependencies**:
```bash
pip install pytest
```

## How to Contribute

### Types of Contributions

We welcome:

1. **Bug Fixes** - Fix issues in existing code
2. **New Features** - Add new security checks or analysis capabilities
3. **Documentation** - Improve or add documentation
4. **Testing** - Add or improve test coverage

### Reporting Bugs

When reporting bugs, please include:

- Clear description of what happened vs. what you expected
- Steps to reproduce the issue
- Environment details (Databricks runtime, cloud provider, SAT version)
- Error messages and stack traces
- Screenshots if applicable

**Security vulnerabilities** should be reported to `bugbounty@databricks.com` (see [SECURITY.md](SECURITY.md))

### Suggesting Features

When suggesting features, explain:

- The use case and why it would be useful
- How you envision it working
- Who would benefit from it

## Pull Request Process

### Branch Naming

Use descriptive branch names:
- `feature/add-azure-security-check`
- `bugfix/fix-aws-credential-scan`
- `docs/update-installation-guide`

### Submitting a Pull Request

1. **Fork the repository** and create your branch from `main`:
```bash
git checkout -b feature/your-feature-name
```

2. **Make your changes**:
   - Write clear, readable code
   - Add tests for new functionality
   - Update documentation as needed

3. **Commit your changes**:
```bash
git commit -m "Add new Azure security check for Key Vault

- Added check for Key Vault soft delete
- Added unit tests
- Updated documentation"
```

4. **Push to your fork** and open a Pull Request with a clear description

### Commit Message Format

Use clear, descriptive commit messages:

- `feat: add new feature`
- `fix: resolve bug`
- `docs: update documentation`
- `test: add tests`

### Pull Request Review

- At least one maintainer must approve the PR
- All tests must pass
- Documentation must be updated if needed

## Testing

Run tests before submitting:

```bash
cd src/securityanalysistoolproject
pytest
```

## Documentation

### Updating Documentation

When making changes:

1. Update inline documentation (docstrings)
2. Update user-facing docs in `docs/sat/docs/` if needed
3. Update README if necessary
4. Update CHANGELOG.md

### Preview Documentation

```bash
cd docs/sat
npm install
npm start
```

## Versioning

SAT follows **Semantic Versioning** (SemVer): `MAJOR.MINOR.PATCH`

- **MAJOR**: Incompatible API changes
- **MINOR**: New features (backward-compatible)
- **PATCH**: Bug fixes (backward-compatible)

See [VERSIONING.md](VERSIONING.md) for detailed guidelines.

### Branch Strategy

- `main`: Stable production releases
- `release/x.x.x`: Release preparation branches
- `feature/*`: New features
- `bugfix/*`: Bug fixes

## Code Style

- Follow PEP 8 conventions
- Use meaningful variable and function names
- Add docstrings to public functions
- Handle errors appropriately
- Don't commit sensitive data (credentials, tokens, etc.)

## License and CLA

By contributing to this project, you agree to the Contributor License Agreement (CLA). All pull requests require CLA acceptance before merging.

This project is licensed under the Databricks License. See [LICENSE](LICENSE) for details.

## Getting Help

- **Documentation**: https://databricks-industry-solutions.github.io/security-analysis-tool/
- **GitHub Issues**: For bug reports and feature requests
- **Security Issues**: bugbounty@databricks.com

## Recognition

Contributors are recognized in release notes and CHANGELOG.md.

Thank you for contributing to SAT! 🔒
