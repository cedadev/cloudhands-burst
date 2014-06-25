#!/usr/bin/env python
# encoding: UTF-8

from collections import deque
from collections import namedtuple
import concurrent.futures
import datetime
import logging

from cloudhands.burst.agent import Agent
from cloudhands.burst.control import create_node
from cloudhands.burst.control import describe_node
from cloudhands.burst.control import destroy_node
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
from cloudhands.common.schema import Touch


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


class PreProvisionAgent(Agent):

    Message = namedtuple("ProvisioningMessage", ["content"])

    @property
    def callbacks(self):
        return [(PreProvisionAgent.Message, self.touch_to_provisioning)]

    def touch_to_provisioning(self, msg:Message, session):
        print(msg)
    
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
