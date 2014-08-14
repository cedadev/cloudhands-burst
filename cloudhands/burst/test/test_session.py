#!/usr/bin/env python
# encoding: UTF-8

import asyncio
import datetime
import os.path
import sqlite3
import tempfile
import unittest
import uuid

from cloudhands.burst.agent import message_handler
from cloudhands.burst.test.test_appliance import AgentTesting
from cloudhands.burst.session import SessionAgent

import cloudhands.common
from cloudhands.common.connectors import Registry
from cloudhands.common.schema import Provider
from cloudhands.common.schema import ProviderToken
from cloudhands.common.schema import Registration
from cloudhands.common.schema import State
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User
from cloudhands.common.pipes import PipeQueue


class SessionAgentTesting(AgentTesting):

    def test_handler_registration(self):
        q = asyncio.Queue()
        agent = SessionAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)
        self.assertEqual(
            agent.touch_with_token,
            message_handler.dispatch(SessionAgent.Message)
        )

    def test_job_creation(self):
        session = Registry().connect(sqlite3, ":memory:").session
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "test.fifo")
            q = SessionAgent.queue(None, None, path=path)
            agent = SessionAgent(q, args=None, config=None)
            jobs = agent.jobs(session)
            self.assertIsInstance(jobs, tuple)
            self.assertFalse(jobs)
            q.close()

    def test_queue_creation_from_path(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "test.fifo")
            q = SessionAgent.queue(None, None, path=path)
            self.assertIsInstance(q, PipeQueue)
            self.assertTrue(os.path.exists(q.path))
            q.close()
        self.assertFalse(os.path.exists(q.path))

    def test_queue_creation_bad_config(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "test.fifo")
            config = {"pipe.tokens": {}}
            q = SessionAgent.queue(None, config, path=path)
            self.assertIsInstance(q, PipeQueue)
            self.assertTrue(os.path.exists(q.path))
            q.close()
        self.assertFalse(os.path.exists(q.path))

    def test_queue_creation_from_config(self):
        config = {"pipe.tokens": {"vcloud": "~/.vcloud.fifo"}}
        q = SessionAgent.queue(None, config)
        self.assertIsInstance(q, PipeQueue)
        self.assertFalse("~" in q.path)
        self.assertTrue(q.path.endswith(".vcloud.fifo"))
        self.assertTrue(os.path.exists(q.path))
        q.close()
        os.remove(q.path)

    def tost_job_query_and_transmit(self):
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

    def tost_operational_msg_dispatch_and_touch(self):
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

    def tost_preoperational_msg_dispatch_and_touch(self):
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
