'''setup file for wheel'''
from io import open
from os import path
from setuptools import setup

DESCRIPTION = "Databricks Security Analysis Tool"

__version__ = "0.1.14"

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, "README.md"), encoding="utf-8") as f:
    LONG_DESCRIPTION = f.read()

VERSION = __version__

setup(
    name="dbl-sat-sdk",
    version=VERSION,
    packages=[
        "clientpkgs", "core",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests"
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: Other/Proprietary License',
        'Operating System :: OS Independent',
    ],
    author="Arun Pamulapati, Anindita Mahapatra, Ram Murali",
    author_email="labs@databricks.com",
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="https://databricks.com/learn/labs",
    license="https://github.com/databrickslabs/profile/blob/master/LICENSE"
)





# import setuptools

# with open("README.md", "r") as fh:
#     long_description = fh.read()

# setuptools.setup(
#     name="dbr-profiler-tool",
#     version="0.4.2",
#     author="RKMurali",
#     author_email="ramdas.murali@databricks.com",
#     description="Databricks Profiling Tool",
#     long_description=long_description,
#     long_description_content_type="text/markdown",
#     url="https://github.com/databrickslabs/yoohoo",
#     license="https://github.com/databrickslabs/profile/blob/master/LICENSE",
#     packages=["clientpkgs", "core"],
#     install_requires=[
#           'requests'
#       ],
#     classifiers=[
#         "Programming Language :: Python :: 3",
#         "Operating System :: OS Independent",
#     ],
#     python_requires='>=3.6'
# )
