#!/usr/bin/env python
# encoding: UTF-8

import asyncio
from collections import deque
from collections import namedtuple
import concurrent.futures
import datetime
import functools
import logging
import operator
import re
import textwrap
import uuid
import xml.etree.ElementTree as ET
import xml.sax.saxutils

import aiohttp
from chameleon import PageTemplateFile
import pkg_resources
from sqlalchemy import desc

from cloudhands.burst.agent import Agent
from cloudhands.burst.agent import Job
from cloudhands.burst.control import create_node
from cloudhands.burst.control import describe_node
from cloudhands.burst.control import destroy_node
from cloudhands.burst.utils import find_xpath
from cloudhands.burst.utils import unescape_script
from cloudhands.common.discovery import providers
from cloudhands.common.discovery import settings
from cloudhands.common.schema import Appliance
from cloudhands.common.schema import CatalogueChoice
from cloudhands.common.schema import Component
from cloudhands.common.schema import IPAddress
from cloudhands.common.schema import Label
from cloudhands.common.schema import NATRouting
from cloudhands.common.schema import Node
from cloudhands.common.schema import OSImage
from cloudhands.common.schema import Provider
from cloudhands.common.schema import ProviderReport
from cloudhands.common.schema import ProviderToken
from cloudhands.common.schema import Touch
from cloudhands.common.states import ApplianceState

__doc__ = """


.. graphviz::

   digraph appliance {
    center = true;
    compound = true;
    nodesep = 0.6;
    edge [decorate=true,labeldistance=3,labelfontname=helvetica,
        labelfontsize=10,labelfloat=false];

    subgraph cluster_states {
        label = "Static";
        configuring -> pre_provision [style=invis];
        pre_check -> pre_operational [style=invis];
        pre_operational -> pre_delete [style=invis];
        pre_delete -> deleted [style=invis];
        deleted -> pre_stop [style=invis];
        stopped -> pre_start [style=invis];
        pre_start -> running [style=invis];

    subgraph cluster_super {
        label = "Active";
        node [height=1,width=2];
        provisioning -> operational [style=invis];
    }

    }

    pre_provision -> provisioning [style=invis];
    operational -> pre_check [style=invis];

    configuring -> pre_provision [taillabel="user"];
    operational -> pre_check [ltail=cluster_super,taillabel="user"];
    operational -> pre_stop [taillabel="user"];

    subgraph cluster_agents {
        label = "Burst controller";
        style = filled;
        node [shape=box];
        pre_provision_agent -> provisioning_agent [style=invis];
        provisioning_agent -> pre_check_agent [style=invis];
        pre_check_agent -> pre_operational_agent [style=invis];
        pre_operational_agent -> pre_delete_agent [style=invis];
        pre_delete_agent -> pre_stop_agent [style=invis];
        pre_stop_agent -> pre_start_agent [style=invis];
    }

    pre_provision -> pre_provision_agent[style=dashed,arrowhead=none];
    pre_provision_agent -> provisioning;

    provisioning -> provisioning_agent [taillabel="delay",style=dashed,arrowhead=none];
    provisioning_agent -> pre_check;
    pre_check -> pre_check_agent [style=dashed,arrowhead=none];
    pre_check_agent -> operational;
    pre_check_agent -> pre_operational;
    pre_operational -> pre_operational_agent [style=dashed,arrowhead=none];
    pre_operational -> pre_stop [taillabel="out of resource"];
    pre_operational_agent -> operational;
    pre_delete -> pre_delete_agent [style=dashed,arrowhead=none];
    pre_delete_agent -> deleted;
    pre_stop -> pre_stop_agent [style=dashed,arrowhead=none];
    pre_stop_agent -> stopped;
    stopped -> pre_delete [taillabel="user"];
    stopped -> pre_start [taillabel="user"];
    pre_start -> pre_start_agent [style=dashed,arrowhead=none,weight=2];
    pre_start_agent -> running [tailport=w,weight=6];
    running -> pre_stop [taillabel="user"];
   }
"""

customizationScript = """#!/bin/sh
if [ x$1 == x"precustomization" ]; then
echo "Precustomisation"
elif [ x$1 == x"postcustomization" ]; then
echo "Postcustomisation"
/usr/local/bin/activator.sh {host}/appliance/{uuid}
fi
"""

find_catalogueitems = functools.partial(
    find_xpath, ".//*[@type='application/vnd.vmware.vcloud.catalogItem+xml']",
    namespaces={"": "http://www.vmware.com/vcloud/v1.5"})

find_catalogues = functools.partial(
    find_xpath, "./*/[@type='application/vnd.vmware.vcloud.catalog+xml']")

def find_customizationsection(tree): 
    elems = find_xpath(
        ".//*[@type='application/vnd.vmware.vcloud.guestCustomizationSection+xml']",
        tree, namespaces={"": "http://www.vmware.com/vcloud/v1.5"})
    return (i for i in elems if i.tag.endswith("CustomizationSection"))

def find_customizationscript(tree): 
    return (i for s in find_customizationsection(tree) for i in s
            if i.tag.endswith("CustomizationScript"))

find_gatewayserviceconfiguration = functools.partial(
    find_xpath,
    ".//*[@type='application/vnd.vmware.admin.edgeGatewayServiceConfiguration+xml']")

