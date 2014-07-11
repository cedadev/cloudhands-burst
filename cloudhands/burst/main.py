#!/usr/bin/env python
# encoding: UTF-8

import argparse
import asyncio
import datetime
import logging
from logging.handlers import WatchedFileHandler
import sched
import sqlite3
import sys
import time

from cloudhands.burst.agent import message_handler
from cloudhands.burst.agent import operate
from cloudhands.burst.appliance import ApplianceAgent # TODO: remove
from cloudhands.burst.appliance import PreCheckAgent
from cloudhands.burst.appliance import PreDeleteAgent
from cloudhands.burst.appliance import PreOperationalAgent
from cloudhands.burst.appliance import PreProvisionAgent
from cloudhands.burst.appliance import PreStopAgent
from cloudhands.burst.appliance import ProvisioningAgent
from cloudhands.burst.subscription import SubscriptionAgent
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.discovery import settings
from cloudhands.common.fsm import ApplianceState

__doc__ = """
This process performs tasks to administer hosts in the JASMIN cloud.

It makes state changes to Appliance artifacts in the JASMIN database. It
operates in a round-robin loop with a specified interval.
"""

DFLT_DB = ":memory:"


def main(args):
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
    loop = asyncio.get_event_loop()
    msgQ = asyncio.Queue(loop=loop)

    workers = []
    for agentType in (
        PreCheckAgent,
        PreDeleteAgent,
        PreOperationalAgent,
        PreProvisionAgent,
        PreStopAgent,
        ProvisioningAgent,
    ):
        workQ = agentType.queue(args, config, loop=loop)
        agent = agentType(workQ, args, config)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)
        workers.append(agent)

    loop.run_until_complete(operate(loop, msgQ, workers, args, config))
    loop.close()

    return 0
    ### Old code below for deletion ####
    session = Registry().connect(sqlite3, args.db).session
    initialise(session)

    loop = sched.scheduler()

    sA = SubscriptionAgent(args, config, session, loop)
    sA.touch_unchecked(priority=1)

    aA = ApplianceAgent(args, config, session, loop)
    aA.touch_pre_provision(priority=1)
    aA.touch_pre_operational(priority=1)
    #aA.touch_deleting(priority=2)

    if args.interval:
        loop.run()
        return 1
    else:
        return 0


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
