#!/usr/bin/env python
# encoding: UTF-8

import functools
import unittest
import xml.etree.ElementTree as ET

from cloudhands.burst.appliance import find_orgs
from cloudhands.burst.appliance import find_results
from cloudhands.burst.utils import find_xpath

xml_orglist = """
<OrgList xmlns="http://www.vmware.com/vcloud/v1.5"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/"
type="application/vnd.vmware.vcloud.orgList+xml"
xsi:schemaLocation="http://www.vmware.com/vcloud/v1.5
http://172.16.151.139/api/v1.5/schema/master.xsd">
    <Org
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/59432a59-d448"
name="managed_tenancy_test_org" type="application/vnd.vmware.vcloud.org+xml"
colour="blue"
size="small" />
    <Org
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/6483ae7d-2307"
name="un-managed_tenancy_test_org"
type="application/vnd.vmware.vcloud.org+xml"
colour="red"
size="small" />
    <Org
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/94704688-a5e2"
name="STFC-Administrator" type="application/vnd.vmware.vcloud.org+xml"
colour="blue"
size="small" />
    <Org
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/a93c9db9-7471"
name="System" type="application/vnd.vmware.vcloud.org+xml"
colour="red"
size="big" />
</OrgList>
"""

xml_queryresultrecords = """
<QueryResultRecords xmlns="http://www.vmware.com/vcloud/v1.5"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/networks?page=1&amp;pageSize=25&amp;format=records"
name="orgVdcNetwork" page="1" pageSize="25" total="1"
type="application/vnd.vmware.vcloud.query.records+xml"
xsi:schemaLocation="http://www.vmware.com/vcloud/v1.5
http://172.16.151.139/api/v1.5/schema/master.xsd">
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/networks?page=1&amp;pageSize=25&amp;format=references"
rel="alternate" type="application/vnd.vmware.vcloud.query.references+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/networks?page=1&amp;pageSize=25&amp;format=idrecords"
rel="alternate" type="application/vnd.vmware.vcloud.query.idrecords+xml" />
    <OrgVdcNetworkRecord connectedTo="jasmin-priv-external-network"
defaultGateway="192.168.2.1" dns1="8.8.8.8" dns2=" " dnsSuffix=" "
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/network/9604bd58-b05c-4fa3-9f9b-4e7991376f21"
isBusy="false" isIpScopeInherited="false" isShared="false" linkType="1"
name="un-managed-external-network" netmask="255.255.255.0"
task="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/task/d59edfc1-d608-4c4a-9661-ba4b19b328d6"
taskDetails=" " taskOperation="networkCreateOrgVdcNetwork"
taskStatus="success"
vdc="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44"
vdcName="un-managed_tenancy_test_org-std-compute-PAYG" />
</QueryResultRecords>"""

xml_instantiatevapp = """
<InstantiateVAppTemplateParams
xmlns="http://www.vmware.com/vcloud/v1.5" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"
name="Charlie-TEST5" deploy="false" powerOn="false">
<Description>Testing AppServer</Description>
<InstantiationParams>
<NetworkConfigSection>
<ovf:Info>The configuration parameters for logical networks</ovf:Info>
<NetworkConfig networkName="proxied-external-network">
<Configuration>
<ParentNetwork name="un-managed-external-network"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/network/9604bd58-b05c-4fa3-9f9b-4e7991376f21"/>
<FenceMode>bridged</FenceMode>
</Configuration>
</NetworkConfig>
</NetworkConfigSection>
</InstantiationParams>
<Source href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vAppTemplate/vappTemplate-1964b597-5477-4513-b126-4e6baa6032d6" />
</InstantiateVAppTemplateParams>
"""


class XMLTests(unittest.TestCase):

    def test_org_list_without_arguments(self):
        tree = ET.fromstring(xml_orglist)
        self.assertEqual(4, len(list(find_orgs(tree))))

    def test_org_list_by_href(self):
        tree = ET.fromstring(xml_orglist)
        self.assertEqual(1, len(list(find_orgs(tree,
        href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/a93c9db9-7471"))))

    def test_org_list_by_name(self):
        tree = ET.fromstring(xml_orglist)
        self.assertEqual(
            1, len(list(find_orgs(tree, name="un-managed_tenancy_test_org"))))

    def test_org_list_by_multiple_attributes(self):
        tree = ET.fromstring(xml_orglist)
        self.assertEqual(
            1, len(list(find_orgs(tree, size="big", colour="red"))))

    def test_queryresultrecords_by_name(self):
        tree = ET.fromstring(xml_queryresultrecords)
        self.assertEqual(
            1, len(list(find_results(
                tree, name="un-managed-external-network"))))