def find_ipranges(tree, namespace="http://www.vmware.com/vcloud/v1.5"): 
    ranges = tree.iter("{{{}}}IpRange".format(namespace))
    for r in ranges:
        yield (
            r.find("{{{}}}StartAddress".format(namespace)),
            r.find("{{{}}}EndAddress".format(namespace)))

def find_networkconnectionsection(tree): 
    elems = find_xpath(
        ".//*[@type='application/vnd.vmware.vcloud.networkConnectionSection+xml']",
        tree, namespaces={"": "http://www.vmware.com/vcloud/v1.5"})
    return (i for i in elems if i.tag.endswith("NetworkConnectionSection"))

def find_networkconnection(tree): 
    return (i for s in find_networkconnectionsection(tree) for i in s
            if i.tag.endswith("NetworkConnection"))

def find_networkconfigsection(tree): 
    elems = find_xpath(
        ".//*[@type='application/vnd.vmware.vcloud.networkConfigSection+xml']",
        tree, namespaces={"": "http://www.vmware.com/vcloud/v1.5"})
    return (i for i in elems if i.tag.endswith("NetworkConfigSection"))

def find_networkconfig(tree): 
    return (i for s in find_networkconfigsection(tree) for i in s
            if i.tag.endswith("NetworkConfig"))

find_networkinterface = functools.partial(
    find_xpath, ".//*[@type='application/vnd.vmware.admin.network+xml']",
    namespaces={"": "http://www.vmware.com/vcloud/v1.5"})

find_orgs = functools.partial(
    find_xpath, "./*/[@type='application/vnd.vmware.vcloud.org+xml']")

find_records = functools.partial(
    find_xpath, "./*/[@type='application/vnd.vmware.vcloud.query.records+xml']")

find_results = functools.partial(find_xpath, "./*")

find_templates = functools.partial(
    find_xpath, ".//*[@type='application/vnd.vmware.vcloud.vAppTemplate+xml']",
    namespaces={"": "http://www.vmware.com/vcloud/v1.5"})

find_vdcs = functools.partial(
    find_xpath, "./*/[@type='application/vnd.vmware.vcloud.vdc+xml']")

find_vms = functools.partial(
    find_xpath, ".//*[@type='application/vnd.vmware.vcloud.vm+xml']")

def find_catalogrecords(text):
    # ElementTree expects QueryResultRecords to declare a namespace. This and
    # other issues mean using regular expressions instead.
    log = logging.getLogger(
        "cloudhands.burst.appliance.find_catalogrecords")
    records = re.findall("<CatalogRecord[^>]+>", text)
    return [ET.fromstring(r) for r in records]

@asyncio.coroutine
def find_template_among_catalogues(
    client, headers, templateName, catalogues
):
    log = logging.getLogger(
        "cloudhands.burst.appliance.find_template_among_catalogues")
    rv = None
    for catalogue in catalogues:
        response = yield from client.request(
            "GET", catalogue.attrib.get("href"),
            headers=headers)
        catalogueData = yield from response.read_and_close()
        tree = ET.fromstring(catalogueData.decode("utf-8"))
        for catalogueItem in find_catalogueitems(tree, name=templateName):
            response = yield from client.request(
                "GET", catalogueItem.attrib.get("href"),
                headers=headers)
            catalogueItemData = yield from response.read_and_close()
            tree = ET.fromstring(catalogueItemData.decode("utf-8"))

            rv = next(find_templates(tree), None)
            if rv is not None:
                break

    return rv


@asyncio.coroutine
def find_template_among_orgs(
    client, headers, orgs, templateName,
    catalogName="UN-managed Public Catalog"
):
    log = logging.getLogger("cloudhands.burst.appliance.find_template_among_orgs")
    rv = None
    orgs = list(orgs)
    while rv is None:
        try:
            org = orgs.pop(0)
        except IndexError:
            break
        else:
            response = yield from client.request(
            "GET", org.attrib.get("href"),
            headers=headers)
        orgData = yield from response.read_and_close()
        tree = ET.fromstring(orgData.decode("utf-8"))

        for catalogue in find_catalogues(tree, name=catalogName):
            response = yield from client.request(
                "GET", catalogue.attrib.get("href"),
                headers=headers)
            catalogueData = yield from response.read_and_close()
            tree = ET.fromstring(catalogueData.decode("utf-8"))
            for catalogueItem in find_catalogueitems(tree, name=templateName):
                response = yield from client.request(
                    "GET", catalogueItem.attrib.get("href"),
                    headers=headers)
                catalogueItemData = yield from response.read_and_close()
                tree = ET.fromstring(catalogueItemData.decode("utf-8"))

                rv = next(find_templates(tree), None)
    return rv


def hosts(session, state=None):
    query = session.query(Appliance)
    if not state:
        return query.all()

    return [h for h in query.all() if h.changes[-1].state.name == state]


class Strategy:

    @staticmethod
    def config(providerName):
        return next((
            cfg for p in providers.values() for cfg in p
            if cfg["metadata"]["path"] == providerName),
            None
        )

    @staticmethod
    def recommend(host):  # TODO sort providers
        providerName = host.organisation.subscriptions[0].provider.name
        return Strategy.config(providerName)


