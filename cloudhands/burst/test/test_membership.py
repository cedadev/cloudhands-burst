#!/usr/bin/env python3
# encoding: UTF-8

import sqlite3
import unittest
import uuid

from cloudhands.burst.membership import MembershipAgent

import cloudhands.common
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry

from cloudhands.common.schema import Membership
from cloudhands.common.schema import Organisation
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User


class MembershipLifecycleTests(unittest.TestCase):

    def setUp(self):
        session = Registry().connect(sqlite3, ":memory:").session
        initialise(session)
        self.org = Organisation(name="TestOrg")
        aM = Membership(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=self.org,
            role="admin")
        uM = Membership(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=self.org,
            role="user")
        self.admin = User(handle="Administrator", uuid=uuid.uuid4().hex)
        self.user = User(handle="User", uuid=uuid.uuid4().hex)
        self.guest = User(handle="Guest", uuid=uuid.uuid4().hex)
        session.add_all((self.admin, self.user, self.guest, aM, uM, self.org))
        session.commit()

    def tearDown(self):
        Registry().disconnect(sqlite3, ":memory:")
 
    def test_only_admins_create_invites(self):
        session = Registry().connect(sqlite3, ":memory:").session
        self.assertIsNone(
            MembershipAgent.invitation(session, self.user, self.org))
        self.assertIsInstance(
            Touch,
            MembershipAgent.invitation(session, self.admin, self.org))
