#!/usr/bin/env python
# encoding: UTF-8

import asyncio
import unittest

from cloudhands.burst.agent import message_handler
from cloudhands.burst.appliance import PreProvisionAgent

class PreProvisionAgentTesting(unittest.TestCase):

    def test_handler_registration(self):
        q = asyncio.Queue()
        agent = PreProvisionAgent(q, args=None, config=None)
        for typ, handler in agent.callbacks:
            message_handler.register(typ, handler)
        self.assertEqual(
            agent.touch_to_provisioning,
            message_handler.dispatch(PreProvisionAgent.Message)
        )

    def test_queue_creation(self):
        self.assertIsInstance(
            PreProvisionAgent.queue(None, None, loop=None),
            asyncio.Queue
        )