class PreCheckAgent(Agent):

    CheckedAsOperational = namedtuple(
        "CheckedAsOperational",
        ["uuid", "ts", "provider", "ip", "creation", "power", "health"])

    CheckedAsPreOperational = namedtuple(
        "CheckedAsPreOperational",
        ["uuid", "ts", "provider", "ip", "creation", "power", "health"])

    CheckedAsProvisioning = namedtuple(
        "CheckedAsProvisioning",
        ["uuid", "ts", "provider", "ip", "creation", "power", "health"])

    @property
    def callbacks(self):
        return [
            (PreCheckAgent.CheckedAsOperational, self.touch_to_operational),
            (PreCheckAgent.CheckedAsPreOperational, self.touch_to_preoperational),
            (PreCheckAgent.CheckedAsProvisioning, self.touch_to_provisioning),
        ]

    def jobs(self, session):
        for app in session.query(Appliance).all():  # TODO: Filter earlier
            acts = app.changes
            if acts[-1].state.name == "pre_check":
                prvdrName = app.organisation.subscriptions[0].provider.name
                token = session.query(ProviderToken).join(Touch).join(
                    Provider).filter(Touch.actor == acts[0].actor).filter(
                    Provider.name == prvdrName).order_by(
                    desc(Touch.at)).first()
                creds = (prvdrName, token.key, token.value) if token else None
                    
                yield Job(app.uuid, creds, app)

    def touch_to_operational(self, msg:CheckedAsOperational, session):
        operational = session.query(ApplianceState).filter(
            ApplianceState.name == "operational").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(
            artifact=app, actor=actor, state=operational, at=msg.ts)
        resource = ProviderReport(
            creation=msg.creation, power=msg.power, health=msg.health,
            touch=act, provider=provider)
        session.add(resource)
        session.commit()
        return act

    def touch_to_preoperational(self, msg:CheckedAsPreOperational, session):
        preoperational = session.query(ApplianceState).filter(
            ApplianceState.name == "pre_operational").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(
            artifact=app, actor=actor, state=preoperational, at=msg.ts)
        ip = IPAddress(value=msg.ip, touch=act, provider=provider)
        report = ProviderReport(
            creation=msg.creation, power=msg.power, health=msg.health,
            touch=act, provider=provider)
        session.add_all((ip, report))
        session.commit()
        return act

    def touch_to_provisioning(self, msg:CheckedAsProvisioning, session):
        provisioning = session.query(ApplianceState).filter(
            ApplianceState.name == "provisioning").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(
            artifact=app, actor=actor, state=provisioning, at=msg.ts)
        resource = ProviderReport(
            creation=msg.creation, power=msg.power, health=msg.health,
            touch=act, provider=provider)
        session.add(resource)
        session.commit()
        return act

    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.appliance.precheck")
        log.info("Activated.")
        ET.register_namespace("", "http://www.vmware.com/vcloud/v1.5")
        while True:
            job = yield from self.work.get()
            log.debug(job)
            app = job.artifact
            resources = sorted(
                (r for c in app.changes for r in c.resources),
                key=operator.attrgetter("touch.at"),
                reverse=True)
            node = next((i for i in resources if isinstance(i, Node)), None)
            config = Strategy.config(node.provider.name)

            headers = {
                "Accept": "application/*+xml;version=5.5",
            }
            try:
                headers[job.token[1]] = job.token[2]
            except (TypeError, IndexError):
                log.warning("No token supplied")

            client = aiohttp.client.HttpClient(
                ["{host}:{port}".format(
                    host=config["host"]["name"],
                    port=config["host"]["port"])
                ],
                verify_ssl=config["host"].getboolean("verify_ssl_cert")
            )
            response = yield from client.request(
                "GET", node.uri, headers=headers)

            vApp = yield from response.read_and_close()
            log.debug(vApp)
            tree = ET.fromstring(vApp.decode("utf-8"))

            creation = "unknown"
            ipAddr = None
            messageType = PreCheckAgent.CheckedAsProvisioning
            try:
                scriptElement = next(find_customizationscript(tree))
            except StopIteration:
                # Not necessarily an error; possibly still provisioning
                log.warning("Missing customisation script")
            else:
                try:
                    nc = next(find_networkconnection(tree))
                except StopIteration:
                    log.debug("Missing network connection")
                    creation = "undeployed"
                else:
                    try:
                        ipAddr = next(
                            i for i in nc if i.tag.endswith("IpAddress")).text
                    except Exception as e:
                        log.error(e)

                script = unescape_script(scriptElement.text).splitlines()
                if len(script) > 5:
                    # Customisation script is in place
                    messageType = (PreCheckAgent.CheckedAsOperational if any(
                        i for i in resources
                        if i.touch.state.name == "operational")
                        else PreCheckAgent.CheckedAsPreOperational)

            if tree.attrib.get("deployed") == "true":
                creation = "deployed"

            msg = messageType(
                app.uuid, datetime.datetime.utcnow(),
                node.provider.name, ipAddr,
                creation, None, None
            )
            yield from msgQ.put(msg)


