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
import xml.etree.ElementTree as ET

import aiohttp
from chameleon import PageTemplateFile
import pkg_resources

from cloudhands.burst.agent import Agent
from cloudhands.burst.agent import Job
from cloudhands.burst.control import create_node
from cloudhands.burst.control import describe_node
from cloudhands.burst.control import destroy_node
from cloudhands.burst.utils import find_xpath
from cloudhands.common.discovery import providers
from cloudhands.common.fsm import ApplianceState
from cloudhands.common.schema import Appliance
from cloudhands.common.schema import CatalogueChoice
from cloudhands.common.schema import Component
from cloudhands.common.schema import IPAddress
from cloudhands.common.schema import Label
from cloudhands.common.schema import Node
from cloudhands.common.schema import OSImage
from cloudhands.common.schema import Provider
from cloudhands.common.schema import ProviderReport
from cloudhands.common.schema import Touch

find_catalogueitems = functools.partial(
    find_xpath, ".//*[@type='application/vnd.vmware.vcloud.catalogItem+xml']",
    namespaces={"": "http://www.vmware.com/vcloud/v1.5"})

find_catalogues = functools.partial(
    find_xpath, "./*/[@type='application/vnd.vmware.vcloud.catalog+xml']")

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



def hosts(session, state=None):
    query = session.query(Appliance)
    if not state:
        return query.all()

    return [h for h in query.all() if h.changes[-1].state.name == state]


class Strategy:

    @staticmethod
    def config(providerName):
        for config in [
            cfg for p in providers.values() for cfg in p
            if cfg["metadata"]["path"] == providerName
        ]:
            return config
        else:
            return None

    @staticmethod
    def recommend(host):  # TODO sort providers
        providerName = host.organisation.subscriptions[0].provider.name
        return Strategy.config(providerName)


class PreCheckAgent(Agent):

    CheckedAsOperational = namedtuple(
        "CheckedAsOperational",
        ["uuid", "ts", "provider", "creation", "power", "health"])

    CheckedAsPreOperational = namedtuple(
        "CheckedAsPreOperational",
        ["uuid", "ts", "provider", "creation", "power", "health"])

    CheckedAsProvisioning = namedtuple(
        "CheckedAsProvisioning",
        ["uuid", "ts", "provider", "creation", "power", "health"])

    @property
    def callbacks(self):
        # TODO: CheckedAsProvisioning
        return [
            (PreCheckAgent.CheckedAsOperational, self.touch_to_operational),
            (PreCheckAgent.CheckedAsPreOperational, self.touch_to_preoperational),
        ]

    def jobs(self, session):
        return [Job(i.uuid, None, i) for i in session.query(Appliance).all()
                if i.changes[-1].state.name == "pre_check"]

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
        resource = ProviderReport(
            creation=msg.creation, power=msg.power, health=msg.health,
            touch=act, provider=provider)
        session.add(resource)
        session.commit()
        return act

    @asyncio.coroutine
    def __call__(self, loop, msgQ):
        log = logging.getLogger("cloudhands.burst.appliance.precheck")
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

            messageType = (PreCheckAgent.CheckedAsOperational if any(
                i for i in resources if i.touch.state.name == "operational")
                else PreCheckAgent.CheckedAsPreOperational)


            msg = messageType(
                app.uuid, datetime.datetime.utcnow(),
                node.provider.name,
                None, None, None
            )
            log.debug(msg)
            yield from msgQ.put(msg)


