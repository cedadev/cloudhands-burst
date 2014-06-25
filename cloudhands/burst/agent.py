#!/usr/bin/env python
# encoding: UTF-8


import asyncio
try:
    from functools import singledispatch
except ImportError:
    from singledispatch import singledispatch
import warnings


class Agent:

    def __init__(self, workQ, args, config):
        self.work = workQ
        self.args = args
        self.config = config

    @staticmethod
    def queue(args, config, loop=None):
        raise NotImplementedError

    @property
    def callbacks(self):
        raise NotImplementedError

    def jobs(self, session):
        raise NotImplementedError

    @asyncio.coroutine
    def __call__(self, loop, msgQ):
        raise NotImplementedError


@singledispatch
def message_handler(msg):
    warnings.warn("No handler for {}".format(type(msg)))
    pass

@asyncio.coroutine
def operate(loop, msgQ, workers, args, config):
    log = logging.getLogger("cloudhands.burst.operate")
    tasks = [asyncio.Task(w(loop, msgQ)) for w in workers]
    session = Registry().connect(sqlite3, args.db).session
    initialise(session)
    while any(task for task in tasks if not task.done()):
        yield from asyncio.sleep(0)
        for worker in workers:
            for job in worker.jobs(session):
                yield from worker.work.put(job)

        try:
            while True:
                msg = msgQ.get_nowait()
                log.debug(touch(msg, session))
        except asyncio.QueueEmpty:
            continue