class PreDeleteAgent(Agent):

    Message = namedtuple(
        "DeletedMessage", ["uuid", "ts", "provider"])

    @property
    def callbacks(self):
        return [(PreDeleteAgent.Message, self.touch_to_deleted)]

    def jobs(self, session):
        for app in session.query(Appliance).all():  # TODO: Filter earlier
            acts = app.changes
            if acts[-1].state.name == "pre_delete":
                prvdrName = app.organisation.subscriptions[0].provider.name
                token = session.query(ProviderToken).join(Touch).join(
                    Provider).filter(Touch.actor == acts[0].actor).filter(
                    Provider.name == prvdrName).order_by(
                    desc(Touch.at)).first()
                creds = (prvdrName, token.key, token.value) if token else None
                    
                yield Job(app.uuid, creds, app)

    def touch_to_deleted(self, msg:Message, session):
        deleted = session.query(ApplianceState).filter(
            ApplianceState.name == "deleted").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(artifact=app, actor=actor, state=deleted, at=msg.ts)
        session.add(act)
        session.commit()
        return act

    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.appliance.predelete")
        log.info("Activated.")
        ET.register_namespace("", "http://www.vmware.com/vcloud/v1.5")
        while True:
            job = yield from self.work.get()
            app = job.artifact
            resources = sorted(
                (r for c in app.changes for r in c.resources),
                key=operator.attrgetter("touch.at"),
                reverse=True)
            node = next(i for i in resources if isinstance(i, Node))
            config = Strategy.config(node.provider.name)

            headers = {
                "Accept": "application/*+xml;version=5.5",
            }
            try:
                headers[job.token[1]] = job.token[2]
            except (TypeError, IndexError):
                log.warning("No token supplied")

            client = aiohttp.client.HttpClient(
                ["{host}:{port}".format(
                    host=config["host"]["name"],
                    port=config["host"]["port"])
                ],
                verify_ssl=config["host"].getboolean("verify_ssl_cert")
            )

            response = yield from client.request(
                "DELETE", node.uri,
                headers=headers)
            reply = yield from response.read_and_close()

            msg = PreDeleteAgent.Message(
                app.uuid, datetime.datetime.utcnow(),
                node.provider.name
            )
            yield from msgQ.put(msg)


