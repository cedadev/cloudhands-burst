#!/usr/bin/env python
# encoding: UTF-8

import argparse
import concurrent.futures
from configparser import ConfigParser
import datetime
import logging
import sqlite3
import sys

import cloudhands.burst.main

from cloudhands.burst.agents import supply_nodes_to_requested_hosts
from cloudhands.burst.test.fixtures import BurstFixture
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.web.test.fixtures import WebFixture

__doc__ = """
Back end demo
"""

DFLT_DB = ":memory:"


def main(args):
    rv = 1
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s|%(message)s")
    log = logging.getLogger("cloudhands.burst.demo")

    session = Registry().connect(sqlite3, args.db).session
    initialise(session)
    WebFixture.create_organisations(session)
    user = WebFixture.grant_user_membership(session)
    WebFixture.load_hosts_for_user(session, user)
    supply_nodes_to_requested_hosts(session)
    return rv


def parser(description=__doc__):
    rv = cloudhands.burst.main.parser(description)
    return rv


def run():
    p = parser()
    args = p.parse_args()
    rv = main(args)
    sys.exit(rv)

if __name__ == "__main__":
    run()
