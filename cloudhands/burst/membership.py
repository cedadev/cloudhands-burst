#!/usr/bin/env python3
# encoding: UTF-8

import datetime
import uuid
from cloudhands.common.fsm import MembershipState

import cloudhands.common.schema
from cloudhands.common.schema import Membership
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User


def handle_from_email(addrVal):
    return ' '.join(
        i.capitalize() for i in addrVal.split('@')[0].split('.'))


class Invitation():
    """
    :param object user: A :py:func:`cloudhands.common.schema.User` object.
    :param object org: A :py:func:`cloudhands.common.schema.Organisation`.
    """
    def __init__(self, user, org):
        self.user = user
        self.org = org

    def __call__(self, session):
        """
        Attempts to create a new membership record for the organisation.

        If the `user` attribute is not privileged in the organisation, the
        operation will fail and `None` will be returned.

        :param object session:  A SQLALchemy database session.
        :returns: a :py:func:`cloudhands.common.schema.Touch` object.
        """
        prvlg = session.query(Membership).join(Touch).join(User).filter(
            User.id == self.user.id).filter(
            Membership.organisation == self.org).filter(
            Membership.role == "admin").first()
        if not prvlg or not prvlg.changes[-1].state.name == "active":
            return None

        mship = Membership(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=self.org,
            role="user")
        invite = session.query(MembershipState).filter(
            MembershipState.name == "invite").one()
        now = datetime.datetime.utcnow()
        act = Touch(artifact=mship, actor=self.user, state=invite, at=now)
        mship.changes.append(act)
        session.add(mship)
        session.commit()
        return act 


class Activation():
    """
    :param object user: A :py:func:`cloudhands.common.schema.User` object.
    :param object mship: A :py:func:`cloudhands.common.schema.Membership`.
    :param object eAddr: A :py:func:`cloudhands.common.schema.EmailAddress`.
    """
    def __init__(self, user, mship, eAddr):
        self.user = user
        self.mship = mship
        self.eAddr = eAddr

    def __call__(self, session):
        """
        Activates the membership record for the organisation.

        :param object session:  A SQLALchemy database session.
        :returns: a :py:func:`cloudhands.common.schema.Touch` object.
        """
        active = session.query(
            MembershipState).filter(MembershipState.name == "active").one()
        now = datetime.datetime.utcnow()

        act = Touch(artifact=self.mship, actor=self.user, state=active, at=now)
        self.mship.changes.append(act)
        self.eAddr.touch = act
        session.add(self.eAddr)
        session.commit()
        return act


class MembershipAgent():
    pass