class PreOperationalAgent(Agent):

    OperationalMessage = namedtuple(
        "OperationalMessage",
        ["uuid", "ts", "provider", "ip_internal", "ip_external"])

    ResourceConstrainedMessage = namedtuple(
        "ResourceConstrainedMessage",
        ["uuid", "ts", "provider", "ip_internal", "ip_external"])

    @property
    def callbacks(self):
        return [
            (PreOperationalAgent.OperationalMessage, self.touch_to_operational),
            (PreOperationalAgent.ResourceConstrainedMessage, self.touch_to_prestop),
        ]

    def jobs(self, session):
        for app in session.query(Appliance).all():  # TODO: Filter earlier
            acts = app.changes
            if acts[-1].state.name == "pre_operational":
                prvdrName = app.organisation.subscriptions[0].provider.name
                token = session.query(ProviderToken).join(Touch).join(
                    Provider).filter(Touch.actor == acts[0].actor).filter(
                    Provider.name == prvdrName).order_by(
                    desc(Touch.at)).first()
                creds = (prvdrName, token.key, token.value) if token else None
                    
                yield Job(app.uuid, creds, app)

    def touch_to_operational(self, msg:OperationalMessage, session):
        operational = session.query(ApplianceState).filter(
            ApplianceState.name == "operational").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(artifact=app, actor=actor, state=operational, at=msg.ts)

        if msg.ip_internal and msg.ip_external:
            resource = NATRouting(
                touch=act, provider=provider,
                ip_int=msg.ip_internal, ip_ext=msg.ip_external)
            session.add(resource)
        else:
            session.add(act)

        session.commit()
        return act

    def touch_to_prestop(self, msg:ResourceConstrainedMessage, session):
        prestop = session.query(ApplianceState).filter(
            ApplianceState.name == "pre_stop").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(artifact=app, actor=actor, state=prestop, at=msg.ts)
        session.add(act)
        session.commit()
        return act

    @asyncio.coroutine
    def __call__(self, loop, msgQ, session):
        log = logging.getLogger("cloudhands.burst.appliance.preoperation")
        log.info("Activated.")
        ET.register_namespace("", "http://www.vmware.com/vcloud/v1.5")
        natMacro = PageTemplateFile(pkg_resources.resource_filename(
            "cloudhands.burst.drivers", "NatRule.pt"))
        fwMacro = PageTemplateFile(pkg_resources.resource_filename(
            "cloudhands.burst.drivers", "FirewallRule.pt"))
        while True:
            job = yield from self.work.get()
            app = job.artifact
            resources = sorted(
                (r for c in app.changes for r in c.resources),
                key=operator.attrgetter("touch.at"),
                reverse=True)
            choice = next(i for i in resources if isinstance(i, CatalogueChoice))
            node = next(i for i in resources if isinstance(i, Node))
            config = Strategy.config(node.provider.name)
            network = config.get("vdc", "network", fallback=None)

            if not choice.natrouted:
                log.info("No rules applied for {} {}".format(
                    choice.name, app.uuid))
                msg = PreOperationalAgent.OperationalMessage(
                    app.uuid, datetime.datetime.utcnow(),
                    node.provider.name,
                    None, None
                )
                yield from msgQ.put(msg)
                continue

            log.info("Applying rules for {} {}".format(choice.name, app.uuid))
            try:
                privateIP = next(
                    i for i in resources if isinstance(i, IPAddress))
            except StopIteration:
                log.error("No IPAddress")
                continue
            else:
                log.debug(privateIP.value)

            subs = next(i for i in app.organisation.subscriptions
                        if i.provider.name == node.provider.name)
            ipPool = {r.value for c in subs.changes for r in c.resources
                             if isinstance(r, IPAddress)}
            ipTaken = {i.ip_ext for i in session.query(NATRouting).join(
                Provider).filter(Provider.name == node.provider.name).all()}
            ipFree = ipPool.difference(ipTaken)
            if not ipFree:
                log.warning("No public IP Addresses available")
                msg = PreOperationalAgent.ResourceConstrainedMessage(
                    app.uuid, datetime.datetime.utcnow(),
                    node.provider.name, privateIP.value, None
                )
                yield from msgQ.put(msg)
                continue
            else:
                log.info("Allocating from {}".format(ipFree))

            publicIP = session.query(IPAddress).filter(
                IPAddress.value == ipFree.pop()).first()

            headers = {
                "Accept": "application/*+xml;version=5.5",
            }
            try:
                headers[job.token[1]] = job.token[2]
            except (TypeError, IndexError):
                log.warning("No token supplied")

            client = aiohttp.client.HttpClient(
                ["{host}:{port}".format(
                    host=config["host"]["name"],
                    port=config["host"]["port"])
                ],
                verify_ssl=config["host"].getboolean("verify_ssl_cert")
            )

            url = "{scheme}://{host}:{port}/{endpoint}".format(
                scheme="https",
                host=config["host"]["name"],
                port=config["host"]["port"],
                endpoint="api/org")
            response = yield from client.request(
                "GET", url,
                headers=headers)

            orgList = yield from response.read_and_close()
            tree = ET.fromstring(orgList.decode("utf-8"))
            orgFound = find_orgs(tree, name=config["vdc"]["org"])

            try:
                org = next(orgFound)
            except StopIteration:
                log.error("Failed to find org")
                continue

            response = yield from client.request(
                "GET", org.attrib.get("href"),
                headers=headers)
            orgData = yield from response.read_and_close()
            tree = ET.fromstring(orgData.decode("utf-8"))
            try:
                vdcLink = next(find_vdcs(tree))
            except StopIteration:
                log.error("Failed to find VDC")
                continue

            response = yield from client.request(
                "GET", vdcLink.attrib.get("href"),
                headers=headers)
            vdcData = yield from response.read_and_close()
            tree = ET.fromstring(vdcData.decode("utf-8"))

            # Gateway details via query to vdc
            try:
                gwLink = next(
                    find_records(tree, rel="edgeGateways"))
            except StopIteration:
                log.error("Failed to find gateways")
                continue

            # Gateway data from link
            response = yield from client.request(
                "GET", gwLink.attrib.get("href"),
                headers=headers)
            gwData = yield from response.read_and_close()
            tree = ET.fromstring(gwData.decode("utf-8"))

            gwRecord = next(
                find_results(tree, name=config["gateway"]["name"]))

            response = yield from client.request(
                "GET", gwRecord.attrib.get("href"),
                headers=headers)
            gwData = yield from response.read_and_close()
            tree = ET.fromstring(gwData.decode("utf-8"))

            try:
                interface = next(
                    find_networkinterface(
                        tree, name=config["gateway"]["interface"]))
            except StopIteration:
                log.error("Failed to find network")

            try:
                eGSC = next(
                    c for i in tree if i.tag.endswith("Configuration")
                    for c in i
                    if c.tag.endswith("EdgeGatewayServiceConfiguration"))
            except StopIteration:
                log.error("Missing Edge gateway service configuration")
                continue

            try:
                natService = next(
                    i for i in eGSC if i.tag.endswith("NatService"))
            except StopIteration:
                natService = ET.XML(
                    """<NatService><IsEnabled>true</IsEnabled></NatService>""")
                eGSC.append(natService)

            try:
                fwService = next(
                    i for i in eGSC if i.tag.endswith("FirewallService"))
            except StopIteration:
                log.error("Failed to find firewall service")

            # SNAT rule already defined for entire subnet
            defn = {
                "typ": "DNAT",
                "network": {
                    "name": config["gateway"]["interface"],
                    "href": interface.attrib.get("href")
                },
                "rule": {
                    "rx": publicIP.value,
                    "tx": privateIP.value,
                },
                "description": "Public IP PNAT"
            }
            
            fwService.append(ET.XML(fwMacro(**defn)))
            natService.append(ET.XML(natMacro(**defn)))

            gwServiceCfgs = find_gatewayserviceconfiguration(tree)
            try:
                gwSCfg = next(gwServiceCfgs)
            except StopIteration:
                log.error("Failed to find gateway service configuration")

            url = gwSCfg.attrib.get("href")
            headers["Content-Type"] = (
                "application/vnd.vmware.admin.edgeGatewayServiceConfiguration+xml")
            response = yield from client.request(
                "POST", url,
                headers=headers,
                data=ET.tostring(eGSC, encoding="utf-8"))
            reply = yield from response.read_and_close()
            log.debug(reply)

            msg = PreOperationalAgent.OperationalMessage(
                app.uuid, datetime.datetime.utcnow(),
                node.provider.name,
                defn["rule"]["tx"], defn["rule"]["rx"]
            )
            yield from msgQ.put(msg)


