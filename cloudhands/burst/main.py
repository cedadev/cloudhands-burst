#!/usr/bin/env python
# encoding: UTF-8

import argparse
import logging
import sys

import cloudhands.burst
import cloudhands.common

__doc__ = """
"""

def main(args):
    rv = 1
    logging.basicConfig(level=args.log_level,
    format="%(asctime)s %(levelname)-7s %(name)s|%(message)s")
    log = logging.getLogger("cloudhands.burst")
    if args.version:
        for mod in (cloudhands.burst, cloudhands.common):
            log.info("{:18} version {}".format(mod.__name__, mod.__version__))
        rv = 0
    return rv

def parser():
    rv = argparse.ArgumentParser(description=__doc__)
    rv.add_argument("--version", action="store_true", default=False,
    help="Print the current version number")
    rv.add_argument("-v", "--verbose", required=False,
    action="store_const", dest="log_level",
    const=logging.DEBUG, default=logging.INFO,
    help="Increase the verbosity of output")
    return rv

def run():
    p = parser()
    args = p.parse_args()
    rv = main(args)
    sys.exit(rv)

if __name__ == "__main__":
    run()
