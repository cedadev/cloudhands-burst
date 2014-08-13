#!/usr/bin/env python
# encoding: UTF-8

import asyncio
import datetime
import sqlite3
import unittest
import uuid

from cloudhands.burst.agent import message_handler
from cloudhands.burst.appliance.test.test_appliance import AgentTesting
from cloudhands.burst.session import SessionAgent

import cloudhands.common
from cloudhands.common.connectors import Registry
from cloudhands.common.fsm import ApplianceState
from cloudhands.common.schema import Appliance
from cloudhands.common.schema import CatalogueChoice
from cloudhands.common.schema import CatalogueItem
from cloudhands.common.schema import Component
from cloudhands.common.schema import IPAddress
from cloudhands.common.schema import Label
from cloudhands.common.schema import NATRouting
from cloudhands.common.schema import Node
from cloudhands.common.schema import Organisation
from cloudhands.common.schema import Provider
from cloudhands.common.schema import ProviderReport
from cloudhands.common.schema import SoftwareDefinedNetwork
from cloudhands.common.schema import State
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User


class SessionAgentTesting(AgentTesting):

    def test_handler_registration(self):
        q = asyncio.Queue()
        agent = PreCheckAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)
        self.assertEqual(
            agent.touch_to_operational,
            message_handler.dispatch(PreCheckAgent.CheckedAsOperational)
        )
        self.assertEqual(
            agent.touch_to_preoperational,
            message_handler.dispatch(PreCheckAgent.CheckedAsPreOperational)
        )
        self.assertEqual(
            agent.touch_to_provisioning,
            message_handler.dispatch(PreCheckAgent.CheckedAsProvisioning)
        )

    def test_job_query_and_transmit(self):
        session = Registry().connect(sqlite3, ":memory:").session

        # 0. Set up User
        user = User(handle="Anon", uuid=uuid.uuid4().hex)
        org = session.query(Organisation).one()

        # 1. User creates new appliances
        now = datetime.datetime.utcnow()
        then = now - datetime.timedelta(seconds=45)
        requested = session.query(ApplianceState).filter(
            ApplianceState.name == "requested").one()
        apps = (
            Appliance(
                uuid=uuid.uuid4().hex,
                model=cloudhands.common.__version__,
                organisation=org),
            Appliance(
                uuid=uuid.uuid4().hex,
                model=cloudhands.common.__version__,
                organisation=org),
            )
        acts = (
            Touch(artifact=apps[0], actor=user, state=requested, at=then),
            Touch(artifact=apps[1], actor=user, state=requested, at=now)
        )

        tmplt = session.query(CatalogueItem).first()
        choices = (
            CatalogueChoice(
                provider=None, touch=acts[0], natrouted=True,
                **{k: getattr(tmplt, k, None)
                for k in ("name", "description", "logo")}),
            CatalogueChoice(
                provider=None, touch=acts[1], natrouted=True,
                **{k: getattr(tmplt, k, None)
                for k in ("name", "description", "logo")})
        )
        session.add_all(choices)
        session.commit()

        now = datetime.datetime.utcnow()
        then = now - datetime.timedelta(seconds=45)
        configuring = session.query(ApplianceState).filter(
            ApplianceState.name == "configuring").one()
        acts = (
            Touch(artifact=apps[0], actor=user, state=configuring, at=then),
            Touch(artifact=apps[1], actor=user, state=configuring, at=now)
        )
        session.add_all(acts)
        session.commit()

        self.assertEqual(
            2, session.query(Touch).join(Appliance).filter(
            Appliance.id == apps[1].id).count())

        # 2. One Appliance is configured interactively by user
        latest = apps[1].changes[-1]
        now = datetime.datetime.utcnow()
        act = Touch(
            artifact=apps[1], actor=user, state=latest.state, at=now)
        label = Label(
            name="test_server01",
            description="This is just for kicking tyres",
            touch=act)
        session.add(label)
        session.commit()

        self.assertEqual(
            3, session.query(Touch).join(Appliance).filter(
            Appliance.id == apps[1].id).count())

        # 3. Skip to provisioning
        now = datetime.datetime.utcnow()
        preprovision = session.query(ApplianceState).filter(
            ApplianceState.name == "provisioning").one()
        session.add(
            Touch(
                artifact=apps[1],
                actor=user,
                state=preprovision, at=now))

        # 4. Schedule for check
        now = datetime.datetime.utcnow()
        precheck = session.query(ApplianceState).filter(
            ApplianceState.name == "pre_check").one()
        session.add(
            Touch(
                artifact=apps[1],
                actor=user,
                state=precheck, at=now))

        session.add(act)
        session.commit()

        q = PreCheckAgent.queue(None, None, loop=None)
        agent = PreCheckAgent(q, args=None, config=None)
        jobs = agent.jobs(session)
        self.assertEqual(1, len(jobs))

        q.put_nowait(jobs[0])
        self.assertEqual(1, q.qsize())

        job = q.get_nowait()
        self.assertEqual(5, len(job.artifact.changes))

    def test_queue_creation(self):
        self.assertIsInstance(
            PreCheckAgent.queue(None, None, loop=None),
            asyncio.Queue
        )

    def test_operational_msg_dispatch_and_touch(self):
        session = Registry().connect(sqlite3, ":memory:").session
        user = User(handle="Anon", uuid=uuid.uuid4().hex)
        org = session.query(Organisation).one()

        now = datetime.datetime.utcnow()
        requested = session.query(ApplianceState).filter(
            ApplianceState.name == "requested").one()
        app = Appliance(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=org,
            )
        act = Touch(artifact=app, actor=user, state=requested, at=now)
        session.add(act)
        session.commit()

        self.assertEqual(0, session.query(ProviderReport).count())
        q = PreCheckAgent.queue(None, None, loop=None)
        agent = PreCheckAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)

        msg = PreCheckAgent.CheckedAsOperational(
            app.uuid, datetime.datetime.utcnow(),
            "cloudhands.jasmin.vcloud.phase04.cfg",
            "192.168.2.1", "deployed", "on", None)
        rv = message_handler(msg, session)
        self.assertIsInstance(rv, Touch)

        self.assertEqual(1, session.query(ProviderReport).count())
        report = session.query(ProviderReport).one()
        self.assertEqual(report.creation, "deployed")
        self.assertEqual(report.power, "on")
        self.assertEqual("operational", app.changes[-1].state.name)

    def test_preoperational_msg_dispatch_and_touch(self):
        session = Registry().connect(sqlite3, ":memory:").session
        user = User(handle="Anon", uuid=uuid.uuid4().hex)
        org = session.query(Organisation).one()

        now = datetime.datetime.utcnow()
        requested = session.query(ApplianceState).filter(
            ApplianceState.name == "requested").one()
        app = Appliance(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=org,
            )
        act = Touch(artifact=app, actor=user, state=requested, at=now)
        session.add(act)
        session.commit()

        self.assertEqual(0, session.query(ProviderReport).count())
        q = PreCheckAgent.queue(None, None, loop=None)
        agent = PreCheckAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)

        msg = PreCheckAgent.CheckedAsPreOperational(
            app.uuid, datetime.datetime.utcnow(),
            "cloudhands.jasmin.vcloud.phase04.cfg",
            "192.168.2.1", "deployed", "off", None)
        rv = message_handler(msg, session)
        self.assertIsInstance(rv, Touch)

        self.assertEqual(1, session.query(ProviderReport).count())
        report = session.query(ProviderReport).one()
        self.assertEqual(report.creation, "deployed")
        self.assertEqual(report.power, "off")
        self.assertEqual("pre_operational", app.changes[-1].state.name)
