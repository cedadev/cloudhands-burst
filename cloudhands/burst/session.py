#!/usr/bin/env python
# encoding: UTF-8

import asyncio
import os

from cloudhands.burst.agent import Agent
from cloudhands.burst.agent import Job

from cloudhands.common.pipes import PipeQueue

class SessionAgent(Agent):

    @staticmethod
    def queue(args, config, loop=None, path=None):
        try:
            if path is None:
                path = os.path.expanduser(config["pipe.tokens"]["vcloud"])
        finally:
            return PipeQueue.pipequeue(path)
