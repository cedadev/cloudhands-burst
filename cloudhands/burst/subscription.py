#!/usr/bin/env python3
# encoding: UTF-8

import datetime

from cloudhands.common.fsm import SubscriptionState

from cloudhands.common.schema import Touch

class Catalogue:
    """
    The catalogue of a provider as most recently discovered.
    """
    def __init__(self, actor, subs, items):
        self.actor = actor
        self.subs = subs
        self.items = items
        print(*list(vars(i) for i in self.items))

    def __call__(self, session):
        if self.subs.changes[-1].state.name != "unchecked":
            return None

        active = session.query(
            SubscriptionState).filter(
            SubscriptionState.name=="active").one()
        now = datetime.datetime.utcnow()
        act = Touch(
            artifact=self.subs, actor=self.actor, state=active, at=now)
        self.subs.changes.append(act)
        act.resources = self.items
        session.commit()
        return act


class Online:
    """
    Brings a provider subscription out of maintenance

    :param object subs: \
    A :py:func:`cloudhands.common.schema.Subscription` object.
    """

    def __init__(self, actor, subs):
        self.actor = actor
        self.subs = subs

    def __call__(self, session):
        if self.subs.changes[-1].state.name != "maintenance":
            return None

        unchecked = session.query(
            SubscriptionState).filter(
            SubscriptionState.name=="unchecked").one()

        now = datetime.datetime.utcnow()
        act = Touch(
            artifact=self.subs, actor=self.actor, state=unchecked, at=now)
        self.subs.changes.append(act)
        session.commit()
        return act
