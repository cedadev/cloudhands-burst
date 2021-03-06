#!/usr/bin/env python
# encoding: UTF-8

import ast
from setuptools import setup
import os.path


try:
    import cloudhands.burst.__version__ as version
except ImportError:
    # Pip evals this file prior to running setup.
    # This causes ImportError in a fresh virtualenv.
    version = str(ast.literal_eval(
                open(os.path.join(os.path.dirname(__file__),
                "cloudhands", "burst", "__init__.py"),
                'r').read().split("=")[-1].strip()))

__doc__ = open(os.path.join(os.path.dirname(__file__), "README.rst"),
               "r").read()

setup(
    name="cloudhands-burst",
    version=version,
    description="Cross-cloud bursting for cloudhands PaaS",
    author="D Haynes",
    author_email="david.e.haynes@stfc.ac.uk",
    url="https://github.com/cedadev/cloudhands-burst.git",
    long_description=__doc__,
    classifiers=[
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License"
    ],
    namespace_packages=["cloudhands"],
    packages=[
        "cloudhands.burst",
        "cloudhands.burst.drivers",
        "cloudhands.burst.drivers.test",
        "cloudhands.burst.test"
        ],
    package_data={
        "cloudhands.burst": [],
        "cloudhands.burst.drivers": [
            "*.pt",
        ],
        "cloudhands.burst.drivers.test": [
            "*.xml",
        ],
        "cloudhands.burst.test": [],
        },
    install_requires=[
        "cloudhands-common>=0.32",
        "aiohttp>=0.8.2",
        "apache-libcloud>=0.13.0",
        "Chameleon>=2.14",
        ],
    entry_points={
        "console_scripts": [
            "cloud-burst=cloudhands.burst.main:run",
        ],
    },
    zip_safe=False
)
