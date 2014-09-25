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

from cloudhands.common.discovery import providers
from cloudhands.common.schema import Component
from cloudhands.common.schema import Provider
from cloudhands.common.schema import ProviderToken
from cloudhands.common.schema import Registration
from cloudhands.common.schema import Touch
from cloudhands.common.states import RegistrationState


class ValidAgent(Agent):

    Message = namedtuple(
        "RegistrationActivated", ["uuid", "ts", "provider"])

    @staticmethod
    def queue(args, config, loop=None):
        return asyncio.Queue(loop=loop)

    @property
    def callbacks(self):
        return [(ValidAgent.Message, self.touch_to_active)]

    def jobs(self, session):
        return [Job(i.uuid, None, i) for i in session.query(Registration).all()
                if i.changes[-1].state.name == "valid"]

    def touch_to_active(self, msg:Message, session):
        reg = session.query(Registration).filter(
            Registration.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        provider = session.query(Provider).filter(
            Provider.name==msg.provider).one() # TODO: per-provider resource
        active = session.query(RegistrationState).filter(
            RegistrationState.name == "active").one()
        act = Touch(artifact=reg, actor=actor, state=active, at=msg.ts)
        session.add(act)
        session.commit()
        return act

    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.registration")
        log.info("Activated.")
        while True:
            job = yield from self.work.get()

            try:
                config = providers["vcloud"][-1]

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

                #response = yield from client.request(
                #    "POST", url,
                #    auth=(user_name, user_pass),
                #    headers=headers)
                #key = "x-vcloud-authorization"
                #value = response.headers.get(key)

                value = None
                if not value:
                    log.info(job.artifact)
                else:
                    msg = SessionAgent.Message(
                        reg_uuid, datetime.datetime.utcnow(),
                        provider_name,
                    )
                    yield from msgQ.put(msg)

            except Exception as e:
                log.error(e)
