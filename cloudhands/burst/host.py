#!/usr/bin/env python
# encoding: UTF-8

from collections import deque
import concurrent.futures
import datetime
import logging

from cloudhands.burst.control import create_node
from cloudhands.burst.control import destroy_node
from cloudhands.common.discovery import providers
from cloudhands.common.fsm import HostState
from cloudhands.common.schema import Host
from cloudhands.common.schema import Node
from cloudhands.common.schema import OSImage
from cloudhands.common.schema import Provider
from cloudhands.common.schema import Touch


def hosts(session, state=None):
    query = session.query(Host)
    if not state:
        return query.all()

    return [h for h in query.all() if h.changes[-1].state.name == state]


class Strategy:

    @staticmethod
    def recommend(host):  # TODO sort providers
        providerName = host.organisation.subscriptions[0].provider.name
        for config in [
            cfg for p in providers.values() for cfg in p
            if cfg["metadata"]["path"] == providerName
        ]:
            return config
        else:
            return None


class HostAgent:

    _shared_state = {}

    def __init__(self, args, config, session, loop=None):
        self.__dict__ = self._shared_state
        if not hasattr(self, "loop"):
            self.q = deque(maxlen=256)
            self.args = args
            self.config = config
            self.session = session
            self.loop = loop

    def touch_requested(self, priority=1):
        log = logging.getLogger("cloudhands.burst.host.touch_requested")
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exctr:
            jobs = {}
            for h in hosts(self.session, state="requested"):
                name = h.name
                config=Strategy.recommend(h)
                imgs = [r for r in h.changes[0].resources if isinstance(r, OSImage)]
                job = exctr.submit(
                    create_node,
                    config=config,
                    name=h.name,
                    image=imgs[0].name if rsrc else None)
                jobs[job] = h

            now = datetime.datetime.utcnow()
            scheduling = self.session.query(HostState).filter(
                HostState.name == "scheduling").one()
            for host in jobs.values():
                user = host.changes[-1].actor
                host.changes.append(
                    Touch(artifact=host, actor=user, state=scheduling, at=now))
                self.session.commit()
                log.info("{} is scheduling".format(host.name))

            requested = self.session.query(HostState).filter(
                HostState.name == "requested").one()
            unknown = self.session.query(HostState).filter(
                HostState.name == "unknown").one()
            for job in concurrent.futures.as_completed(jobs):
                host = jobs[job]
                user = host.changes[-1].actor
                config, node = job.result()
                now = datetime.datetime.utcnow()
                if not node:
                    act = Touch(
                        artifact=host, actor=user, state=requested, at=now)
                    log.info("{} re-requested.".format(host.name))
                else:
                    provider = self.session.query(Provider).filter(
                        Provider.name==config["metadata"]["path"]).one()
                    act = Touch(
                        artifact=host, actor=user, state=unknown, at=now)
                    resource = Node(
                        name=host.name, touch=act, provider=provider,
                        uri=node.id)
                    self.session.add(resource)
                    log.info("{} created: {}".format(host.name, node.id))
                host.changes.append(act)
                self.session.commit()
                self.q.append(act)

        if self.loop is not None:
            log.debug("Rescheduling {}s later".format(self.args.interval))
            self.loop.enter(self.args.interval, priority, self.touch_requested)

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

            deleting = self.session.query(HostState).filter(
                HostState.name == "deleting").one()
            down = self.session.query(HostState).filter(
                HostState.name == "down").one()
            unknown = self.session.query(HostState).filter(
                HostState.name == "unknown").one()

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
