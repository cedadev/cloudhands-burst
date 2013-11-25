#!/usr/bin/env python
# encoding: UTF-8

import logging
import sqlite3

from libcloud import security
from libcloud.compute.base import NodeAuthPassword
from libcloud.compute.providers import get_driver

from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.discovery import bundles
from cloudhands.common.discovery import settings

security.CA_CERTS_PATH = bundles


class Strategy(object):

    def recommend(session=None):
        provider, config = next(iter(settings.items()))  # TODO sort providers
        user = config["user"]["name"]
        pswd = config["user"]["pass"]
        host = config["host"]["name"]
        port = config["host"]["port"]
        apiV = config["host"]["api_version"]
        drvr = get_driver(config["libcloud"]["provider"])
        conn = drvr(
            user, pswd, host=host, port=port, api_version=apiV)
        return provider, conn


def create_node(name, auth=None, size=None, image=None):
    """
    Create a node the libcloud way. Connection is created locally to permit
    threadpool dispatch.
    """
    provider, conn = Strategy.recommend()
    log = logging.getLogger("cloudhands.burst.{}".format(provider))
    auth = auth or NodeAuthPassword("q1W2e3R4t5Y6")
    img = image or next(
        i for i in conn.list_images() if i.name == "Routed-Centos6.4a")
    size = size or next(
        i for i in conn.list_sizes() if i.name == "1024 Ram")
    try:
        node = conn.create_node(name=name, auth=auth, size=size, image=img)
        del node.driver  # rv should be picklable
    except Exception as e:
        log.warning(e)
        node = None
    return (provider, node)
