#!/usr/bin/env python
# encoding: UTF-8

import argparse
import datetime
import logging
from logging.handlers import WatchedFileHandler
import sched
import sqlite3
import sys
import time

from cloudhands.burst.host import HostAgent
from cloudhands.burst.subscription import SubscriptionAgent
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.discovery import settings
from cloudhands.common.fsm import HostState

__doc__ = """
This process performs tasks to administer hosts in the JASMIN cloud.

It makes state changes to Host artifacts in the JASMIN database. It
operates in a round-robin loop with a specified interval.
"""

DFLT_DB = ":memory:"


def hosts_deleting(args, session, loop=None):
    log = logging.getLogger("cloudhands.burst.hosts_deleting")
    for act in enumerate(HostAgent.touch_deleting(session)):
        log.debug(act)

    if loop is not None:
        log.debug("Rescheduling {}s later".format(args.interval))
        loop.enter(args.interval, 0, hosts_deleting, (args, session, loop))


def hosts_requested(args, session, loop=None):
    log = logging.getLogger("cloudhands.burst.hosts_requested")
    for act in enumerate(HostAgent.touch_requested(session)):
        log.debug(act)

    if loop is not None:
        log.debug("Rescheduling {}s later".format(args.interval))
        loop.enter(args.interval, 0, hosts_requested, (args, session, loop))


# TODO: refactor to singleton pattern like identity controller
def subscriptions_unchecked(args, session, loop=None):
    log = logging.getLogger("cloudhands.burst.subscriptions_unchecked")
    for act in enumerate(SubscriptionAgent.touch_unchecked(session)):
        log.debug(act)

    if loop is not None:
        log.debug("Rescheduling {}s later".format(args.interval))
        loop.enter(
            args.interval, 0, subscriptions_unchecked,
            (args, session, loop))


def main(args):
    rv = 1
    log = logging.getLogger("cloudhands.burst")
    log.setLevel(args.log_level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s|%(message)s")
    ch = logging.StreamHandler()

    if args.log_path is None:
        ch.setLevel(args.log_level)
    else:
        fh = WatchedFileHandler(args.log_path)
        fh.setLevel(args.log_level)
        fh.setFormatter(formatter)
        log.addHandler(fh)
        ch.setLevel(logging.WARNING)

    ch.setFormatter(formatter)
    log.addHandler(ch)

    portalName, config = next(iter(settings.items()))
    session = Registry().connect(sqlite3, args.db).session
    initialise(session)

    loop = sched.scheduler()
    ops = (
        hosts_deleting,
        hosts_requested,
        subscriptions_unchecked)
    if args.interval is None:
        for op in ops:
            op(args, session)
        return 0
    else:
        d = max(1, args.interval // len(ops))
        for n, op in enumerate(ops):
            loop.enter(args.interval, n, op, (args, session, loop))
            time.sleep(d)
        loop.run()
        return 1

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
    rv.add_argument(
        "--interval", default=None, type=int,
        help="Set the indexing interval (s)")
    rv.add_argument(
        "--log", default=None, dest="log_path",
        help="Set a file path for log output")
    return rv


def run():
    p = parser()
    args = p.parse_args()
    rv = main(args)
    sys.exit(rv)

if __name__ == "__main__":
    run()
