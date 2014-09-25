#!/usr/bin/env python
# encoding: UTF-8

import asyncio
import datetime
import sqlite3
import unittest
import uuid

from cloudhands.burst.agent import message_handler
from cloudhands.burst.registration import ValidAgent

import cloudhands.common
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
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
from cloudhands.common.schema import Registration
from cloudhands.common.schema import SoftwareDefinedNetwork
from cloudhands.common.schema import State
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User
from cloudhands.common.states import RegistrationState


class AgentTesting(unittest.TestCase):

    def setUp(self):
        """ Populate test database"""
        self.session = Registry().connect(sqlite3, ":memory:").session
        initialise(self.session)
        self.session.add_all((
            Organisation(
                uuid=uuid.uuid4().hex,
                name="TestOrg"),
            Provider(
                uuid=uuid.uuid4().hex,
                name="cloudhands.jasmin.vcloud.phase04.cfg"),
            Registration(
                uuid=uuid.uuid4().hex,
                model=cloudhands.common.__version__),
            User(handle="testuser", uuid=uuid.uuid4().hex),
        ))
        self.session.commit()

        self.reg, user = (
            self.session.query(Registration).one(),
            self.session.query(User).one(),
        )
        valid = self.session.query(
            RegistrationState).filter(
            RegistrationState.name == "valid").one()
        now = datetime.datetime.utcnow()
        act = Touch(artifact=self.reg, actor=user, state=valid, at=now)
        self.session.add(act)
        self.session.commit()

    def tearDown(self):
        """ Every test gets its own in-memory database """
        r = Registry()
        r.disconnect(sqlite3, ":memory:")


class ValidAgentTesting(AgentTesting):

    def test_handler_registration(self):
        q = asyncio.Queue()
        agent = ValidAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)
        self.assertEqual(
            agent.touch_to_active,
            message_handler.dispatch(ValidAgent.Message)
        )

    def test_job_query_and_transmit(self):
        q = ValidAgent.queue(None, None, loop=None)
        agent = ValidAgent(q, args=None, config=None)
        jobs = agent.jobs(self.session)
        self.assertEqual(1, len(jobs))

        q.put_nowait(jobs[0])
        self.assertEqual(1, q.qsize())

        job = q.get_nowait()
        self.assertEqual(1, len(job.artifact.changes))

    def test_queue_creation(self):
        self.assertIsInstance(
            ValidAgent.queue(None, None, loop=None),
            asyncio.Queue
        )

    def test_msg_dispatch_and_touch(self):
        reg = self.session.query(Registration).one()
        active = self.session.query(RegistrationState).filter(
            RegistrationState.name == "active").one()

        q = ValidAgent.queue(None, None, loop=None)
        agent = ValidAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)

        msg = ValidAgent.Message(
            reg.uuid, datetime.datetime.utcnow(),
            "cloudhands.jasmin.vcloud.phase04.cfg")
        rv = message_handler(msg, self.session)
        self.assertIsInstance(rv, Touch)
        self.assertIs(rv.state, active)
