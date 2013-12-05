#!/usr/bin/env python3
# encoding: UTF-8

import datetime
import sqlite3
import unittest
import uuid

from cloudhands.burst.membership import Invitation

import cloudhands.common
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry

from cloudhands.common.fsm import MembershipState

from cloudhands.common.schema import Membership
from cloudhands.common.schema import Organisation
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User


class MembershipLifecycleTests(unittest.TestCase):

    def setUp(self):
        self.session = Registry().connect(sqlite3, ":memory:").session
        initialise(self.session)
        self.org = Organisation(name="TestOrg")
        adminMp = Membership(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=self.org,
            role="admin")
        userMp = Membership(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=self.org,
            role="user")
        self.admin = User(handle="Administrator", uuid=uuid.uuid4().hex)
        self.user = User(handle="User", uuid=uuid.uuid4().hex)
        self.guest = User(handle="Guest", uuid=uuid.uuid4().hex)
        active = self.session.query(MembershipState).filter(
            MembershipState.name == "active").one()
        adminMp.changes.append(
            Touch(
                artifact=adminMp, actor=self.admin, state=active,
                at=datetime.datetime.utcnow())
            )
        userMp.changes.append(
            Touch(
                artifact=userMp, actor=self.user, state=active,
                at=datetime.datetime.utcnow())
            )
        self.session.add_all(
            (self.admin, self.user, self.guest, adminMp, userMp, self.org))
        self.session.commit()

    def tearDown(self):
        Registry().disconnect(sqlite3, ":memory:")
 
    def test_expired_admins_cannot_create_invites(self):
        expired = self.session.query(MembershipState).filter(
            MembershipState.name == "expired").one()
        adminMp = self.session.query(Membership).join(Touch).join(User).filter(
            User.id == self.admin.id).one()
        adminMp.changes.append(
            Touch(
                artifact=adminMp, actor=self.admin, state=expired,
                at=datetime.datetime.utcnow())
            )
        self.session.commit()
        self.assertIsNone(
            Invitation(self.admin, self.org)(self.session))

    def test_withdrawn_admins_cannot_create_invites(self):
        withdrawn = self.session.query(MembershipState).filter(
            MembershipState.name == "withdrawn").one()
        adminMp = self.session.query(Membership).join(Touch).join(User).filter(
            User.id == self.admin.id).one()
        adminMp.changes.append(
            Touch(
                artifact=adminMp, actor=self.admin, state=withdrawn,
                at=datetime.datetime.utcnow())
            )
        self.session.commit()
        self.assertIsNone(
            Invitation(self.admin, self.org)(self.session))

    def test_only_admins_create_invites(self):
        self.assertIsNone(
            Invitation(self.user, self.org)(self.session))
        self.assertIsInstance(
            Invitation(self.admin, self.org)(self.session),
            Touch)
