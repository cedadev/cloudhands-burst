#!/usr/bin/env python
# encoding: UTF-8

import concurrent.futures
import datetime
import logging

from cloudhands.burst.control import create_node

from cloudhands.common.fsm import HostState
from cloudhands.common.schema import Host
from cloudhands.common.schema import Node
from cloudhands.common.schema import Touch


def hosts(session, state=None):
    query = session.query(Host)
    if not state:
        return query.all()

    return [h for h in query.all() if h.changes[-1].state.name == state]


class HostAgent():

    def touch_requested(session):
        log = logging.getLogger("cloudhands.burst.agents.HostAgent")
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exctr:
            jobs = {
                exctr.submit(create_node, name=h.name): h for h in hosts(
                    session, state="requested")}

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
                provider, node = job.result()
                now = datetime.datetime.utcnow()
                if not node:
                    act = Touch(
                        artifact=host, actor=user, state=requested, at=now)
                    log.info("{} re-requested.".format(host.name))
                else:
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