class PreProvisionAgent(Agent):

    Message = namedtuple(
        "ProvisioningMessage", ["uuid", "ts", "provider", "uri"])

    @property
    def callbacks(self):
        return [(PreProvisionAgent.Message, self.touch_to_provisioning)]

    def jobs(self, session):
        for app in session.query(Appliance).all():  # TODO: Filter earlier
            acts = app.changes
            if acts[-1].state.name == "pre_provision":
                prvdrName = app.organisation.subscriptions[0].provider.name
                token = session.query(ProviderToken).join(Touch).join(
                    Provider).filter(Touch.actor == acts[0].actor).filter(
                    Provider.name == prvdrName).order_by(
                    desc(Touch.at)).first()
                creds = (prvdrName, token.key, token.value) if token else None
                    
                yield Job(app.uuid, creds, app)

    def touch_to_provisioning(self, msg:Message, session):
        provisioning = session.query(ApplianceState).filter(
            ApplianceState.name == "provisioning").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(artifact=app, actor=actor, state=provisioning, at=msg.ts)
        resource = Node(
            name="", touch=act, provider=provider,
            uri=msg.uri)
        session.add(resource)
        session.commit()
        return act
 
    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.appliance.preprovision")
        log.info("Activated.")
        ET.register_namespace("", "http://www.vmware.com/vcloud/v1.5")
        portalName, portal = next(iter(settings.items()))
        macro = PageTemplateFile(pkg_resources.resource_filename(
            "cloudhands.burst.drivers", "InstantiateVAppTemplateParams.pt"))
        macro = PageTemplateFile(pkg_resources.resource_filename(
            "cloudhands.burst.drivers", "ComposeVAppParams.pt"))
        while True:
            job = yield from self.work.get()
            app = job.artifact
            resources = sorted(
                (r for c in app.changes for r in c.resources),
                key=operator.attrgetter("touch.at"),
                reverse=True)
            label = next(i for i in resources if isinstance(i, Label))
            choice = next(i for i in resources if isinstance(i, CatalogueChoice))
            image = choice.name
            config = Strategy.recommend(app)

            headers = {
                "Accept": "application/*+xml;version=5.5",
            }
            try:
                headers[job.token[1]] = job.token[2]
            except (TypeError, IndexError):
                log.warning("No token supplied")

            client = aiohttp.client.HttpClient(
                ["{host}:{port}".format(
                    host=config["host"]["name"],
                    port=config["host"]["port"])
                ],
                verify_ssl=config["host"].getboolean("verify_ssl_cert")
            )

            # Find template among catalogues
            url = "{scheme}://{host}:{port}/{endpoint}".format(
                scheme="https",
                host=config["host"]["name"],
                port=config["host"]["port"],
                endpoint="api/catalogs/query")
            response = yield from client.request(
                "GET", url, headers=headers)
            data = yield from response.read_and_close()

            catalogues = [
                i for i in find_catalogrecords(data.decode("utf-8"))
                if i.attrib.get("name", None) in (
                    config["vdc"]["org"],
                    config["vdc"]["catalogue"]
                )
            ]
            template = yield from find_template_among_catalogues(
                client, headers, image, catalogues
            )
            if template is None:
                log.error("Couldn't find template {}".format(image))

            response = yield from client.request(
                "GET", template.get("href"),
                headers=headers)
            reply = yield from response.read_and_close()
            log.debug(reply)
            tree = ET.fromstring(reply.decode("utf-8"))

            script = customizationScript.format(
                host=portal["auth.rest"]["host"],
                uuid=app.uuid)

            vmConfigs = []
            for vm in find_vms(tree):
                ncs = next(find_networkconnectionsection(tree), None)
                if ncs is None:
                    log.error("Couldn't find network connection section")
                vmConfigs.append({
                    "href": vm.attrib.get("href"),
                    "name": uuid.uuid4().hex,
                    "networks": [
                        {"name": nc.attrib.get("network")}
                        for nc in find_networkconnection(vm)
                    ],
                    "script": script})

            # VDC details from organisation
            url = "{scheme}://{host}:{port}/{endpoint}".format(
                scheme="https",
                host=config["host"]["name"],
                port=config["host"]["port"],
                endpoint="api/org")
            response = yield from client.request(
                "GET", url,
                headers=headers)
            orgList = yield from response.read_and_close()
            tree = ET.fromstring(orgList.decode("utf-8"))

            userOrg = next(find_orgs(tree, name=config["vdc"]["org"]), None)
            response = yield from client.request(
                "GET", userOrg.attrib.get("href"),
                headers=headers)
            orgData = yield from response.read_and_close()
            tree = ET.fromstring(orgData.decode("utf-8"))
            try:
                vdcLink = next(find_vdcs(tree))
            except StopIteration:
                log.error("Failed to find VDC")

            response = yield from client.request(
                "GET", vdcLink.attrib.get("href"),
                headers=headers)
            vdcData = yield from response.read_and_close()
            tree = ET.fromstring(vdcData.decode("utf-8"))

            # Network details via query to vdc
            try:
                netLink = next(
                    find_records(tree, rel="orgVdcNetworks"))
            except StopIteration:
                log.error("Failed to find network")
            response = yield from client.request(
                "GET", netLink.attrib.get("href"),
                headers=headers)
            netData = yield from response.read_and_close()
            tree = ET.fromstring(netData.decode("utf-8"))
            netDetails = [
                next(find_results(tree, name=name), None)
                for n, name in sorted(config.items("network"))]

            try:
                data = {
                    "appliance": {
                        "name": label.name,
                        "description": "FIXME: Description",
                        "vms": vmConfigs,
                    },
                    "networks": [{
                        "name": net.attrib.get("name"),
                        "href": net.attrib.get("href"),
                    } for net in netDetails],
                    "template": {
                        "name": template.attrib.get("name"),
                        "href": template.attrib.get("href"),
                    },
                }

                url = "{vdc}/{endpoint}".format(
                    vdc=vdcLink.attrib.get("href"),
                    endpoint="action/composeVApp")
                headers["Content-Type"] = (
                "application/vnd.vmware.vcloud.instantiateVAppTemplateParams+xml")
                headers["Content-Type"] = (
                "application/vnd.vmware.vcloud.composeVAppParams+xml")
                payload = macro(**data)
                log.debug(payload)
            except Exception as e:
                log.error(e)

            response = yield from client.request(
                "POST", url,
                headers=headers,
                data=payload.encode("utf-8"))
            reply = yield from response.read_and_close()
            log.debug(reply)

            tree = ET.fromstring(reply.decode("utf-8"))
            try:
                vApp = next(find_xpath(".", tree, name=label.name))
            except StopIteration:
                #TODO: Check error for duplicate, take action
                log.error("Failed to find vapp")
            else:

                msg = PreProvisionAgent.Message(
                    app.uuid, datetime.datetime.utcnow(),
                    config["metadata"]["path"],
                    vApp.attrib.get("href")
                )
                yield from msgQ.put(msg)