class PreProvisionAgent(Agent):

    Message = namedtuple(
        "ProvisioningMessage", ["uuid", "ts", "provider", "uri"])

    @property
    def callbacks(self):
        return [(PreProvisionAgent.Message, self.touch_to_provisioning)]

    def jobs(self, session):
        return [Job(i.uuid, None, i) for i in session.query(Appliance).all()
                if i.changes[-1].state.name == "pre_provision"]

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
    def __call__(self, loop, msgQ):
        log = logging.getLogger("cloudhands.burst.appliance.preprovision")
        log.info("Activated.")
        ET.register_namespace("", "http://www.vmware.com/vcloud/v1.5")
        macro = PageTemplateFile(pkg_resources.resource_filename(
            "cloudhands.burst.drivers", "InstantiateVAppTemplateParams.pt"))
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
            network = config.get("vdc", "network", fallback=None)

            # FIXME: Tokens to be maintained in database. Start of login code
            url = "{scheme}://{host}:{port}/{endpoint}".format(
                scheme="https",
                host=config["host"]["name"],
                port=config["host"]["port"],
                endpoint="api/sessions")

            headers = {
                "Accept": "application/*+xml;version=5.5",
            }

            client = aiohttp.client.HttpClient(
                ["{host}:{port}".format(
                    host=config["host"]["name"],
                    port=config["host"]["port"])
                ],
                verify_ssl=config["host"].getboolean("verify_ssl_cert")
            )

            response = yield from client.request(
                "POST", url,
                auth=(config["user"]["name"], config["user"]["pass"]),
                headers=headers)
                #connector=connector)
                #request_class=requestClass)
            headers["x-vcloud-authorization"] = response.headers.get(
                "x-vcloud-authorization")


            # FIXME: End of login code

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
                log.error(orgFound)

            response = yield from client.request(
                "GET", org.attrib.get("href"),
                headers=headers)
            orgData = yield from response.read_and_close()
            tree = ET.fromstring(orgData.decode("utf-8"))
            try:
                vdcLink = next(find_vdcs(tree))
            except StopIteration:
                log.error("Failed to find VDC")

            try:
                catalogue = next(
                    find_catalogues(tree, name="Public catalog"))
            except StopIteration:
                log.error("Failed to find catalogue")

            response = yield from client.request(
                "GET", catalogue.attrib.get("href"),
                headers=headers)
            catalogueData = yield from response.read_and_close()
            tree = ET.fromstring(catalogueData.decode("utf-8"))
            try:
                # FIXME:
                catalogueItem = next(
                    find_catalogueitems(tree, name="centos6-stemcell"))
            except StopIteration:
                log.error("Failed to find catalogue item")
            response = yield from client.request(
                "GET", catalogueItem.attrib.get("href"),
                headers=headers)
            catalogueItemData = yield from response.read_and_close()
            tree = ET.fromstring(catalogueItemData.decode("utf-8"))

            # FIXME: a fudge for the demo
            templates = list(find_templates(tree))
            log.debug(templates)
            try:
                template = templates[0]
            except IndexError:
                log.error("Failed to find template")
                ET.dump(tree)
 
            # Can also finding templates in VDC
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
            netDetails = next(
                find_results(tree, name=config["vdc"]["network"]))

            data = {
                "appliance": {
                    "name": label.name,
                    "description": "FIXME: Description",
                },
                "network": {
                    "name": config["vdc"]["network"],
                    "href": netDetails.attrib.get("href"),
                },
                "template": {
                    "name": template.attrib.get("name"),
                    "href": template.attrib.get("href"),
                }
            }

            url = "{vdc}/{endpoint}".format(
                vdc=vdcLink.attrib.get("href"),
                endpoint="action/instantiateVAppTemplate")
            headers["Content-Type"] = (
            "application/vnd.vmware.vcloud.instantiateVAppTemplateParams+xml")
            payload = macro(**data)

            response = yield from client.request(
                "POST", url,
                headers=headers,
                data=payload.encode("utf-8"))
            reply = yield from response.read_and_close()

            tree = ET.fromstring(reply.decode("utf-8"))
            try:
                vApp = next(find_xpath(".", tree, name=label.name))
            except StopIteration:
                #TODO: Check error for duplicate, take action
                log.error("Failed to find vapp")
            else:
                log.debug(vApp.attrib.get("href"))

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
        now = datetime.datetime.utcnow()
        then = now - datetime.timedelta(seconds=20)
        return [Job(i.uuid, None, i) for i in session.query(Appliance).all()
                if i.changes[-1].state.name == "provisioning"
                and i.changes[-1].at < then]

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
    def __call__(self, loop, msgQ):
        log = logging.getLogger("cloudhands.burst.appliance.provisioning")
        log.info("Activated.")
        while True:
            job = yield from self.work.get()

            msg = ProvisioningAgent.Message(
                job.uuid, datetime.datetime.utcnow())
            yield from msgQ.put(msg)


