#!/usr/bin/env python
# encoding: UTF-8

import asyncio
from collections import namedtuple
import datetime
import logging
import os

import aiohttp

from cloudhands.burst.agent import Agent
from cloudhands.burst.agent import Job
from cloudhands.burst.appliance import Strategy

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
        user = reg.changes[0].actor
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one()
        state = reg.changes[-1].state
        act = Touch(artifact=reg, actor=user, state=state, at=msg.ts)
        resource = ProviderToken(
            touch=act, provider=provider,
            key=msg.key, value=msg.value)

        session.add(resource)
        session.commit()
        return act

    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.session.token")
        log.info("Activated.")
        while True:
            data = yield from self.work.get()
            try:
                reg_uuid, provider_name, user_name, user_pass = data
            except ValueError as e:
                log.error(e)
                continue

            try:
                config = Strategy.config(provider_name)

                url = "{scheme}://{host}:{port}/{endpoint}".format(
                    scheme="https",
                    host=config["host"]["name"],
                    port=config["host"]["port"],
                    endpoint="api/sessions")

                headers = {
                    "Accept": "application/*+xml;version=5.5",
                }

                client = aiohttp.client.HttpClient(
                    ["{host}:{port}".format(
                        host=config["host"]["name"],
                        port=config["host"]["port"])
                    ],
                    verify_ssl=config["host"].getboolean("verify_ssl_cert")
                )

                user_ref = "{}@{}".format(user_name, config["vdc"]["org"])
                auth=(user_ref, user_pass)
                response = yield from client.request(
                    "POST", url,
                    auth=auth,
                    headers=headers)
                key = "x-vcloud-authorization"
                value = response.headers.get(key)

                if not value:
                    log.warning("{} sent status {} on auth of {}".format(
                        provider_name, response.status, reg_uuid))
                else:
                    msg = SessionAgent.Message(
                        reg_uuid, datetime.datetime.utcnow(),
                        provider_name, key, value
                    )
                    yield from msgQ.put(msg)

            except Exception as e:
                log.error(e)
