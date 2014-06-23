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
import xml.etree.ElementTree as ET

def debug_node(self, **kwargs):
    """Creates and returns node.


    @inherits: :class:`NodeDriver.create_node`

    :keyword    ex_network: link to a "Network" e.g.,
      "https://services.vcloudexpress.terremark.com/api/v0.8/network/7"
    :type       ex_network: ``str``

    :keyword    ex_vdc: Name of organisation's virtual data
        center where vApp VMs will be deployed.
    :type       ex_vdc: ``str``

    :keyword    ex_cpus: number of virtual cpus (limit depends on provider)
    :type       ex_cpus: ``int``

    :keyword    ex_row: ????
    :type       ex_row: ``str``

    :keyword    ex_group: ????
    :type       ex_group: ``str``
    """
    log = logging.getLogger("cloudhands.burst.control.debug_node")
    name = kwargs['name']
    image = kwargs['image']
    size = kwargs['size']

    # Some providers don't require a network link
    try:
        network = kwargs.get('ex_network', self.networks[0].get('href'))
    except IndexError:
        network = ''

    password = None
    auth = self._get_and_check_auth(kwargs.get('auth'))
    password = auth.password

    instantiate_xml = InstantiateVAppXML(
        name=name,
        template=image.id,
        net_href=network,
        cpus=str(kwargs.get('ex_cpus', 1)),
        memory=str(size.ram),
        password=password,
        row=kwargs.get('ex_row', None),
        group=kwargs.get('ex_group', None)
    )

    log.debug("###")
    with open("cn_payload.xml", "w") as output:
        log.debug(os.path.abspath(output.name))
        print(instantiate_xml.tostring(), file=output)

    vdc = self._get_vdc(kwargs.get('ex_vdc', None))

    # Instantiate VM and get identifier.
    content_type = \
        'application/vnd.vmware.vcloud.instantiateVAppTemplateParams+xml'
    res = self.connection.request(
        '%s/action/instantiateVAppTemplate' % get_url_path(vdc.id),
        data=instantiate_xml.tostring(),
        method='POST',
        headers={'Content-Type': content_type}
    )
    vapp_path = get_url_path(res.object.get('href'))

    # Deploy the VM from the identifier.
    res = self.connection.request('%s/action/deploy' % vapp_path,
                                  method='POST')

    self._wait_for_task_completion(res.object.get('href'))

    # Power on the VM.
    res = self.connection.request('%s/power/action/powerOn' % vapp_path,
                                  method='POST')

    res = self.connection.request(vapp_path)
    node = self._to_node(res.object)

    if getattr(auth, "generated", False):
        node.extra['password'] = auth.password

    return node


def connect(config):
    log = logging.getLogger("cloudhands.burst.control.connect")
    user = config["user"]["name"]
    pswd = config["user"]["pass"]
    host = config["host"]["name"]
    port = config["host"]["port"]
    apiV = config["host"]["api_version"]
    security.VERIFY_SSL_CERT = config["host"].getboolean("verify_ssl_cert")
    DRIVERS[config["libcloud"]["provider"]] = (
        config["libcloud"]["module"], config["libcloud"]["driver"])

    drvr = get_driver(config["libcloud"]["provider"])
    log.debug(drvr)
    log.debug(' '.join((user, pswd, host, port, apiV)))
    conn = drvr(
        user, pswd, host=host, port=port, api_version=apiV)
    #conn.create_node = debug_node
    return conn


def create_node(config, name, auth=None, size=None, image=None, network=None):
    """
    Create a node the libcloud way. Connection is created locally to permit
    threadpool dispatch.
    """
    log = logging.getLogger("cloudhands.burst.control.create_node")
    conn = connect(config)
    log.debug("Connection uses {}".format(config["metadata"]["path"]))
    auth = auth or NodeAuthPassword("q1W2e3R4t5Y6")  # FIXME
    images = conn.list_images()
    img = ([i for i in images if i.name==image] or images)[0]
    size = size or next(
        i for i in conn.list_sizes() if i.name == "1024 Ram")
    net = (
        [i.get("href") for i in conn.networks if i.get("name") == network]
        or [None])[0]  # TODO: remove
    log.debug(net)
    try:
        node = conn.create_node(
            #name=name, auth=auth, size=size, image=img,
            #ex_network=network, ex_vm_fence="natRouted")
            name=name, auth=auth, size=size, image=img, network=network)
        #node = conn.create_node(conn, name=name, auth=auth, size=size, image=img)
        log.debug("create_node returned {}".format(repr(node)))
        del node.driver  # rv should be picklable
    except Exception as e:
        log.warning(e)
        node = None
    return (config, node)


def describe_node(config, uri, auth=None, size=None, image=None):
    """
    Get the attributes of an existing node.
    """
    log = logging.getLogger("cloudhands.burst.control.describe_node")
    conn = connect(config)
    log.debug("Connection uses {}".format(config["metadata"]["path"]))
    try:
        node = next(i for i in conn.list_nodes() if i.id == uri)
    except Exception as e:
        log.warning(e)
        return None
    else:
        log.debug(node)
        return (node.public_ips,)


def destroy_node(config, uri, auth=None, size=None, image=None):
    """
    Destroy a node the libcloud way. Connection is created locally to permit
    threadpool dispatch.
    """
    log = logging.getLogger("cloudhands.burst.control.destroy_node")
    conn = connect(config)
    log.debug("Connection uses {}".format(config["metadata"]["path"]))
    try:
        node = next(i for i in conn.list_nodes() if i.id == uri)
        conn.destroy_node(node)
    except Exception as e:
        log.warning(e)
        uri = None
    return (config, uri)


def list_images(providerName):
    for config in [
        cfg for p in providers.values() for cfg in p
        if cfg["metadata"]["path"] == providerName
    ]:
        conn = connect(config)
        return [(i.name, i.id) for i in conn.list_images()]
    else:
        return None

class NATNanny:

    def __init__(self, q, args, config):
        self.q = q
        self.args = args
        self.config = config

        #proxies = {
        #    "http": "http://wwwcache.rl.ac.uk:8080",
        #    "https": "http://wwwcache.rl.ac.uk:8080"
        #}
        #connector = aiohttp.ProxyConnector(proxy=proxies["http"])

    @asyncio.coroutine
    def __call__(self):
        log = logging.getLogger("cloudhands.burst.natnanny")
        session = Registry().connect(sqlite3, self.args.db).session
        initialise(session)
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

            orgData = yield from response.read_and_close()
            tree = ET.fromstring(orgData.decode("utf-8"))
            for org in tree.iter():
                print(org)

            msg = yield from self.q.get()
            if msg is None:
                log.warning("Sentinel received. Shutting down.")
                break


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
    q = asyncio.Queue(loop=loop)
    nanny = NATNanny(q, args, cfg)
    tasks = [
        asyncio.Task(nanny())]

    loop.call_soon_threadsafe(q.put_nowait, None)
    loop.run_until_complete(asyncio.wait(tasks))
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