### Old code below for deletion ####
class ApplianceAgent:

    _shared_state = {}

    def __init__(self, args, config, session, loop=None):
        self.__dict__ = self._shared_state
        if not hasattr(self, "loop"):
            self.q = deque(maxlen=256)
            self.args = args
            self.config = config
            self.session = session
            self.loop = loop

    def touch_pre_provision(self, priority=1):
        log = logging.getLogger("cloudhands.burst.host.touch_pre_provision")
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exctr:
            jobs = {}
            apps = [i for i in self.session.query(Appliance).all()
                    if i.changes[-1].state.name == "pre_provision"]
            for app in apps:
                label = self.session.query(Label).join(Touch).join(Appliance).filter(
                    Appliance.id == app.id).first()
                image = self.session.query(CatalogueChoice).join(Touch).join(
                    Appliance).filter(Appliance.id == app.id).first()
                config = Strategy.recommend(app)
                network = config.get("vdc", "network", fallback=None)
                job = exctr.submit(
                    create_node,
                    config=config,
                    name=label.name,
                    image=image.name if image else None,
                    network=network)
                jobs[job] = app

            now = datetime.datetime.utcnow()
            provisioning = self.session.query(ApplianceState).filter(
                ApplianceState.name == "provisioning").one()
            for app in jobs.values():
                user = app.changes[-1].actor
                app.changes.append(
                    Touch(artifact=app, actor=user, state=provisioning, at=now))
                self.session.commit()
                log.info("Appliance {} is provisioning".format(app.uuid))

            pre_operational = self.session.query(ApplianceState).filter(
                ApplianceState.name == "pre_operational").one()
            pre_provision = self.session.query(ApplianceState).filter(
                ApplianceState.name == "pre_provision").one()
            for job in concurrent.futures.as_completed(jobs):
                app = jobs[job]
                user = app.changes[-1].actor
                config, node = job.result()
                now = datetime.datetime.utcnow()
                if not node:
                    act = Touch(
                        artifact=app, actor=user, state=pre_provision, at=now)
                    log.info("{} re-requested.".format(app.name))
                else:
                    label = self.session.query(Label).join(Touch).join(Appliance).filter(
                        Appliance.id == app.id).first()
                    provider = self.session.query(Provider).filter(
                        Provider.name==config["metadata"]["path"]).one()
                    act = Touch(
                        artifact=app, actor=user, state=pre_operational, at=now)
                    resource = Node(
                        name=label.name, touch=act, provider=provider,
                        uri=node.id)
                    self.session.add(resource)
                    log.info("{} created: {}".format(label.name, node.id))
                app.changes.append(act)
                self.session.commit()
                self.q.append(act)

        if self.loop is not None:
            log.debug("Rescheduling {}s later".format(self.args.interval))
            self.loop.enter(
                self.args.interval, priority, self.touch_pre_provision)

    def touch_pre_operational(self, priority=1):
        log = logging.getLogger("cloudhands.burst.host.touch_pre_operational")

        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exctr:
            jobs = {}
            apps = [i for i in self.session.query(Appliance).all()
                    if i.changes[-1].state.name == "pre_operational"]

            for app in apps:
                #label = self.session.query(Label).join(Touch).join(Appliance).filter(
                #    Appliance.id == app.id).first()
                node = self.session.query(Node).join(Touch).join(Appliance).filter(
                    Appliance.id == app.id).first()
                job = exctr.submit(
                    describe_node,
                    config=Strategy.config(node.provider.name),
                    uri=node.uri)
                jobs[job] = node

            actor = self.session.query(Component).filter(
                Component.handle=="burst.controller").one()
            operational = self.session.query(ApplianceState).filter(
                ApplianceState.name == "operational").one()

            for job in concurrent.futures.as_completed(jobs):
                node = jobs[job]
                user = app.changes[-1].actor
                (ips,) = job.result()

                now = datetime.datetime.utcnow()
                act = Touch(
                    artifact=node.touch.artifact,
                    actor=actor, state=operational, at=now)
                for addr in ips:
                    ip = IPAddress(value=addr, touch=act, provider=node.provider)
                    self.session.add(ip)
                self.session.commit()

        if self.loop is not None:
            log.debug("Rescheduling {}s later".format(self.args.interval))
            self.loop.enter(
                self.args.interval, priority, self.touch_pre_operational)

    def touch_deleting(self, priority=1):
        log = logging.getLogger("cloudhands.burst.host.touch_deleting")
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exctr:
            jobs = {
                exctr.submit(
                    destroy_node,
                    config=Strategy.recommend(h), # FIXME
                    uri=r.uri): r for h in hosts(self.session, state="deleting")
                    for t in h.changes for r in t.resources
                    if isinstance(r, Node)}

            for node in jobs.values():
                log.info("{} is going down".format(node.name))

            deleting = self.session.query(ApplianceState).filter(
                ApplianceState.name == "deleting").one()
            down = self.session.query(ApplianceState).filter(
                ApplianceState.name == "down").one()
            unknown = self.session.query(ApplianceState).filter(
                ApplianceState.name == "unknown").one()

            for job in concurrent.futures.as_completed(jobs):
                node = jobs[job]
                host = node.touch.artifact
                user = node.touch.actor
                config, uri = job.result()
                now = datetime.datetime.utcnow()
                if uri:
                    act = Touch(
                        artifact=host, actor=user, state=down, at=now)
                    log.info("{} down".format(host.name))
                else:
                    act = Touch(
                        artifact=host, actor=user, state=deleting, at=now)
                    log.info("{} still deleting ({}).".format(host.name, node.id))
                host.changes.append(act)
                self.session.commit()
                self.q.append(act)

        if self.loop is not None:
            log.debug("Rescheduling {}s later".format(self.args.interval))
            self.loop.enter(self.args.interval, priority, self.touch_deleting)
