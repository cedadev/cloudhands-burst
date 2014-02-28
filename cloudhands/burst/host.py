#!/usr/bin/env python
# encoding: UTF-8

import concurrent.futures
import datetime
import logging

from cloudhands.burst.control import create_node
from cloudhands.burst.control import destroy_node
from cloudhands.common.discovery import providers
from cloudhands.common.fsm import HostState
from cloudhands.common.schema import Host
from cloudhands.common.schema import Node
from cloudhands.common.schema import Provider
from cloudhands.common.schema import Touch


def hosts(session, state=None):
    query = session.query(Host)
    if not state:
        return query.all()

    return [h for h in query.all() if h.changes[-1].state.name == state]


class Strategy(object):

    def recommend(host):  # TODO sort providers
        providerName = host.organisation.subscriptions[0].provider.name
        for config in [
            cfg for p in providers.values() for cfg in p
            if cfg["metadata"]["path"] == providerName
        ]:
            return config
        else:
            return None


class HostAgent():

    def touch_requested(session):
        log = logging.getLogger("cloudhands.burst.host.touch_requested")
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exctr:
            jobs = {
                exctr.submit(
                    create_node,
                    config=Strategy.recommend(h),
                    name=h.name): h for h in hosts(session, state="requested")}

            now = datetime.datetime.utcnow()
            scheduling = session.query(HostState).filter(
                HostState.name == "scheduling").one()
            for host in jobs.values():
                user = host.changes[-1].actor
                host.changes.append(
                    Touch(artifact=host, actor=user, state=scheduling, at=now))
                session.commit()
                log.info("{} is scheduling".format(host.name))

            requested = session.query(HostState).filter(
                HostState.name == "requested").one()
            unknown = session.query(HostState).filter(
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
                    provider = session.query(Provider).filter(
                        Provider.name==config["metadata"]["path"]).one()
                    act = Touch(
                        artifact=host, actor=user, state=unknown, at=now)
                    resource = Node(
                        name=host.name, touch=act, provider=provider,
                        uri=node.id)
                    session.add(resource)
                    log.info("{} created: {}".format(host.name, node.id))
                host.changes.append(act)
                session.commit()
                yield act

    def touch_deleting(session):
        log = logging.getLogger("cloudhands.burst.host.touch_deleting")
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exctr:
            jobs = {
                exctr.submit(
                    destroy_node,
                    config=Strategy.recommend(h), # FIXME
                    uri=r.uri): r for h in hosts(session, state="deleting")
                    for t in h.changes for r in t.resources
                    if isinstance(r, Node)}

            for host in jobs.values():
                log.info("{} is going down".format(host.name))

            deleting = session.query(HostState).filter(
                HostState.name == "deleting").one()
            down = session.query(HostState).filter(
                HostState.name == "down").one()
            unknown = session.query(HostState).filter(
                HostState.name == "unknown").one()

            for job in concurrent.futures.as_completed(jobs):
                host = jobs[job]
                user = host.changes[-1].actor
                config, node = job.result()
                now = datetime.datetime.utcnow()
                if node:
                    act = Touch(
                        artifact=host, actor=user, state=deleting, at=now)
                    log.info("{} still deleting ({}).".format(host.name, node.id))
                else:
                    act = Touch(
                        artifact=host, actor=user, state=down, at=now)
                    log.info("{} down".format(host.name))
                host.changes.append(act)
                session.commit()
                yield act
