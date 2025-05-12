"""setup file for wheel"""

from io import open
from os import path

from setuptools import setup

DESCRIPTION = "Databricks Security Analysis Tool"

# testing 0.0.102
# main 0.1.37

__version__ = "0.0.102"  # "0.1.37" #0.0.102

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, "README.md"), encoding="utf-8") as f:
    LONG_DESCRIPTION = f.read()


def read_text(file_name: str):
    v = open(path.join(this_directory, "../..", file_name), encoding="utf-8").read()
    print(v)


VERSION = __version__

setup(
    name="dbl-sat-sdk",
    version=VERSION,
    packages=[
        "clientpkgs",
        "core",
    ],
    python_requires=">=3.8",
    install_requires=["requests", "msal"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
    ],
    author="Arun Pamulapati, Anindita Mahapatra, Ram Murali",
    author_email="sat@databricks.com",
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="https://databricks.com/learn/labs",
)
