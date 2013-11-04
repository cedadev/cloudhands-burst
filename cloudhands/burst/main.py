#!/usr/bin/env python
# encoding: UTF-8

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import logging
import sqlite3
import sys
import uuid

from libcloud import security
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

import cloudhands.burst

import cloudhands.common
from cloudhands.common.component import burstCtrl  # TODO: Entry point
from cloudhands.common.connectors import Initialiser
from cloudhands.common.connectors import Session
from cloudhands.common.discovery import bundles
from cloudhands.common.discovery import settings
from cloudhands.common.fsm import ResourceState
from cloudhands.common.schema import Component
from cloudhands.common.schema import DCStatus
from cloudhands.common.schema import Touch

__doc__ = """
"""

DFLT_DB = ":memory:"

security.CA_CERTS_PATH = bundles


class BurstController(Initialiser):

    def __init__(self, config, path=DFLT_DB):
        self.config = config
        self.engine = self.connect(sqlite3, path=path)
        self.session = Session()
        self.identity = self.session.query(
            Component).filter(Component.handle == burstCtrl).first()

    def check_DC(self):
        try:
            status = self.session.query(DCStatus).filter(
                DCStatus.name == self.config["host"]["name"]).first()
        except Exception as e:
            status = DCStatus(
                uuid=uuid.uuid4().hex,
                model=cloudhands.common.__version__,
                uri=self.config["host"]["name"],
                name=self.config["host"]["name"])

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(list_dc)
            try:
                now = datetime.datetime.utcnow()
                rv = future.result(timeout=2.0)
            except TimeoutError:
                log.warning("timed out")
                unknown = self.session.query(
                    ResourceState).filter(
                    ResourceState.name == "unknown").first()
            else:
                up = self.session.query(
                    ResourceState).filter(ResourceState.name == "up").first()

                status.changes.append(
                    Touch(
                        artifact=status, actor=self.identity, state=up, at=now)
                    )
                self.session.add(status)
                self.session.commit()

        return rv


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
