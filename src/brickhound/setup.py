"""
Permissions Analysis Tool setup configuration
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="brickhound",
    version="0.1.0",
    author="Arun Pamulapati",
    author_email="arun.pamulapati@example.com",
    description="Security analysis tool for Databricks environments",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/arunpamulapati/BrickHound",
    packages=find_packages(exclude=["tests", "notebooks"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Information Technology",
        "Intended Audience :: System Administrators",
        "Topic :: Security",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=[
        "databricks-sdk>=0.18.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "networkx>=3.1",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
        "click>=8.1.0",
        "tqdm>=4.65.0",
    ],
    extras_require={
        "viz": [
            "plotly>=5.14.0",
            "matplotlib>=3.7.0",
            "seaborn>=0.12.0",
            "pyvis>=0.3.0",
        ],
        "dev": [
            "pytest>=7.3.0",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.11.0",
            "black>=23.3.0",
            "flake8>=6.0.0",
            "mypy>=1.3.0",
        ],
        "docs": [
            "mkdocs>=1.4.0",
            "mkdocs-material>=9.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "brickhound=brickhound.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "brickhound": ["*.yaml", "*.json"],
    },
)

