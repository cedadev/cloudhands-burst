#!/usr/bin/env python
# encoding: UTF-8

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
from cloudhands.common.fsm import HostState
from cloudhands.common.schema import Component
from cloudhands.common.schema import DCStatus
from cloudhands.common.schema import Touch

__doc__ = """
"""

DFLT_DB = ":memory:"

security.CA_CERTS_PATH = bundles


class BurstController(Initialiser):

    def get_dcs(driver, user, pswd, host, port, version):
        conn = driver(
            user, pswd, host=host, port=port, api_version=version)
        return conn.vdcs

    def __init__(self, config, path=DFLT_DB, driver=None):
        self.config = config
        self.driver = driver or get_driver(Provider.VCLOUD)
        self.engine = self.connect(sqlite3, path=path)
        self.session = Session()
        self.identity = self.session.query(
            Component).filter(Component.handle == burstCtrl).first()

    def check_DC(self):
        status = self.session.query(DCStatus).filter(
            DCStatus.name == self.config["host"]["name"]).first()
        if status is None:
            status = DCStatus(
                uuid=uuid.uuid4().hex,
                model=cloudhands.common.__version__,
                uri=self.config["host"]["name"],
                name=self.config["host"]["name"])

        kwargs = {
            "user": self.config["user"]["name"],
            "pswd": self.config["user"]["pass"],
            "host": self.config["host"]["name"],
            "port": self.config["host"]["port"],
            "version": self.config["host"]["api_version"],
        }
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                BurstController.get_dcs, self.driver, **kwargs)
            try:
                now = datetime.datetime.utcnow()
                rv = list(future.result(timeout=2.0))
            except TimeoutError:
                log.warning("timed out")
                state = self.session.query(
                    HostState).filter(
                    HostState.name == "unknown").first()
            else:
                if not rv:
                    state = self.session.query(
                        HostState).filter(
                        HostState.name == "down").first()
                else:
                    state = self.session.query(
                        HostState).filter(
                        HostState.name == "up").first()

            finally:
                status.changes.append(
                    Touch(
                        artifact=status, actor=self.identity,
                        state=state, at=now)
                    )
                self.session.add(status)
                self.session.commit()

        return rv
