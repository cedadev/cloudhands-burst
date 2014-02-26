#!/usr/bin/env python
# encoding: UTF-8

import os
import os.path
import logging
import sqlite3

from libcloud import security
from libcloud.compute.base import NodeAuthPassword
from libcloud.compute.providers import get_driver

from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.discovery import bundles
from cloudhands.common.discovery import providers

security.CA_CERTS_PATH = bundles
security.VERIFY_SSL_CERT = True

from libcloud.compute.drivers.vcloud import InstantiateVAppXML

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
    user = config["user"]["name"]
    pswd = config["user"]["pass"]
    host = config["host"]["name"]
    port = config["host"]["port"]
    apiV = config["host"]["api_version"]
    drvr = get_driver(config["libcloud"]["provider"])
    conn = drvr(
        user, pswd, host=host, port=port, api_version=apiV)
    #conn.create_node = debug_node
    return conn


def create_node(config, name, auth=None, size=None, image=None):
    """
    Create a node the libcloud way. Connection is created locally to permit
    threadpool dispatch.
    """
    log = logging.getLogger("cloudhands.burst.control.create_node")
    conn = connect(config)
    log.debug("Connection uses {}".format(config["metadata"]["path"]))
    auth = auth or NodeAuthPassword("q1W2e3R4t5Y6")
    img = image or next(
        i for i in conn.list_images() if i.name == "Routed-Centos6.4a")  # Ph1
        # i for i in conn.list_images() if i.name == "centos-routed64a")  # Ph2
    size = size or next(
        i for i in conn.list_sizes() if i.name == "1024 Ram")
    try:
        node = conn.create_node(name=name, auth=auth, size=size, image=img)
        #node = conn.create_node(conn, name=name, auth=auth, size=size, image=img)
        log.debug("create_node returned {}".format(repr(node)))
        del node.driver  # rv should be picklable
    except Exception as e:
        log.warning(e)
        node = None
    return (config, node)


def list_images(providerName):
    for config in [
        cfg for p in providers.values() for cfg in p
        if cfg["metadata"]["path"] == providerName
    ]:
        conn = connect(config)
        return [(i.name, i.id) for i in conn.list_images()]
    else:
        return None
