#!/usr/bin/env python
# encoding: UTF-8


import asyncio
from collections import namedtuple
try:
    from functools import singledispatch
except ImportError:
    from singledispatch import singledispatch
import logging
import sqlite3
import warnings

from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry


Job = namedtuple("Job", ["uuid", "token", "artifact"])

class Agent:

    def __init__(self, workQ, args, config):
        self.work = workQ
        self.args = args
        self.config = config

    @staticmethod
    def queue(args, config, loop=None):
        return asyncio.Queue(loop=loop)

    @property
    def callbacks(self):
        raise NotImplementedError

    def jobs(self, session):
        raise NotImplementedError

    @asyncio.coroutine
    def __call__(self, loop, msgQ):
        raise NotImplementedError


@singledispatch
def message_handler(msg, *args, **kwargs):
    warnings.warn("No handler for {}".format(type(msg)))
    pass

@asyncio.coroutine
def operate(loop, msgQ, workers, args, config):
    log = logging.getLogger("cloudhands.burst.operate")
    tasks = [asyncio.Task(w(loop, msgQ)) for w in workers]
    session = Registry().connect(sqlite3, args.db).session
    initialise(session)
    pending = set()
    log.info("Starting task scheduler.")
    while any(task for task in tasks if not task.done()):
        for worker in workers:
            for job in worker.jobs(session):
                if job.uuid not in pending:
                    pending.add(job.uuid)
                    yield from worker.work.put(job)

        pause = 0.1 if pending else 1
        yield from asyncio.sleep(pause)

        try:
            while True:
                msg = msgQ.get_nowait()
                act = message_handler(msg, session)
                log.debug(act)
                pending.discard(act.artifact.uuid)
        except asyncio.QueueEmpty:
            continue
