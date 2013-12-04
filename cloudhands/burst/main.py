#!/usr/bin/env python
# encoding: UTF-8

import argparse
import datetime
import logging
import sched
import sys
import time

from cloudhands.burst.host import HostAgent
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.fsm import HostState

__doc__ = """
"""

DFLT_DB = ":memory:"


def operate(session):
    for n, i in enumerate(HostAgent.touch_requested(session)):
        print(n, i)


def main(args):
    rv = 1
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s|%(message)s")

    session = Registry().connect(sqlite3, args.db).session
    initialise(session)
    operate(session)
    return rv


def parser(descr=__doc__):
    rv = argparse.ArgumentParser(description=descr)
    rv.add_argument(
        "--version", action="store_true", default=False,
        help="Print the current version number")
    rv.add_argument(
        "-v", "--verbose", required=False,
        action="store_const", dest="log_level",
        const=logging.DEBUG, default=logging.INFO,
        help="Increase the verbosity of output")
    rv.add_argument(
        "--db", default=DFLT_DB,
        help="Set the path to the database [{}]".format(DFLT_DB))

    return rv


def run():
    p = parser()
    args = p.parse_args()
    rv = main(args)
    sys.exit(rv)

if __name__ == "__main__":
    run()
