#!/usr/bin/env python
# encoding: UTF-8

import argparse
import datetime
import logging
import sched
import sys
import time

from cloudhands.burst.agents import supply_nodes_to_requested_hosts
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.fsm import HostState

__doc__ = """
"""

DFLT_DB = ":memory:"


class Operation(object):

    def __init__(self, schdlr):
        self.schdlr = schdlr
        self.shots = 10

    def __call__(self, shot):
        log = logging.getLogger("cloudhands.burst")
        log.info("Shot nr: {}".format(shot))
        if self.shots:
            self.shots -= 1
            job = self.schdlr.enter(5, 0, self, (self.shots,))

def main(args):
    rv = 1
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s|%(message)s")

    session = Registry().connect(sqlite3, args.db).session
    initialise(session)
    transitions = {
        HostState: [supply_nodes_to_requested_hosts]
    }
    s = sched.scheduler(time.time, time.sleep)
    op = Operation(s)
    op(op.shots)
    s.run()
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
