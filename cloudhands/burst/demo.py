#!/usr/bin/env python
# encoding: UTF-8

import argparse
import concurrent.futures
from configparser import ConfigParser
import datetime
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
from cloudhands.common.fsm import HostState
from cloudhands.common.schema import Component
from cloudhands.common.schema import Host
from cloudhands.common.schema import Node
from cloudhands.common.schema import State
from cloudhands.common.schema import Touch

from cloudhands.web.demo import DemoLoader

__doc__ = """
Back end demo
"""

DFLT_DB = ":memory:"

security.CA_CERTS_PATH = bundles

def create_node(name, auth, size=None, image=None):
    """
    Create a node the libcloud way. Connection is created locally to permit
    threadpool dispatch.
    """
    log = logging.getLogger("cloudhands.burst.{}".format(name))
    conn = configure_driver()
    img = image or next(
        i for i in conn.list_images() if i.name == "Routed-Centos6.4a")
    log.info(img)
    size = size or next(
        i for i in conn.list_sizes() if i.name == "1024 Ram")
    node = conn.create_node(name=name, auth=auth, size=size, image=image)
    #rv = vars(node)
    #del rv["driver"]
    #print(rv)
    return node

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
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s|%(message)s")
    log = logging.getLogger("cloudhands.burst.demo")

    ldr = DemoLoader(config=ConfigParser(), path=args.db)
    ldr.create_organisations()
    user = ldr.grant_user_membership()
    ldr.load_hosts_for_user(user)

    pwd = NodeAuthPassword("q1W2e3R4t5Y6")
    for host in hosts(ldr.con.session, state="requested"):
        create_node(host.name, pwd)

    return 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as exctr:
    #with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exctr:
        jobs = {exctr.submit(
            create_node, name=host.name, auth=pwd): host for host in hosts(
                ldr.con.session, state="requested")}

        now = datetime.datetime.utcnow()
        scheduling = ldr.con.session.query(HostState).filter(
            HostState.name == "scheduling").one()
        for host in jobs.values():
            host.changes.append(
                Touch(artifact=host, actor=user, state=scheduling, at=now))
            ldr.con.session.commit()
            log.info("{} is scheduling".format(host.name))

        unknown = ldr.con.session.query(HostState).filter(
            HostState.name == "unknown").one()
        for job in concurrent.futures.as_completed(jobs):
            host = jobs[job]
            now = datetime.datetime.utcnow()
            act = Touch(artifact=host, actor=user, state=unknown, at=now)
            host.changes.append(act)
            node = Node(name=host.name, touch=act)
            ldr.con.session.add(node)
            ldr.con.session.commit()
            log.info("{} {}: Status unknown".format(host.name, job.result()))

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
