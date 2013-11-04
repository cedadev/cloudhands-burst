#!/usr/bin/env python
# encoding: UTF-8

from collections import namedtuple
import unittest

from cloudhands.burst.controller import BurstController
from cloudhands.common.schema import DCStatus
from cloudhands.common.schema import Touch


class BurstControllerTests(unittest.TestCase):

    fakeConfig = {
        "user": {
            "name": "test user",
            "pass": "qwertyuiop"},
        "host": {
            "name": "host.domain",
            "port": "1234",
            "api_version": "1.5"}
    }

    def fakeDriverDown(*args, **kwargs):
        fixed = namedtuple("ResultSet", ["vdcs"])
        return fixed(vdcs=[])

    def fakeDriverUp(*args, **kwargs):
        fixed = namedtuple("ResultSet", ["vdcs"])
        return fixed(vdcs=[{}])

    def test_check_dc_with_no_vdcs(self):
        bc = BurstController(
            config=BurstControllerTests.fakeConfig,
            driver=BurstControllerTests.fakeDriverDown)
        self.assertEqual(0, bc.session.query(Touch).count())
        self.assertFalse(bc.check_DC())
        touch = bc.session.query(Touch).first()
        self.assertTrue(touch)
        self.assertEqual("down", touch.state.name)

    def test_check_dc_with_fake_vdcs(self):
        bc = BurstController(
            config=BurstControllerTests.fakeConfig,
            driver=BurstControllerTests.fakeDriverUp
        )
        self.assertEqual(0, bc.session.query(Touch).count())
        self.assertTrue(bc.check_DC())
        touch = bc.session.query(Touch).first()
        self.assertTrue(touch)
        self.assertEqual("up", touch.state.name)
