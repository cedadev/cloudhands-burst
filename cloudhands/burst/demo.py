#!/usr/bin/env python
# encoding: UTF-8

import argparse
from configparser import ConfigParser
import logging
import sqlite3
import sys

from libcloud import security
from libcloud.compute.base import NodeAuthPassword
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

import cloudhands.burst.main

from cloudhands.common.component import burstCtrl  # TODO: Entry point
from cloudhands.common.connectors import Initialiser
from cloudhands.common.connectors import Session
from cloudhands.common.discovery import bundles
from cloudhands.common.discovery import settings
from cloudhands.common.schema import Component
from cloudhands.common.schema import Host
from cloudhands.common.schema import State
from cloudhands.common.schema import Touch

from cloudhands.web.demo import DemoLoader

__doc__ = """
Back end demo
"""

DFLT_DB = ":memory:"

security.CA_CERTS_PATH = bundles


def configure_driver():
    config = next(iter(settings))  # FIXME
    user = config["user"]["name"]
    pswd = config["user"]["pass"]
    host = config["host"]["name"]
    port = config["host"]["port"]
    apiV = config["host"]["api_version"]
    drvr = get_driver(Provider.VCLOUD)
    conn = drvr(
        user, pswd, host=host, port=port, api_version=apiV)
    return conn

def hosts(session, state=None):
    query = session.query(Host)
    if not state:
        return query.all()

    return [h for h in query.all() if h.changes[-1].state.name == state]


def main(args):
    rv = 1
    log = logging.getLogger("cloudhands.burst.demo")

    ldr = DemoLoader(config=ConfigParser(), path=args.db)
    ldr.create_organisations()
    user = ldr.grant_user_membership()
    ldr.load_hosts_for_user(user)

    conn = configure_driver()
    img = next(i for i in conn.list_images() if i.name == "Routed-Centos6.4a")
    size = next(i for i in conn.list_sizes() if i.name == "1024 Ram")
    for host in hosts(ldr.con.session, state="requested"):
        pwd = NodeAuthPassword("q1W2e3R4t5Y6")
        node = conn.create_node(name=host.name, auth=pwd, size=size, image=img)
        print(node)
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
