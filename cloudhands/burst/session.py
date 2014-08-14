#!/usr/bin/env python
# encoding: UTF-8

import asyncio
from collections import namedtuple
import os

from cloudhands.burst.agent import Agent
from cloudhands.burst.agent import Job

from cloudhands.common.schema import Component
from cloudhands.common.schema import Provider
from cloudhands.common.schema import ProviderToken
from cloudhands.common.schema import Registration
from cloudhands.common.schema import Touch
from cloudhands.common.pipes import PipeQueue


class SessionAgent(Agent):

    Message = namedtuple(
        "TokenReceived", ["uuid", "ts", "provider", "key", "value"])

    @staticmethod
    def queue(args, config, loop=None, path=None):
        try:
            path = path or os.path.expanduser(config["pipe.tokens"]["vcloud"])
        finally:
            return PipeQueue.pipequeue(path)

    @property
    def callbacks(self):
        return [(SessionAgent.Message, self.touch_with_token)]

    def jobs(self, session):
        return tuple()

    def touch_with_token(self, msg:Message, session):
        reg = session.query(Registration).filter(
            Registration.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        state = reg.changes[-1].state
        act = Touch(artifact=reg, actor=actor, state=state, at=msg.ts)
        resource = ProviderToken(
            touch=act, provider=provider,
            key=msg.key, value=msg.value)

        session.add(resource)
        session.commit()
        return act
