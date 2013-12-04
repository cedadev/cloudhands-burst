#!/usr/bin/env python3
# encoding: UTF-8

import datetime
import uuid
from cloudhands.common.fsm import MembershipState

import cloudhands.common.schema
from cloudhands.common.schema import Membership
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User


class MembershipAgent():

    def invitation(session, user, org):
        prvlg = session.query(Membership).join(Touch).join(User).filter(
            User.id == user.id).filter(
            Membership.organisation == org).filter(
            Membership.role == "admin").first()
        if not prvlg or not prvlg.changes[-1].state.name == "active":
            return None

        mship = Membership(
            uuid=uuid.uuid4().hex,
            model=cloudhands.common.__version__,
            organisation=org,
            role="user")
        invite = session.query(MembershipState).filter(
            MembershipState.name == "invite").one()
        now = datetime.datetime.utcnow()
        act = Touch(artifact=mship, actor=user, state=invite, at=now)
        mship.changes.append(act)
        session.add(mship)
        session.commit()
        return act 
