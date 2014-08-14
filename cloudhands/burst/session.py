#!/usr/bin/env python
# encoding: UTF-8

import asyncio
from collections import namedtuple
import os

from cloudhands.burst.agent import Agent
from cloudhands.burst.agent import Job

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
        provisioning = session.query(ApplianceState).filter(
            ApplianceState.name == "provisioning").one()
        app = session.query(Appliance).filter(
            Appliance.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        act = Touch(artifact=app, actor=actor, state=provisioning, at=msg.ts)
        resource = Node(
            name="", touch=act, provider=provider,
            uri=msg.uri)
        session.add(resource)
        session.commit()
        return act
