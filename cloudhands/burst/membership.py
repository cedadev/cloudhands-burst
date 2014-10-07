#!/usr/bin/env python
# encoding: UTF-8

import asyncio
from collections import namedtuple
import datetime
import functools
import logging
import os
import textwrap
import traceback
import xml.etree.ElementTree as ET
import sys

import aiohttp

from cloudhands.burst.agent import Agent
from cloudhands.burst.agent import Job
from cloudhands.burst.utils import find_xpath

from cloudhands.common.discovery import providers
from cloudhands.common.schema import Component
from cloudhands.common.schema import Membership
from cloudhands.common.schema import Touch
from cloudhands.common.states import MembershipState


find_add_user_link = functools.partial(
    find_xpath, "./*/[@type='application/vnd.vmware.admin.user+xml']",
    rel="add")

def find_admin_org(tree, **kwargs): 
    elems = find_xpath(
        ".//*[@type='application/vnd.vmware.admin.organization+xml']",
        tree, namespaces={"": "http://www.vmware.com/vcloud/v1.5"}, **kwargs)
    return (i for i in elems if i.tag.endswith("OrganizationReference"))

def find_user_role(tree, **kwargs):
    elems = find_xpath(
        ".//*[@type='application/vnd.vmware.admin.role+xml']",
        tree, namespaces={"": "http://www.vmware.com/vcloud/v1.5"}, **kwargs)
    return (i for i in elems if i.tag.endswith("RoleReference"))

class AcceptedAgent(Agent):

    MembershipActivated = namedtuple(
        "MembershipActivated", ["uuid", "ts", "provider"])

    MembershipNotActivated = namedtuple(
        "MembershipNotActivated", ["uuid", "ts", "provider"])

    @staticmethod
    def queue(args, config, loop=None):
        return asyncio.Queue(loop=loop)

    @property
    def callbacks(self):
        return [
            (AcceptedAgent.MembershipActivated, self.touch_to_active),
            (AcceptedAgent.MembershipNotActivated, self.touch_to_previous),
        ]

    def jobs(self, session):
        return [Job(i.uuid, None, i) for i in session.query(Membership).all()
                if i.changes[-1].state.name == "accepted"]

    def touch_to_active(self, msg:MembershipActivated , session):
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

    def touch_to_previous(self, msg:MembershipNotActivated , session):
        reg = session.query(Membership).filter(
            Membership.uuid == msg.uuid).first()
        actor = session.query(Component).filter(
            Component.handle=="burst.controller").one()
        # TODO: per-provider resource
        state = reg.changes[-1].state
        act = Touch(artifact=reg, actor=actor, state=state, at=msg.ts)
        session.add(act)
        session.commit()
        return act


    @asyncio.coroutine
    def __call__(self, loop, msgQ, *args):
        log = logging.getLogger("cloudhands.burst.membership")
        configs = {cfg["metadata"]["path"]: cfg
                  for p in providers.values() for cfg in p}
        log.info("Activated.")
        while True:
            job = yield from self.work.get()

            try:
                try:
                    prvdrs = [sub.provider.name
                              for sub in job.artifact.organisation.subscriptions]
                    username = job.artifact.changes[1].actor.handle
                except (AttributeError, IndexError) as e:
                    log.error(e)
                    continue
                else:
                    log.debug(username)

                for provider in prvdrs:
                    config = configs[provider]

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
                        endpoint="api/admin")
                    response = yield from client.request(
                        "GET", url,
                        headers=headers)

                    orgList = yield from response.read_and_close()
                    tree = ET.fromstring(orgList.decode("utf-8"))

                    try:
                        role = next(find_user_role(tree, name="vApp User"))
                    except StopIteration:
                        log.error("Failed to find user role reference")
                        continue

                    orgFound = find_admin_org(tree, name=config["vdc"]["org"])
                    try:
                        org = next(orgFound)
                    except StopIteration:
                        log.error("Failed to find org")
                        continue

                    response = yield from client.request(
                        "GET", org.attrib.get("href"),
                        headers=headers)
                    orgData = yield from response.read_and_close()
                    tree = ET.fromstring(orgData.decode("utf-8"))


                    try:
                        addUser = next(find_add_user_link(tree))
                    except StopIteration:
                        log.error("Failed to find user endpoint")
                        continue

                    user = textwrap.dedent("""
                        <User
                           xmlns="http://www.vmware.com/vcloud/v1.5"
                           name="{}"
                           type="application/vnd.vmware.admin.user+xml">
                           <IsEnabled>true</IsEnabled>
                           <IsExternal>true</IsExternal>
                           <Role
                            type="application/vnd.vmware.admin.role+xml"
                            href="{}" />
                        </User>""").format(username, role.attrib.get("href"))

                    headers["Content-Type"] = (
                        "application/vnd.vmware.admin.user+xml")

                    response = yield from client.request(
                        "POST", addUser.attrib.get("href"),
                        headers=headers,
                        data=user.encode("utf-8"))
                    reply = yield from response.read_and_close()

                    tree = ET.fromstring(reply.decode("utf-8"))
                    if not tree.tag.endswith("User"):
                        log.warning(
                            "Error while adding user {}".format(username))
                        msg = AcceptedAgent.MembershipNotActivated(
                            job.uuid, datetime.datetime.utcnow(),
                            provider,
                        )
                    else:
                        msg = AcceptedAgent.MembershipActivated(
                            job.uuid, datetime.datetime.utcnow(),
                            provider,
                        )

                    yield from msgQ.put(msg)

            except Exception as e:
                exc_type, exc_value, exc_tb = sys.exc_info()
                log.error(traceback.format_exception(
                    exc_type, exc_value, exc_tb))
                log.error(e)
