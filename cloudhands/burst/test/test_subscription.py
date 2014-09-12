#!/usr/bin/env python3
# encoding: UTF-8

import datetime
import sqlite3
import unittest
import uuid

from cloudhands.burst.subscription import Catalogue
from cloudhands.burst.subscription import Online

import cloudhands.common
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry

from cloudhands.common.schema import Component
from cloudhands.common.schema import Organisation
from cloudhands.common.schema import OSImage
from cloudhands.common.schema import Provider
from cloudhands.common.schema import Subscription
from cloudhands.common.schema import Touch

from cloudhands.common.states import SubscriptionState


class SubscriptionLifecycleTests(unittest.TestCase):

    def setUp(self):
        self.session = Registry().connect(sqlite3, ":memory:").session
        initialise(self.session)
        self.org = Organisation(
            uuid=uuid.uuid4().hex,
            name="TestOrg")
        self.providers = [
            Provider(uuid=uuid.uuid4().hex, name="JASMIN private DC"),
            Provider(uuid=uuid.uuid4().hex, name="JASMIN burst partner"),
        ]
        self.session.add_all([self.org] + self.providers)
        self.session.commit()

    def tearDown(self):
        Registry().disconnect(sqlite3, ":memory:")


class OnlineTests(SubscriptionLifecycleTests):

    def setUp(self):
        super().setUp()
        self.subs = Subscription(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=self.org,
            provider=self.providers[0])
        puppet = Component(handle="config management", uuid=uuid.uuid4().hex)
        maintenance = self.session.query(
            SubscriptionState).filter(SubscriptionState.name=="maintenance").one()
        self.subs.changes.append(
            Touch(
                artifact=self.subs, actor=puppet, state=maintenance,
                at=datetime.datetime.utcnow())
            )
        self.session.add_all([puppet, self.subs])
        self.session.commit()

    def test_bring_subscriptions_online(self):
        actor = Component(handle="Maintenence", uuid=uuid.uuid4().hex)
        maintenance = self.session.query(
            SubscriptionState).filter(
            SubscriptionState.name=="maintenance").one()
        offline = [i for i in self.org.subscriptions
            if i.changes[-1].state is maintenance]
        self.assertEqual(1, len(offline))
        for subs in offline:
            act = Online(actor, subs)(self.session)
            self.assertIs(self.subs, act.artifact)
            self.assertEqual("unchecked", act.state.name)

    def test_online_from_invalid_state(self):
        actor = Component(handle="Maintenence", uuid=uuid.uuid4().hex)
        maintenance = self.session.query(
            SubscriptionState).filter(
            SubscriptionState.name=="maintenance").one()
        active = self.session.query(
            SubscriptionState).filter(
            SubscriptionState.name=="active").one()
        offline = [i for i in self.org.subscriptions
            if i.changes[-1].state is maintenance]
        self.assertEqual(1, len(offline))
        now = datetime.datetime.utcnow()
        self.session.add(
            Touch(artifact=offline[0], actor=actor, state=active, at=now))
        self.session.commit()
        for subs in offline:
            act = Online(actor, subs)(self.session)
            self.assertIs(None, act)


class CatalogueTests(SubscriptionLifecycleTests):

    def setUp(self):
        super().setUp()
        self.subs = Subscription(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=self.org,
            provider=self.providers[0])
        puppet = Component(handle="config management", uuid=uuid.uuid4().hex)
        unchecked = self.session.query(
            SubscriptionState).filter(SubscriptionState.name=="unchecked").one()
        self.subs.changes.append(
            Touch(
                artifact=self.subs, actor=puppet, state=unchecked,
                at=datetime.datetime.utcnow())
            )
        self.session.add_all([puppet, self.subs])
        self.session.commit()

    def test_calling_catalogue_makes_active(self):
        actor = Component(handle="Maintenence", uuid=uuid.uuid4().hex)
        unchecked = self.session.query(
            SubscriptionState).filter(
            SubscriptionState.name=="unchecked").one()
        jobs = [i for i in self.org.subscriptions
            if i.changes[-1].state is unchecked]
        self.assertEqual(1, len(jobs))
        for subs in jobs:
            act = Catalogue(actor, subs)(self.session)
            for name in ("CentOS6.5", "Ubuntu 12.04 LTS"):
                self.session.add(OSImage(name=name, touch=act))
            subs.changes.append(act)
            self.session.commit()
            self.assertIs(self.subs, act.artifact)
            self.assertEqual("active", act.state.name)
            self.assertEqual(2, len(act.resources))

    def test_catalogue_from_invalid_state(self):
        actor = Component(handle="Maintenence", uuid=uuid.uuid4().hex)
        unchecked = self.session.query(
            SubscriptionState).filter(
            SubscriptionState.name=="unchecked").one()
        active = self.session.query(
            SubscriptionState).filter(
            SubscriptionState.name=="active").one()
        jobs = [i for i in self.org.subscriptions
            if i.changes[-1].state is unchecked]
        self.assertEqual(1, len(jobs))
        now = datetime.datetime.utcnow()
        self.session.add(
            Touch(artifact=jobs[0], actor=actor, state=active, at=now))
        self.session.commit()

        for subs in jobs:
            act = Catalogue(actor, subs)(self.session)
            self.assertIs(None, act)

