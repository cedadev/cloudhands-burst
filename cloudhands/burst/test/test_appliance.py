#!/usr/bin/env python
# encoding: UTF-8

import asyncio
import datetime
import sqlite3
import unittest
import uuid

from cloudhands.burst.agent import message_handler
from cloudhands.burst.appliance import PreCheckAgent
from cloudhands.burst.appliance import PreProvisionAgent
from cloudhands.burst.appliance import ProvisioningAgent

import cloudhands.common
from cloudhands.common.connectors import Registry
from cloudhands.common.fsm import ApplianceState
from cloudhands.common.schema import Appliance
from cloudhands.common.schema import CatalogueChoice
from cloudhands.common.schema import CatalogueItem
from cloudhands.common.schema import Component
from cloudhands.common.schema import IPAddress
from cloudhands.common.schema import Label
from cloudhands.common.schema import Node
from cloudhands.common.schema import Organisation
from cloudhands.common.schema import Provider
from cloudhands.common.schema import ProviderReport
from cloudhands.common.schema import SoftwareDefinedNetwork
from cloudhands.common.schema import State
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User


class AgentTesting(unittest.TestCase):

    def setUp(self):
        """ Populate test database"""
        session = Registry().connect(sqlite3, ":memory:").session
        session.add_all(
            State(fsm=ApplianceState.table, name=v)
            for v in ApplianceState.values)
        session.add(
            Component(handle="burst.controller", uuid=uuid.uuid4().hex))
        session.add_all((
            Organisation(
                uuid=uuid.uuid4().hex,
                name="TestOrg"),
            Provider(
                uuid=uuid.uuid4().hex,
                name="cloudhands.jasmin.vcloud.phase04.cfg"),
            )
        )
        session.commit()

        org = session.query(Organisation).one()
        session.add_all((
            CatalogueItem(
                uuid=uuid.uuid4().hex,
                name="Web Server",
                description="Apache server VM",
                note=None,
                logo=None,
                organisation=org,
            ),
            CatalogueItem(
                uuid=uuid.uuid4().hex,
                name="File Server",
                description="OpenSSH server VM",
                note=None,
                logo=None,
                organisation=org,
            )
        ))
        session.commit()

    def tearDown(self):
        """ Every test gets its own in-memory database """
        r = Registry()
        r.disconnect(sqlite3, ":memory:")


class PreCheckAgentTesting(AgentTesting):

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
            "deployed", "on", None)
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
            "deployed", "off", None)
        rv = message_handler(msg, session)
        self.assertIsInstance(rv, Touch)

        self.assertEqual(1, session.query(ProviderReport).count())
        report = session.query(ProviderReport).one()
        self.assertEqual(report.creation, "deployed")
        self.assertEqual(report.power, "off")
        self.assertEqual("pre_operational", app.changes[-1].state.name)


class PreProvisionAgentTesting(AgentTesting):

    def test_handler_registration(self):
        q = asyncio.Queue()
        agent = PreProvisionAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)
        self.assertEqual(
            agent.touch_to_provisioning,
            message_handler.dispatch(PreProvisionAgent.Message)
        )

    def test_queue_creation(self):
        self.assertIsInstance(
            PreProvisionAgent.queue(None, None, loop=None),
            asyncio.Queue
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
                provider=None, touch=acts[1], natrouted=False,
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

        # 3. When user is happy, clicks 'Go'
        now = datetime.datetime.utcnow()
        preprovision = session.query(ApplianceState).filter(
            ApplianceState.name == "pre_provision").one()
        act = Touch(
            artifact=apps[1], actor=user, state=preprovision, at=now)
        session.add(act)
        session.commit()

        q = PreProvisionAgent.queue(None, None, loop=None)
        agent = PreProvisionAgent(q, args=None, config=None)
        jobs = agent.jobs(session)
        self.assertEqual(1, len(jobs))

        q.put_nowait(jobs[0])
        self.assertEqual(1, q.qsize())

        job = q.get_nowait()
        self.assertEqual(4, len(job.artifact.changes))

    def test_msg_dispatch_and_touch(self):
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

        self.assertEqual(0, session.query(Node).count())
        q = PreProvisionAgent.queue(None, None, loop=None)
        agent = PreProvisionAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)

        msg = PreProvisionAgent.Message(
            app.uuid, datetime.datetime.utcnow(),
            "cloudhands.jasmin.vcloud.phase04.cfg",
            "https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/"
            "vapp-a24617ae-7af0-4e83-92db-41e081b67102")
        rv = message_handler(msg, session)
        self.assertIsInstance(rv, Touch)

        self.assertEqual(1, session.query(Node).count())
        self.assertEqual("provisioning", app.changes[-1].state.name)


