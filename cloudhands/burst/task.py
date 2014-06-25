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

    Message = namedtuple("PreOperationalMessage", ["content"])

    @staticmethod
    def queue(args, config, loop=None):
        return asyncio.Queue(loop=loop)

    @property
    def callbacks(self):
        return [(PreOperationalAgent.Message, self.touch)]

    def jobs(self, session):
        return [1, None]

    def touch(self, msg:Message, session):
        print(msg)
    
    @asyncio.coroutine
    def __call__(self, loop, msgQ):
        log = logging.getLogger("cloudhands.burst.appliance.preoperational")
        ET.register_namespace("", "http://www.vmware.com/vcloud/v1.5")
        provider = next(
            p for seq in providers.values() for p in seq
            if p["metadata"]["path"].endswith("phase04.cfg"))

        while True:
            work = yield from self.work.get()

            if work is None:
                log.warning("Sentinel received. Shutting down.")
                break

            url = "{scheme}://{host}:{port}/{endpoint}".format(
                scheme="https",
                host=provider["host"]["name"],
                port=provider["host"]["port"],
                endpoint="api/sessions")

            headers = {
                "Accept": "application/*+xml;version=5.5",
            }

            client = aiohttp.client.HttpClient(
                ["{host}:{port}".format(
                    host=provider["host"]["name"],
                    port=provider["host"]["port"])
                ],
                verify_ssl=provider["host"].getboolean("verify_ssl_cert")
            )

            # TODO: We have to store tokens in the database
            response = yield from client.request(
                "POST", url,
                auth=(provider["user"]["name"], provider["user"]["pass"]),
                headers=headers)
                #connector=connector)
                #request_class=requestClass)
            headers["x-vcloud-authorization"] = response.headers.get(
                "x-vcloud-authorization")


            url = "{scheme}://{host}:{port}/{endpoint}".format(
                scheme="https",
                host=provider["host"]["name"],
                port=provider["host"]["port"],
                endpoint="api/org")
            response = yield from client.request(
                "GET", url,
                headers=headers)

            orgList = yield from response.read_and_close()
            tree = ET.fromstring(orgList.decode("utf-8"))
            orgFound = find_orgs(tree, name=provider["vdc"]["org"])

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

            yield from msgQ.put(PreOperationalAgent.Message(tree))

@singledispatch
def touch(msg):
    warnings.warn("No handler for {}".format(type(msg)))
    pass

@asyncio.coroutine
def operate(loop, msgQ, workers, args, config):
    log = logging.getLogger("cloudhands.burst.operate")
    tasks = [asyncio.Task(w(loop, msgQ)) for w in workers]
    session = Registry().connect(sqlite3, args.db).session
    initialise(session)
    while any(task for task in tasks if not task.done()):
        yield from asyncio.sleep(0)
        for worker in workers:
            # Call task query against database
            # Place result on task queue
            for job in worker.jobs(session):
                yield from worker.work.put(job)

        try:
            while True:
                msg = msgQ.get_nowait()
                log.debug(touch(msg, session))
        except asyncio.QueueEmpty:
            continue

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

    loop = asyncio.get_event_loop()
    msgQ = asyncio.Queue(loop=loop)

    workers = []
    for agentType in (PreOperationalAgent,):
        workQ = agentType.queue(args, config, loop=loop)
        agent = agentType(workQ, args, config)
        for typ, handler in agent.callbacks:
            touch.register(typ, handler)
        workers.append(agent)

    loop.run_until_complete(operate(loop, msgQ, workers, args, config))
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