class ProvisioningAgent(Agent):

    Message = namedtuple("CheckRequiredMessage", ["uuid", "ts"])

    @property
    def callbacks(self):
        return [
            (ProvisioningAgent.Message, self.touch_to_precheck),
        ]

    def jobs(self, session):
        # TODO: get token (need user registration ProviderToken)
        now = datetime.datetime.utcnow()
        then = now - datetime.timedelta(seconds=20)
        for app in session.query(Appliance).all():  # TODO: Filter earlier
            acts = app.changes
            if acts[-1].state.name == "provisioning" and acts[-1].at < then:
                prvdrName = app.organisation.subscriptions[0].provider.name
                token = session.query(ProviderToken).join(Touch).join(
                    Provider).filter(Touch.actor == acts[0].actor).filter(
                    Provider.name == prvdrName).order_by(
                    desc(Touch.at)).first()
                creds = (prvdrName, token.key, token.value) if token else None
                    
                yield Job(app.uuid, creds, app)

    def touch_to_precheck(self, msg:Message, session):
        precheck = session.query(ApplianceState).filter(
            ApplianceState.name == "pre_check").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        act = Touch(artifact=app, actor=actor, state=precheck, at=msg.ts)
        session.add(act)
        session.commit()
        return act
 
    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.appliance.provisioning")
        log.info("Activated.")
        while True:
            job = yield from self.work.get()
            log.debug(job)

            app = job.artifact
            resources = sorted(
                (r for c in app.changes for r in c.resources),
                key=operator.attrgetter("touch.at"),
                reverse=True)
            node = next((i for i in resources if isinstance(i, Node)), None)
            choice = next((i for i in resources
                          if isinstance(i, CatalogueChoice)), None)

            if not (node and choice):
                log.error("Missing data for new node")

            config = Strategy.config(node.provider.name)

            headers = {
                "Accept": "application/*+xml;version=5.5",
            }
            try:
                headers[job.token[1]] = job.token[2]
            except (TypeError, IndexError):
                log.warning("No token supplied")

            client = aiohttp.client.HttpClient(
                ["{host}:{port}".format(
                    host=config["host"]["name"],
                    port=config["host"]["port"])
                ],
                verify_ssl=config["host"].getboolean("verify_ssl_cert")
            )

            response = yield from client.request(
                "GET", node.uri, headers=headers)
            reply = yield from response.read_and_close()
            tree = ET.fromstring(reply.decode("utf-8"))

            try:
                sectionElement = next(find_customizationsection(tree))
            except StopIteration:
                log.warning("Missing customisation script")

            msg = ProvisioningAgent.Message(
                job.uuid, datetime.datetime.utcnow())
            yield from msgQ.put(msg)


