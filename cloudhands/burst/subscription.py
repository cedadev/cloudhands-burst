#!/usr/bin/env python3
# encoding: UTF-8

import concurrent.futures
import datetime
import logging

from cloudhands.burst.control import list_images
from cloudhands.common.fsm import SubscriptionState
from cloudhands.common.schema import Subscription

from cloudhands.common.schema import Component
from cloudhands.common.schema import Touch
from cloudhands.common.schema import OSImage

class Catalogue:
    """
    The catalogue of a provider as most recently discovered.
    """
    def __init__(self, actor, subs, items):
        self.actor = actor
        self.subs = subs
        self.items = items

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

def fake_list_images(name):
    from cloudhands.common.discovery import bundles
    from cloudhands.common.discovery import providers
    from libcloud import security
    from libcloud.compute.providers import get_driver
    security.CA_CERTS_PATH = bundles
    for config in [
        cfg for p in providers.values() for cfg in p
        if cfg["metadata"]["path"] == name
    ]:
        user = config["user"]["name"]
        pswd = config["user"]["pass"]
        host = config["host"]["name"]
        port = config["host"]["port"]
        apiV = config["host"]["api_version"]
        drvr = get_driver(config["libcloud"]["provider"])
        conn = drvr(
            user, pswd, host=host, port=port, api_version=apiV)
        return [(i.name, i.id) for i in conn.list_images()]


class SubscriptionAgent:

    def touch_unchecked(session):
        log = logging.getLogger("cloudhands.burst.agents.SubscriptionAgent")
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        unchecked = session.query(
            SubscriptionState).filter(
            SubscriptionState.name=="unchecked").one()
            
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exctr:
            subs = [i for i in session.query(Subscription).all()
                if i.changes[-1].state is unchecked]
            jobs = {
                exctr.submit(list_images, name=i.name): i for i in set(
                    s.provider for s in subs)} 
            log.debug(jobs)
            for job in concurrent.futures.as_completed(jobs):
                provider = jobs[job]
                subscribers = [i for i in subs if i.provider is provider]
                log.debug(subscribers)
                now = datetime.datetime.utcnow()
                for s in subscribers:
                    act = Catalogue(actor, s)(session)
                    for name, id_ in job.result():
                        resource = OSImage(name=name, provider=provider, touch=act)
                    s.changes.append(act)
                    session.commit()
                    yield act
