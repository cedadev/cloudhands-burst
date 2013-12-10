#!/usr/bin/env python
# encoding: UTF-8

import datetime
import logging
import uuid

from cloudhands.burst.control import Strategy
from cloudhands.common.fsm import HostState
from cloudhands.common.schema import Host
from cloudhands.common.schema import Node
from cloudhands.common.schema import Touch
from cloudhands.web.tricks import allocate_ip


class BurstFixture(object):

    def load_resources_for_user(session, user, nodes):
        log = logging.getLogger("cloudhands.web.demo")
        provider, conn = Strategy.recommend()
        for jvo, hostname, status, addr in nodes:
            host = session.query(
                Host).filter(Host.name == hostname).first()
            if not host:
                continue

            now = datetime.datetime.utcnow()
            scheduling = session.query(HostState).filter(
                HostState.name == "scheduling").one()
            host.changes.append(
                Touch(artifact=host, actor=user, state=scheduling, at=now))
            session.commit()

            # 2. Burst controller raises a node
            now = datetime.datetime.utcnow()
            act = Touch(artifact=host, actor=user, state=scheduling, at=now)
            host.changes.append(act)
            node = Node(name=host.name, touch=act, provider=provider)
            session.add(node)
            session.commit()

            # 3. Burst controller allocates an IP
            ip = allocate_ip(session, host, addr)

            # 4. Burst controller marks Host with operating state
            now = datetime.datetime.utcnow()
            state = session.query(HostState).filter(
                HostState.name == status).one()
            host.changes.append(
                Touch(artifact=host, actor=user, state=state, at=now))
            session.commit()