class PreStartAgent(Agent):

    Message = namedtuple(
        "OperationalMessage", ["uuid", "ts", "provider"])

    @property
    def callbacks(self):
        return [(PreStartAgent.Message, self.touch_to_running)]

    def jobs(self, session):
        for app in session.query(Appliance).all():  # TODO: Filter earlier
            acts = app.changes
            if acts[-1].state.name == "pre_start":
                prvdrName = app.organisation.subscriptions[0].provider.name
                token = session.query(ProviderToken).join(Touch).join(
                    Provider).filter(Touch.actor == acts[0].actor).filter(
                    Provider.name == prvdrName).order_by(
                    desc(Touch.at)).first()
                creds = (prvdrName, token.key, token.value) if token else None
                    
                yield Job(app.uuid, creds, app)

    def touch_to_running(self, msg:Message, session):
        running = session.query(ApplianceState).filter(
            ApplianceState.name == "running").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(artifact=app, actor=actor, state=running, at=msg.ts)
        session.add(act)
        session.commit()
        return act

    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.appliance.prestart")
        log.info("Activated.")
        ET.register_namespace("", "http://www.vmware.com/vcloud/v1.5")
        while True:
            job = yield from self.work.get()
            try:
                app = job.artifact
                resources = sorted(
                    (r for c in app.changes for r in c.resources),
                    key=operator.attrgetter("touch.at"),
                    reverse=True)
                node = next(i for i in resources if isinstance(i, Node))
                config = Strategy.config(node.provider.name)

                headers = {
                    "Accept": "application/*+xml;version=5.5",
                }
                try:
                    headers[job.token[1]] = job.token[2]
                except (TypeError, IndexError):
                    log.warning("No token supplied")

                client = aiohttp.client.HttpClient(
                    ["{host}:{port}".format(
                        host=config["host"]["name"],
                        port=config["host"]["port"])
                    ],
                    verify_ssl=config["host"].getboolean("verify_ssl_cert")
                )

                deploy = textwrap.dedent("""
                <DeployVAppParams xmlns="http://www.vmware.com/vcloud/v1.5"
                powerOn="true" />
                """)
                url = "{}/action/deploy".format(node.uri)
                headers["Content-Type"] = (
                    "application/vnd.vmware.vcloud.deployVAppParams+xml")
                response = yield from client.request(
                    "POST", url,
                    headers=headers,
                    data=deploy.encode("utf-8"))
                reply = yield from response.read_and_close()

            except Exception as e:
                log.error(e)
                continue

            msg = PreStartAgent.Message(
                app.uuid, datetime.datetime.utcnow(),
                node.provider.name
            )
            yield from msgQ.put(msg)


class PreStopAgent(Agent):

    Message = namedtuple(
        "StoppedMessage", ["uuid", "ts", "provider"])

    @property
    def callbacks(self):
        return [(PreStopAgent.Message, self.touch_to_stopped)]

    def jobs(self, session):
        for app in session.query(Appliance).all():  # TODO: Filter earlier
            acts = app.changes
            if acts[-1].state.name == "pre_stop":
                prvdrName = app.organisation.subscriptions[0].provider.name
                token = session.query(ProviderToken).join(Touch).join(
                    Provider).filter(Touch.actor == acts[0].actor).filter(
                    Provider.name == prvdrName).order_by(
                    desc(Touch.at)).first()
                creds = (prvdrName, token.key, token.value) if token else None
                    
                yield Job(app.uuid, creds, app)

    def touch_to_stopped(self, msg:Message, session):
        stopped = session.query(ApplianceState).filter(
            ApplianceState.name == "stopped").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(artifact=app, actor=actor, state=stopped, at=msg.ts)
        session.add(act)
        session.commit()
        return act

    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.appliance.prestop")
        log.info("Activated.")
        ET.register_namespace("", "http://www.vmware.com/vcloud/v1.5")
        while True:
            job = yield from self.work.get()
            app = job.artifact
            resources = sorted(
                (r for c in app.changes for r in c.resources),
                key=operator.attrgetter("touch.at"),
                reverse=True)
            node = next(i for i in resources if isinstance(i, Node))
            config = Strategy.config(node.provider.name)

            headers = {
                "Accept": "application/*+xml;version=5.5",
            }
            try:
                headers[job.token[1]] = job.token[2]
            except (TypeError, IndexError):
                log.warning("No token supplied")

            client = aiohttp.client.HttpClient(
                ["{host}:{port}".format(
                    host=config["host"]["name"],
                    port=config["host"]["port"])
                ],
                verify_ssl=config["host"].getboolean("verify_ssl_cert")
            )

            unDeploy = textwrap.dedent("""
            <UndeployVAppParams xmlns="http://www.vmware.com/vcloud/v1.5">
            <UndeployPowerAction>powerOff</UndeployPowerAction>
            </UndeployVAppParams>
            """)
            url = "{}/action/undeploy".format(node.uri)
            headers["Content-Type"] = (
                "application/vnd.vmware.vcloud.undeployVAppParams+xml")
            response = yield from client.request(
                "POST", url,
                headers=headers,
                data=unDeploy.encode("utf-8"))
            reply = yield from response.read_and_close()

            msg = PreStopAgent.Message(
                app.uuid, datetime.datetime.utcnow(),
                node.provider.name
            )
            yield from msgQ.put(msg)
