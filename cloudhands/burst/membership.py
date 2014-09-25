#!/usr/bin/env python
# encoding: UTF-8

import asyncio
from collections import namedtuple
import datetime
import logging
import os
import xml.etree.ElementTree as ET

import aiohttp

from cloudhands.burst.agent import Agent
from cloudhands.burst.agent import Job
from cloudhands.burst.appliance import find_orgs

from cloudhands.common.discovery import providers
from cloudhands.common.schema import Component
from cloudhands.common.schema import Membership
from cloudhands.common.schema import Provider
from cloudhands.common.schema import ProviderToken
from cloudhands.common.schema import Touch
from cloudhands.common.states import MembershipState


class AcceptedAgent(Agent):

    Message = namedtuple(
        "MembershipActivated", ["uuid", "ts", "handle"])

    @staticmethod
    def queue(args, config, loop=None):
        return asyncio.Queue(loop=loop)

    @property
    def callbacks(self):
        return [(AcceptedAgent.Message, self.touch_to_active)]

    def jobs(self, session):
        return [Job(i.uuid, None, i) for i in session.query(Membership).all()
                if i.changes[-1].state.name == "accepted"]

    def touch_to_active(self, msg:Message, session):
        reg = session.query(Membership).filter(
            Membership.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        # TODO: per-provider resource
        active = session.query(MembershipState).filter(
            MembershipState.name == "active").one()
        act = Touch(artifact=reg, actor=actor, state=active, at=msg.ts)
        session.add(act)
        session.commit()
        return act

    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.registration")
        configs = {cfg["metadata"]["path"]: cfg
                  for p in providers.values() for cfg in p}
        log.info("Activated.")
        while True:
            job = yield from self.work.get()

            try:
                prvdrs = [sub.provider.name
                          for sub in job.artifact.organisation.subscriptions]
                for p in prvdrs:
                    config = configs[p]
                    log.debug(config)

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

                    response = yield from client.request(
                        "POST", url,
                        auth=(config["user"]["name"], config["user"]["pass"]),
                        headers=headers)
                    headers["x-vcloud-authorization"] = response.headers.get(
                        "x-vcloud-authorization")

                    url = "{scheme}://{host}:{port}/{endpoint}".format(
                        scheme="https",
                        host=config["host"]["name"],
                        port=config["host"]["port"],
                        endpoint="api/org")
                    response = yield from client.request(
                        "GET", url,
                        headers=headers)

                    orgList = yield from response.read_and_close()
                    tree = ET.fromstring(orgList.decode("utf-8"))
                    orgFound = find_orgs(tree, name=config["vdc"]["org"])

                    try:
                        org = next(orgFound)
                    except StopIteration:
                        log.error("Failed to find org")
                        continue
                    else:
                        log.debug(org)

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