class ProvisioningAgentTesting(AgentTesting):

    def test_handler_registration(self):
        q = asyncio.Queue()
        agent = ProvisioningAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)
        self.assertEqual(
            agent.touch_to_precheck,
            message_handler.dispatch(ProvisioningAgent.Message)
        )

    def test_queue_creation(self):
        self.assertIsInstance(
            ProvisioningAgent.queue(None, None, loop=None),
            asyncio.Queue
        )

    def test_msg_dispatch_and_touch(self):
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

        q = ProvisioningAgent.queue(None, None, loop=None)
        agent = PreProvisionAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)

        msg = ProvisioningAgent.Message(
            app.uuid, datetime.datetime.utcnow())
        rv = message_handler(msg, session)
        self.assertIsInstance(rv, Touch)

        self.assertEqual("pre_check", app.changes[-1].state.name)

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
        provisioning = session.query(ApplianceState).filter(
            ApplianceState.name == "provisioning").one()
        acts = (
            Touch(artifact=apps[0], actor=user, state=provisioning, at=then),
            Touch(artifact=apps[1], actor=user, state=provisioning, at=now)
        )
        session.add_all(acts)
        session.commit()

        self.assertEqual(
            2, session.query(Touch).join(Appliance).filter(
            Appliance.id == apps[1].id).count())

        q = ProvisioningAgent.queue(None, None, loop=None)
        agent = ProvisioningAgent(q, args=None, config=None)
        jobs = agent.jobs(session)
        self.assertEqual(1, len(jobs))
        self.assertEqual(apps[0].uuid, jobs[0].uuid)


class ApplianceTesting(AgentTesting):

    def test_appliance_lifecycle(self):
        session = Registry().connect(sqlite3, ":memory:").session

        # 0. Set up User
        user = User(handle="Anon", uuid=uuid.uuid4().hex)
        org = session.query(Organisation).one()

        # 1. User creates a new appliance
        now = datetime.datetime.utcnow()
        requested = session.query(ApplianceState).filter(
            ApplianceState.name == "requested").one()
        app = Appliance(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=org,
            )
        act = Touch(artifact=app, actor=user, state=requested, at=now)

        tmplt = session.query(CatalogueItem).first()
        choice = CatalogueChoice(
            provider=None, touch=act, natrouted=True,
            **{k: getattr(tmplt, k, None)
            for k in ("name", "description", "logo")})
        session.add(choice)
        session.commit()

        self.assertEqual(
            1, session.query(CatalogueChoice).join(Touch).join(
            Appliance).filter(Appliance.id == app.id).count())

        now = datetime.datetime.utcnow()
        configuring = session.query(ApplianceState).filter(
            ApplianceState.name == "configuring").one()
        act = Touch(artifact=app, actor=user, state=configuring, at=now)
        session.add(act)
        session.commit()

        self.assertEqual(
            2, session.query(Touch).join(Appliance).filter(
            Appliance.id == app.id).count())

        # 2. Appliance persists and is configured interactively by user
        latest = app.changes[-1]
        now = datetime.datetime.utcnow()
        act = Touch(
            artifact=app, actor=user, state=latest.state, at=now)
        label = Label(
            name="test_server01",
            description="This is just for kicking tyres",
            touch=act)
        session.add(label)
        session.commit()

        self.assertEqual(
            3, session.query(Touch).join(Appliance).filter(
            Appliance.id == app.id).count())

        # 3. When user is happy, clicks 'Go'
        now = datetime.datetime.utcnow()
        preprovision = session.query(ApplianceState).filter(
            ApplianceState.name == "pre_provision").one()
        act = Touch(
            artifact=app, actor=user, state=preprovision, at=now)
        session.add(act)
        session.commit()

        self.assertEqual(
            4, session.query(Touch).join(Appliance).filter(
            Appliance.id == app.id).count())

        # 4. Burst controller finds hosts in 'pre_provision' and actions them
        latest = (h.changes[-1] for h in session.query(Appliance).all())
        jobs = [
            (t.actor, t.artifact) for t in latest
            if t.state is preprovision]
        self.assertIn((user, app), jobs)

        now = datetime.datetime.utcnow()
        provisioning = session.query(ApplianceState).filter(
            ApplianceState.name == "provisioning").one()
        app.changes.append(
            Touch(artifact=app, actor=user, state=provisioning, at=now))
        session.commit()

        # 5. Burst controller raises a node
        now = datetime.datetime.utcnow()
        provider = session.query(Provider).one()
        act = Touch(artifact=app, actor=user, state=provisioning, at=now)

        label = session.query(Label).join(Touch).join(Appliance).filter(
            Appliance.id == app.id).first()
        node = Node(name=label.name, touch=act, provider=provider)
        sdn = SoftwareDefinedNetwork(name="bridge_routed_external", touch=act)
        session.add_all((sdn, node))
        session.commit()

        # 6. Burst controller allocates an IP
        now = datetime.datetime.utcnow()
        act = Touch(artifact=app, actor=user, state=provisioning, at=now)
        app.changes.append(act)
        ip = IPAddress(value="192.168.1.4", touch=act, provider=provider)
        session.add(ip)
        self.assertIn(act, session)
        session.commit()

        # 7. Burst controller marks Host as pre_operational
        now = datetime.datetime.utcnow()
        preoperational = session.query(ApplianceState).filter(
            ApplianceState.name == "pre_operational").one()
        app.changes.append(
            Touch(artifact=app, actor=user, state=preoperational, at=now))

        # 8. Recovering details of provisioning of this host
        resources = [r for i in session.query(Touch).filter(
            Touch.artifact == app).all() for r in i.resources]
        self.assertIn(node, resources)
        self.assertIn(sdn, resources)
        self.assertIn(ip, resources)
