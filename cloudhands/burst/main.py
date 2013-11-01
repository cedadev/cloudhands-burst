#!/usr/bin/env python
# encoding: UTF-8

import argparse
from concurrent.futures import ThreadPoolExecutor
import logging
import sys

from libcloud import security
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

import cloudhands.burst
import cloudhands.common

from cloudhands.common.discovery import bundles
from cloudhands.common.discovery import settings

__doc__ = """
"""

security.CA_CERTS_PATH = bundles


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
    if args.version:
        for mod in (cloudhands.burst, cloudhands.common):
            log.info("{:18} version {}".format(mod.__name__, mod.__version__))
        rv = 0
    elif args.dc:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(list_dc)
            try:
                for i in future.result(timeout=2.0):
                    bits = vars(i).items()
                    for k, v in bits:
                        log.info("{} {}".format(k, v))
            except TimeoutError:
                log.warning("timed out")
    return rv


def parser():
    rv = argparse.ArgumentParser(description=__doc__)
    rv.add_argument(
        "--version", action="store_true", default=False,
        help="Print the current version number")
    rv.add_argument(
        "-v", "--verbose", required=False,
        action="store_const", dest="log_level",
        const=logging.DEBUG, default=logging.INFO,
        help="Increase the verbosity of output")
    rv.add_argument(
        "--dc", action="store_true", default=False,
        help="Interact with data centres")

    return rv


def run():
    p = parser()
    args = p.parse_args()
    rv = main(args)
    sys.exit(rv)

if __name__ == "__main__":
    run()
