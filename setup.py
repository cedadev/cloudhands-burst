#!/usr/bin/env python
# encoding: UTF-8

from setuptools import setup
import os.path

import cloudhands.burst

__doc__ = open(os.path.join(os.path.dirname(__file__), "README.rst"),
               "r").read()

setup(
    name="cloudhands-burst",
    version=cloudhands.burst.__version__,
    description="Cross-cloud bursting for cloudhands PaaS",
    author="D Haynes",
    author_email="david.e.haynes@stfc.ac.uk",
    url="http://pypi.python.org/pypi/cloudhands-burst",
    long_description=__doc__,
    classifiers=[
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License"
    ],
    namespace_packages=["cloudhands"],
    packages=["cloudhands.burst"],
    package_data={"cloudhands.burst": []},
    install_requires=[
        "cloudhands-common>=0.02",
        "apache-libcloud>=0.13.0",
        ],
    entry_points={
        "console_scripts": [
            "burst=cloudhands.burst.main:run",
            "cloud-demoburst=cloudhands.burst.demo:run",
        ],
    },
    zip_safe=False
)
