#!/usr/bin/env python
# encoding: UTF-8

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import logging
import sqlite3
import sys
import uuid

__doc__ = """
"""

DFLT_DB = ":memory:"

def list_images():
    conn = configure_driver()
    return conn.list_images()

def list_nodes():
    config = next(iter(settings))  # FIXME
    user = config["user"]["name"]
    pswd = config["user"]["pass"]
    host = config["host"]["name"]
    port = config["host"]["port"]
    apiV = config["host"]["api_version"]
    vcloudDrvr = get_driver(Provider.VCLOUD)
    conn = vcloudDrvr(
        user, pswd, host=host, port=port, api_version=apiV)
    return conn.list_nodes()


def list_dc():
    config = next(iter(settings))  # FIXME
    user = config["user"]["name"]
    pswd = config["user"]["pass"]
    host = config["host"]["name"]
    port = config["host"]["port"]
    apiV = config["host"]["api_version"]
    vcloudDrvr = get_driver(Provider.VCLOUD)
    conn = vcloudDrvr(
        user, pswd, host=host, port=port, api_version=apiV)
    return conn.vdcs


def main(args):
    rv = 1
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s|%(message)s")
    log = logging.getLogger("cloudhands.burst")

    ctrl = BurstController(config=next(iter(settings)), path=args.db)

    if args.version:
        for mod in (cloudhands.burst, cloudhands.common):
            log.info("{:18} version {}".format(mod.__name__, mod.__version__))
        rv = 0
    elif args.status == "dc":
        result = ctrl.check_DC()
        for i in result:
            bits = vars(i).items()
            for k, v in bits:
                log.info("{} {}".format(k, v))
    elif args.status == "nodes":
        result = ctrl.check_nodes()
        for i in result:
            bits = vars(i).items()
            for k, v in bits:
                log.info("{} {}".format(k, v))
    elif args.status == "images":
        result = ctrl.check_images()
        for i in result:
            bits = vars(i).items()
            for k, v in bits:
                log.info("{} {}".format(k, v))


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
        "--status", default="dc",
        help="Discover the status of part of the system")

    return rv


def run():
    p = parser()
    args = p.parse_args()
    rv = main(args)
    sys.exit(rv)

if __name__ == "__main__":
    run()
