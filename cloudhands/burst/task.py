#!/usr/bin/env python
# encoding: UTF-8

import argparse
import asyncio
import os
import os.path
import logging
import sqlite3
import sys

#from libcloud import security
#from libcloud.compute.base import NodeAuthPassword
#from libcloud.compute.providers import DRIVERS
#from libcloud.compute.providers import get_driver

from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.discovery import bundles
from cloudhands.common.discovery import providers
from cloudhands.common.discovery import settings

#security.CA_CERTS_PATH = bundles

#from libcloud.compute.drivers.vcloud import InstantiateVAppXML

DFLT_DB = ":memory:"

# prototyping
import aiohttp
from collections import OrderedDict
from collections import namedtuple
import functools
try:
    from functools import singledispatch
except ImportError:
    from singledispatch import singledispatch
import warnings
import xml.etree.ElementTree as ET

from cloudhands.burst.utils import find_xpath

find_orgs = functools.partial(
    find_xpath, "./*/[@type='application/vnd.vmware.vcloud.org+xml']")

find_vdcs = functools.partial(
    find_xpath, "./*/[@type='application/vnd.vmware.vcloud.vdc+xml']")

find_records = functools.partial(
    find_xpath, "./*/[@type='application/vnd.vmware.vcloud.query.records+xml']")

class Agent:

    def __init__(self, workQ, args, config):
        self.work = workQ
        self.args = args
        self.config = config

class PreOperationalAgent(Agent):

        #proxies = {
        #    "http": "http://wwwcache.rl.ac.uk:8080",
        #    "https": "http://wwwcache.rl.ac.uk:8080"
        #}
        #connector = aiohttp.ProxyConnector(proxy=proxies["http"])

    Message = namedtuple("PreOperationalMessage", [])
    Queue = asyncio.Queue

    def touch(self, msg:Message):
        pass
    
    @asyncio.coroutine
    def __call__(self, loop, msgQ):
        log = logging.getLogger("cloudhands.burst.natnanny")
        session = Registry().connect(sqlite3, self.args.db).session
        initialise(session)
        ET.register_namespace("", "http://www.vmware.com/vcloud/v1.5")
        while True:
            url = "{scheme}://{host}:{port}/{endpoint}".format(
                scheme="https",
                host=self.config["host"]["name"],
                port=self.config["host"]["port"],
                endpoint="api/sessions")

            headers = {
                "Accept": "application/*+xml;version=5.5",
            }

            client = aiohttp.client.HttpClient(
                ["{host}:{port}".format(
                    host=self.config["host"]["name"],
                    port=self.config["host"]["port"])
                ],
                verify_ssl=self.config["host"].getboolean("verify_ssl_cert")
            )

            # TODO: We have to store tokens in the database
            response = yield from client.request(
                "POST", url,
                auth=(self.config["user"]["name"], self.config["user"]["pass"]),
                headers=headers)
                #connector=connector)
                #request_class=requestClass)
            headers["x-vcloud-authorization"] = response.headers.get(
                "x-vcloud-authorization")


            url = "{scheme}://{host}:{port}/{endpoint}".format(
                scheme="https",
                host=self.config["host"]["name"],
                port=self.config["host"]["port"],
                endpoint="api/org")
            response = yield from client.request(
                "GET", url,
                headers=headers)

            orgList = yield from response.read_and_close()
            tree = ET.fromstring(orgList.decode("utf-8"))
            orgFound = find_orgs(tree, name=self.config["vdc"]["org"])

            response = yield from client.request(
                "GET", next(orgFound).attrib.get("href"),
                headers=headers)
            orgData = yield from response.read_and_close()
            tree = ET.fromstring(orgData.decode("utf-8"))
            vdcFound = find_vdcs(tree)

            url = next(vdcFound).attrib.get("href")
            response = yield from client.request(
                "GET", url, headers=headers)
            vdcData = yield from response.read_and_close()
            tree = ET.fromstring(vdcData.decode("utf-8"))
            gwsFound = find_records(tree, rel="edgeGateways")


            url = next(gwsFound).attrib.get("href")
            response = yield from client.request(
                "GET", url, headers=headers)
            gwsData = yield from response.read_and_close()
            tree = ET.fromstring(gwsData.decode("utf-8"))
            ET.dump(tree)

            msg = yield from self.q.get()
            if msg is None:
                log.warning("Sentinel received. Shutting down.")
                break

@singledispatch
def touch(msg):
    warnings.warn("No handler for {}".format(type(msg)))
    pass

@asyncio.coroutine
def dispatch(loop, msqQ, workers):
    # Loop through ready tasks
    # Call task query against database
    # Place result on task queue
    # Fetch message from msgQ
    # Call message handler

    while True:
        print("Yay")
        yield from msgQ.get()

def main(args):
    log = logging.getLogger("cloudhands.burst")
    log.setLevel(args.log_level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s|%(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(args.log_level)
    ch.setFormatter(formatter)
    log.addHandler(ch)

    portalName, config = next(iter(settings.items()))

    cfg = next(
        p for seq in providers.values() for p in seq
        if p["metadata"]["path"].endswith("phase04.cfg"))
    loop = asyncio.get_event_loop()
    msgQ = asyncio.Queue(loop=loop)

    workers = []
    for agentType in (PreOperationalAgent,):
        workQ = agentType.Queue(loop=loop)
        agent = agentType(workQ, args, config)
        touch.register(agentType.Message, agent.touch)
        workers.append(agent)

    print(workers)

    tasks = [asyncio.Task(w(loop, msgQ)) for w in workers]
    loop.run_until_complete(asyncio.wait(dispatch(loop, msgQ, workers)))
    loop.close()

    return 0


def parser(descr=__doc__):
    rv = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=descr)
    rv.add_argument(
        "--db", default=DFLT_DB,
        help="Set the path to the database [{}]".format(DFLT_DB))
    rv.add_argument(
        "--version", action="store_true", default=False,
        help="Print the current version number")
    rv.add_argument(
        "-v", "--verbose", required=False,
        action="store_const", dest="log_level",
        const=logging.DEBUG, default=logging.INFO,
        help="Increase the verbosity of output")
    return rv


def run():
    p = parser()
    args = p.parse_args()
    rv = 0
    if args.version:
        sys.stdout.write(__version__ + "\n")
    else:
        rv = main(args)
    sys.exit(rv)

if __name__ == "__main__":
    run()
