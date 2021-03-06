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
    session = Registry().connect(sqlite3, args.db).session
    initialise(session)
    tasks = [asyncio.Task(w(loop, msgQ, session)) for w in workers]
    pending = set()
    log.info("Starting task scheduler.")
    while any(task for task in tasks if not task.done()):
        yield from asyncio.sleep(0)
        for worker in workers:
            for job in worker.jobs(session):
                if job.uuid not in pending:
                    pending.add(job.uuid)
                    log.debug("Sending {} to {}.".format(job, worker))
                    yield from worker.work.put(job)

        pause = 0.1 if pending else 1
        yield from asyncio.sleep(pause)

        try:
            while True:
                msg = msgQ.get_nowait()
                try:
                    act = session.merge(message_handler(msg, session))
                except Exception as e:
                    session.rollback()
                    log.error(e)
                else:
                    pending.discard(act.artifact.uuid)
                    session.close()  # Refresh or expire not effective here
                    log.debug(msg)
        except asyncio.QueueEmpty:
            continue
