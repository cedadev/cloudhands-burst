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
from cloudhands.burst.session import SessionAgent
from cloudhands.burst.test.test_appliance import AgentTesting

import cloudhands.common
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.schema import Provider
from cloudhands.common.schema import ProviderToken
from cloudhands.common.schema import Registration
from cloudhands.common.schema import State
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User
from cloudhands.common.states import RegistrationState
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

    def test_handler_operation(self):
        session = Registry().connect(sqlite3, ":memory:").session
        initialise(session)

        user = session.query(User).one()
        valid = session.query(
            RegistrationState).filter(
            RegistrationState.name == "valid").one()
        reg = Registration(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__)
        now = datetime.datetime.utcnow()
        act = Touch(artifact=reg, actor=user, state=valid, at=now)

        provider = session.query(Provider).one()
        session.add(act)
        session.commit()

        self.assertEqual(1, session.query(ProviderToken).count())

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "test.fifo")
            q = SessionAgent.queue(None, None, path=path)
            agent = SessionAgent(q, args=None, config=None)
            for typ, handler in agent.callbacks:
                message_handler.register(typ, handler)

            msg = SessionAgent.Message(
                reg.uuid, datetime.datetime.utcnow(),
                "cloudhands.jasmin.vcloud.phase04.cfg",
                "x-vcloud-authorization",
                "haj10ZIe55NvwxuN34bf+lOGxLNhuN1P+cBLkfQ7vYU=")
            rv = message_handler(msg, session)

            self.assertIsInstance(rv, Touch)
            self.assertEqual(2, session.query(ProviderToken).count())
            q.close()

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
