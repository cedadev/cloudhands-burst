#!/usr/bin/env python
# encoding: UTF-8

import functools
import unittest
import xml.etree.ElementTree as ET

from chameleon import PageTemplateFile
import pkg_resources

from cloudhands.burst.appliance import find_catalogueitems
from cloudhands.burst.appliance import find_orgs
from cloudhands.burst.appliance import find_results
from cloudhands.burst.appliance import find_templates
from cloudhands.burst.utils import find_xpath

xml_catalog = """
<Catalog xmlns="http://www.vmware.com/vcloud/v1.5"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalog/e7025d98-6591-4c2d-90d6-63cb7aaa8a3f"
id="urn:vcloud:catalog:e7025d98-6591-4c2d-90d6-63cb7aaa8a3f" name="Public
catalog" type="application/vnd.vmware.vcloud.catalog+xml"
xsi:schemaLocation="http://www.vmware.com/vcloud/v1.5
http://172.16.151.139/api/v1.5/schema/master.xsd">
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/94704688-a5e2-4336-a54d-feecd56c82aa"
rel="up" type="application/vnd.vmware.vcloud.org+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalog/e7025d98-6591-4c2d-90d6-63cb7aaa8a3f/metadata"
rel="down" type="application/vnd.vmware.vcloud.metadata+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalog/e7025d98-6591-4c2d-90d6-63cb7aaa8a3f/catalogItems"
rel="add" type="application/vnd.vmware.vcloud.catalogItem+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalog/e7025d98-6591-4c2d-90d6-63cb7aaa8a3f/action/upload"
rel="add" type="application/vnd.vmware.vcloud.media+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalog/e7025d98-6591-4c2d-90d6-63cb7aaa8a3f/action/upload"
rel="add" type="application/vnd.vmware.vcloud.uploadVAppTemplateParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalog/e7025d98-6591-4c2d-90d6-63cb7aaa8a3f/action/copy"
rel="copy"
type="application/vnd.vmware.vcloud.copyOrMoveCatalogItemParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalog/e7025d98-6591-4c2d-90d6-63cb7aaa8a3f/action/move"
rel="move"
type="application/vnd.vmware.vcloud.copyOrMoveCatalogItemParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalog/e7025d98-6591-4c2d-90d6-63cb7aaa8a3f/action/captureVApp"
rel="add" type="application/vnd.vmware.vcloud.captureVAppParams+xml" />
    <Description>This template is asscesible to all other organisaitons. Only
public templates for use by other vCloud organisaiotns should be placed in
here.</Description>
    <CatalogItems>
        <CatalogItem
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalogItem/12aa90b3-811c-4e06-8210-a32d74129bc5"
id="12aa90b3-811c-4e06-8210-a32d74129bc5" name="centos6-stemcell"
type="application/vnd.vmware.vcloud.catalogItem+xml" />
        <CatalogItem
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalogItem/92525027-3e51-48a8-9376-4b4f80fc9e86"
id="92525027-3e51-48a8-9376-4b4f80fc9e86" name="cm002.cems.rl.ac.uk"
type="application/vnd.vmware.vcloud.catalogItem+xml" />
        <CatalogItem
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalogItem/b37615a3-0657-4602-bd83-5f5593f5e05e"
id="b37615a3-0657-4602-bd83-5f5593f5e05e" name="ubuntu-14.04-server-amd64.iso"
type="application/vnd.vmware.vcloud.catalogItem+xml" />
        <CatalogItem
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/catalogItem/bdd0f6e9-7d02-45c4-8b96-0bea3139f592"
id="bdd0f6e9-7d02-45c4-8b96-0bea3139f592" name="stemcell-test"
type="application/vnd.vmware.vcloud.catalogItem+xml" />
    </CatalogItems>
    <IsPublished>true</IsPublished>
    <DateCreated>2014-04-11T09:42:47.407+01:00</DateCreated>
    <VersionNumber>21</VersionNumber>
</Catalog>
"""

xml_error = """
<Error xmlns="http://www.vmware.com/vcloud/v1.5"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" majorErrorCode="400"
message="The VCD entity test_16 already exists."
minorErrorCode="DUPLICATE_NAME"
stackTrace="com.vmware.vcloud.api.presentation.service.DuplicateNameException:
The VCD entity test_16 already exists.  at
com.vmware.ssdc.backend.services.impl.VAppManagerImpl.convertDuplicateNameException(VAppManagerImpl.java:1074) ...
xsi:schemaLocation="http://www.vmware.com/vcloud/v1.5
http://172.16.151.139/api/v1.5/schema/master.xsd" />
"""

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

xml_vapp = """
<VApp xmlns="http://www.vmware.com/vcloud/v1.5"
xmlns:ns2="http://schemas.dmtf.org/ovf/envelope/1"
xmlns:ns3="http://www.vmware.com/vcloud/extension/v1.5"
xmlns:ns4="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData"
xmlns:ns5="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData"
xmlns:ns6="http://www.vmware.com/schema/ovf"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" deployed="false"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a"
id="urn:vcloud:vapp:a662ee42-03cd-4201-879c-a55ac11de94a" name="test_02"
ovfDescriptorUploaded="true" status="8"
type="application/vnd.vmware.vcloud.vApp+xml"
xsi:schemaLocation="http://www.vmware.com/vcloud/extension/v1.5
http://172.16.151.139/api/v1.5/schema/vmwextensions.xsd
http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData
http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2.22.0/CIM_VirtualSystemSettingData.xsd
http://www.vmware.com/schema/ovf http://www.vmware.com/schema/ovf
http://schemas.dmtf.org/ovf/envelope/1
http://schemas.dmtf.org/ovf/envelope/1/dsp8023_1.1.0.xsd
http://www.vmware.com/vcloud/v1.5
http://172.16.151.139/api/v1.5/schema/master.xsd
http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData
http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2.22.0/CIM_ResourceAllocationSettingData.xsd">
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/power/action/powerOn"
rel="power:powerOn" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/action/deploy"
rel="deploy" type="application/vnd.vmware.vcloud.deployVAppParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/network/dd6215d9-b624-4bdb-972b-75fa5443dce5"
name="un-managed-external-network" rel="down"
type="application/vnd.vmware.vcloud.vAppNetwork+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/controlAccess/"
rel="down" type="application/vnd.vmware.vcloud.controlAccess+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/action/controlAccess"
rel="controlAccess" type="application/vnd.vmware.vcloud.controlAccess+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/action/recomposeVApp"
rel="recompose" type="application/vnd.vmware.vcloud.recomposeVAppParams+xml"
/>
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/action/enterMaintenanceMode"
rel="enterMaintenanceMode" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44"
rel="up" type="application/vnd.vmware.vcloud.vdc+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a"
rel="edit" type="application/vnd.vmware.vcloud.vApp+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a"
rel="remove" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/action/enableDownload"
rel="enable" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/action/disableDownload"
rel="disable" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/owner"
rel="down" type="application/vnd.vmware.vcloud.owner+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/metadata"
rel="down" type="application/vnd.vmware.vcloud.metadata+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/ovf"
rel="ovf" type="text/xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/productSections/"
rel="down" type="application/vnd.vmware.vcloud.productSections+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/action/createSnapshot"
rel="snapshot:create"
type="application/vnd.vmware.vcloud.createSnapshotParams+xml" />
    <Description>FIXME: Description</Description>
    <LeaseSettingsSection
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/leaseSettingsSection/"
type="application/vnd.vmware.vcloud.leaseSettingsSection+xml"
ns2:required="false">
        <ns2:Info>Lease settings section</ns2:Info>
        <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/leaseSettingsSection/"
rel="edit" type="application/vnd.vmware.vcloud.leaseSettingsSection+xml" />
        <DeploymentLeaseInSeconds>0</DeploymentLeaseInSeconds>
        <StorageLeaseInSeconds>0</StorageLeaseInSeconds>
    </LeaseSettingsSection>
    <ns2:StartupSection
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/startupSection/"
type="application/vnd.vmware.vcloud.startupSection+xml">
        <ns2:Info>VApp startup section</ns2:Info>
        <ns2:Item ns2:id="centos6-stemcell" ns2:order="0"
ns2:startAction="powerOn" ns2:startDelay="0" ns2:stopAction="powerOff"
ns2:stopDelay="0" />
        <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/startupSection/"
rel="edit" type="application/vnd.vmware.vcloud.startupSection+xml" />
    </ns2:StartupSection>
    <ns2:NetworkSection
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/networkSection/"
type="application/vnd.vmware.vcloud.networkSection+xml">
        <ns2:Info>The list of logical networks</ns2:Info>
        <ns2:Network ns2:name="un-managed-external-network">
            <ns2:Description />
        </ns2:Network>
    </ns2:NetworkSection>
    <NetworkConfigSection
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/networkConfigSection/"
type="application/vnd.vmware.vcloud.networkConfigSection+xml"
ns2:required="false">
        <ns2:Info>The configuration parameters for logical networks</ns2:Info>
        <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/networkConfigSection/"
rel="edit" type="application/vnd.vmware.vcloud.networkConfigSection+xml" />
        <NetworkConfig networkName="un-managed-external-network">
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/network/dd6215d9-b624-4bdb-972b-75fa5443dce5/action/reset"
rel="repair" />
            <Description />
            <Configuration>
                <IpScopes>
                    <IpScope>
                        <IsInherited>true</IsInherited>
                        <Gateway>192.168.2.1</Gateway>
                        <Netmask>255.255.255.0</Netmask>
                        <Dns1>8.8.8.8</Dns1>
                        <IsEnabled>true</IsEnabled>
                        <IpRanges>
                            <IpRange>
                                <StartAddress>192.168.2.2</StartAddress>
                                <EndAddress>192.168.2.254</EndAddress>
                            </IpRange>
                        </IpRanges>
                    </IpScope>
                </IpScopes>
                <ParentNetwork
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/network/9604bd58-b05c-4fa3-9f9b-4e7991376f21"
id="9604bd58-b05c-4fa3-9f9b-4e7991376f21" name="un-managed-external-network"
/>
                <FenceMode>bridged</FenceMode>
                <RetainNetInfoAcrossDeployments>false</RetainNetInfoAcrossDeployments>
            </Configuration>
            <IsDeployed>false</IsDeployed>
        </NetworkConfig>
    </NetworkConfigSection>
    <SnapshotSection
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a/snapshotSection"
type="application/vnd.vmware.vcloud.snapshotSection+xml" ns2:required="false">
        <ns2:Info>Snapshot information section</ns2:Info>
    </SnapshotSection>
    <DateCreated>2014-07-03T09:22:21.353+01:00</DateCreated>
    <Owner type="application/vnd.vmware.vcloud.owner+xml">
        <User
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/user/cc8a9479-be2d-40c2-8347-b5a0a55d160c"
name="system" type="application/vnd.vmware.admin.user+xml" />
    </Owner>
    <InMaintenanceMode>false</InMaintenanceMode>
    <Children>
        <Vm deployed="false"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4"
id="urn:vcloud:vm:ca9f7b28-7473-4293-9a9d-ce836c6017b4"
name="centos6-stemcell" needsCustomization="true"
nestedHypervisorEnabled="false" status="8"
type="application/vnd.vmware.vcloud.vm+xml">
            <VCloudExtension required="false">
                <ns3:VmVimInfo>
                    <ns3:VmVimObjectRef>
                        <ns3:VimServerRef
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/extension/vimServer/d901b67e-55ba-4f52-9025-df4a577f3615"
name="vjasmin-vc-test"
type="application/vnd.vmware.admin.vmwvirtualcenter+xml" />
                        <ns3:MoRef>vm-567</ns3:MoRef>
                        <ns3:VimObjectType>VIRTUAL_MACHINE</ns3:VimObjectType>
                    </ns3:VmVimObjectRef>
                    <ns3:DatastoreVimObjectRef>
                        <ns3:VimServerRef
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/extension/vimServer/d901b67e-55ba-4f52-9025-df4a577f3615"
name="vjasmin-vc-test"
type="application/vnd.vmware.admin.vmwvirtualcenter+xml" />
                        <ns3:MoRef>datastore-23</ns3:MoRef>
                        <ns3:VimObjectType>DATASTORE</ns3:VimObjectType>
                    </ns3:DatastoreVimObjectRef>
                    <ns3:HostVimObjectRef>
                        <ns3:VimServerRef
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/extension/vimServer/d901b67e-55ba-4f52-9025-df4a577f3615"
name="vjasmin-vc-test"
type="application/vnd.vmware.admin.vmwvirtualcenter+xml" />
                        <ns3:MoRef>host-19</ns3:MoRef>
                        <ns3:VimObjectType>HOST</ns3:VimObjectType>
                    </ns3:HostVimObjectRef>
                    <ns3:VirtualDisksMaxChainLength>11</ns3:VirtualDisksMaxChainLength>
                </ns3:VmVimInfo>
            </VCloudExtension>
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/power/action/powerOn"
rel="power:powerOn" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/action/deploy"
rel="deploy" type="application/vnd.vmware.vcloud.deployVAppParams+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4"
rel="edit" type="application/vnd.vmware.vcloud.vm+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4"
rel="remove" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/metadata"
rel="down" type="application/vnd.vmware.vcloud.metadata+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/complianceResult"
rel="down" type="application/vnd.vmware.vm.complianceResult+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/productSections/"
rel="down" type="application/vnd.vmware.vcloud.productSections+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/screen"
rel="screen:thumbnail" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/media/action/insertMedia"
rel="media:insertMedia"
type="application/vnd.vmware.vcloud.mediaInsertOrEjectParams+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/media/action/ejectMedia"
rel="media:ejectMedia"
type="application/vnd.vmware.vcloud.mediaInsertOrEjectParams+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/disk/action/attach"
rel="disk:attach"
type="application/vnd.vmware.vcloud.diskAttachOrDetachParams+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/disk/action/detach"
rel="disk:detach"
type="application/vnd.vmware.vcloud.diskAttachOrDetachParams+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/action/consolidate"
rel="consolidate" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/action/relocate"
rel="relocate" type="application/vnd.vmware.vcloud.relocateVmParams+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/action/enableNestedHypervisor"
rel="enable" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/action/checkCompliance"
rel="checkCompliance" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/action/createSnapshot"
rel="snapshot:create"
type="application/vnd.vmware.vcloud.createSnapshotParams+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/action/reconfigureVm"
name="centos6-stemcell" rel="reconfigureVm"
type="application/vnd.vmware.vcloud.vm+xml" />
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-a662ee42-03cd-4201-879c-a55ac11de94a"
rel="up" type="application/vnd.vmware.vcloud.vApp+xml" />
            <Description />
            <ns2:VirtualHardwareSection ns2:transport=""
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/"
type="application/vnd.vmware.vcloud.virtualHardwareSection+xml">
                <ns2:Info>Virtual hardware requirements</ns2:Info>
                <ns2:System>
                    <ns4:ElementName>Virtual Hardware Family</ns4:ElementName>
                    <ns4:InstanceID>0</ns4:InstanceID>
                    <ns4:VirtualSystemIdentifier>centos6-stemcell</ns4:VirtualSystemIdentifier>
                    <ns4:VirtualSystemType>vmx-10</ns4:VirtualSystemType>
                </ns2:System>
                <ns2:Item>
                    <ns5:Address>00:50:56:01:00:c5</ns5:Address>
                    <ns5:AddressOnParent>0</ns5:AddressOnParent>
                    <ns5:AutomaticAllocation>true</ns5:AutomaticAllocation>
                    <ns5:Connection ipAddress="192.168.2.5"
ipAddressingMode="POOL"
primaryNetworkConnection="true">un-managed-external-network</ns5:Connection>
                    <ns5:Description>Vmxnet3 ethernet adapter on
"un-managed-external-network"</ns5:Description>
                    <ns5:ElementName>Network adapter 0</ns5:ElementName>
                    <ns5:InstanceID>1</ns5:InstanceID>
                    <ns5:ResourceSubType>VMXNET3</ns5:ResourceSubType>
                    <ns5:ResourceType>10</ns5:ResourceType>
                </ns2:Item>
                <ns2:Item>
                    <ns5:Address>0</ns5:Address>
                    <ns5:Description>SCSI Controller</ns5:Description>
                    <ns5:ElementName>SCSI Controller 0</ns5:ElementName>
                    <ns5:InstanceID>2</ns5:InstanceID>
                    <ns5:ResourceSubType>VirtualSCSI</ns5:ResourceSubType>
                    <ns5:ResourceType>6</ns5:ResourceType>
                </ns2:Item>
                <ns2:Item>
                    <ns5:AddressOnParent>0</ns5:AddressOnParent>
                    <ns5:Description>Hard disk</ns5:Description>
                    <ns5:ElementName>Hard disk 1</ns5:ElementName>
                    <ns5:HostResource busSubType="VirtualSCSI" busType="6"
capacity="16384" />
                    <ns5:InstanceID>2000</ns5:InstanceID>
                    <ns5:Parent>2</ns5:Parent>
                    <ns5:ResourceType>17</ns5:ResourceType>
                </ns2:Item>
                <ns2:Item>
                    <ns5:Address>0</ns5:Address>
                    <ns5:Description>IDE Controller</ns5:Description>
                    <ns5:ElementName>IDE Controller 0</ns5:ElementName>
                    <ns5:InstanceID>3</ns5:InstanceID>
                    <ns5:ResourceType>5</ns5:ResourceType>
                </ns2:Item>
                <ns2:Item>
                    <ns5:AddressOnParent>0</ns5:AddressOnParent>
                    <ns5:AutomaticAllocation>false</ns5:AutomaticAllocation>
                    <ns5:Description>CD/DVD Drive</ns5:Description>
                    <ns5:ElementName>CD/DVD Drive 1</ns5:ElementName>
                    <ns5:HostResource />
                    <ns5:InstanceID>3000</ns5:InstanceID>
                    <ns5:Parent>3</ns5:Parent>
                    <ns5:ResourceType>15</ns5:ResourceType>
                </ns2:Item>
                <ns2:Item>
                    <ns5:AddressOnParent>0</ns5:AddressOnParent>
                    <ns5:AutomaticAllocation>false</ns5:AutomaticAllocation>
                    <ns5:Description>Floppy Drive</ns5:Description>
                    <ns5:ElementName>Floppy Drive 1</ns5:ElementName>
                    <ns5:HostResource />
                    <ns5:InstanceID>8000</ns5:InstanceID>
                    <ns5:ResourceType>14</ns5:ResourceType>
                </ns2:Item>
                <ns2:Item
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/cpu"
type="application/vnd.vmware.vcloud.rasdItem+xml">
                    <ns5:AllocationUnits>hertz * 10^6</ns5:AllocationUnits>
                    <ns5:Description>Number of Virtual CPUs</ns5:Description>
                    <ns5:ElementName>1 virtual CPU(s)</ns5:ElementName>
                    <ns5:InstanceID>4</ns5:InstanceID>
                    <ns5:Reservation>0</ns5:Reservation>
                    <ns5:ResourceType>3</ns5:ResourceType>
                    <ns5:VirtualQuantity>1</ns5:VirtualQuantity>
                    <ns5:Weight>0</ns5:Weight>
                    <ns6:CoresPerSocket
ns2:required="false">1</ns6:CoresPerSocket>
                    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/cpu"
rel="edit" type="application/vnd.vmware.vcloud.rasdItem+xml" />
                </ns2:Item>
                <ns2:Item
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/memory"
type="application/vnd.vmware.vcloud.rasdItem+xml">
                    <ns5:AllocationUnits>byte * 2^20</ns5:AllocationUnits>
                    <ns5:Description>Memory Size</ns5:Description>
                    <ns5:ElementName>2048 MB of memory</ns5:ElementName>
                    <ns5:InstanceID>5</ns5:InstanceID>
                    <ns5:Reservation>0</ns5:Reservation>
                    <ns5:ResourceType>4</ns5:ResourceType>
                    <ns5:VirtualQuantity>2048</ns5:VirtualQuantity>
                    <ns5:Weight>0</ns5:Weight>
                    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/memory"
rel="edit" type="application/vnd.vmware.vcloud.rasdItem+xml" />
                </ns2:Item>
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/"
rel="edit" type="application/vnd.vmware.vcloud.virtualHardwareSection+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/cpu"
rel="down" type="application/vnd.vmware.vcloud.rasdItem+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/cpu"
rel="edit" type="application/vnd.vmware.vcloud.rasdItem+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/memory"
rel="down" type="application/vnd.vmware.vcloud.rasdItem+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/memory"
rel="edit" type="application/vnd.vmware.vcloud.rasdItem+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/disks"
rel="down" type="application/vnd.vmware.vcloud.rasdItemsList+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/disks"
rel="edit" type="application/vnd.vmware.vcloud.rasdItemsList+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/media"
rel="down" type="application/vnd.vmware.vcloud.rasdItemsList+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/networkCards"
rel="down" type="application/vnd.vmware.vcloud.rasdItemsList+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/networkCards"
rel="edit" type="application/vnd.vmware.vcloud.rasdItemsList+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/serialPorts"
rel="down" type="application/vnd.vmware.vcloud.rasdItemsList+xml" />
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/virtualHardwareSection/serialPorts"
rel="edit" type="application/vnd.vmware.vcloud.rasdItemsList+xml" />
            </ns2:VirtualHardwareSection>
            <ns2:OperatingSystemSection ns2:id="101"
ns6:osType="centos64Guest"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/operatingSystemSection/"
type="application/vnd.vmware.vcloud.operatingSystemSection+xml">
                <ns2:Info>Specifies the operating system installed</ns2:Info>
                <ns2:Description>CentOS 4/5/6 (64-bit)</ns2:Description>
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/operatingSystemSection/"
rel="edit" type="application/vnd.vmware.vcloud.operatingSystemSection+xml" />
            </ns2:OperatingSystemSection>
            <NetworkConnectionSection
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/networkConnectionSection/"
type="application/vnd.vmware.vcloud.networkConnectionSection+xml"
ns2:required="false">
                <ns2:Info>Specifies the available VM network
connections</ns2:Info>
                <PrimaryNetworkConnectionIndex>0</PrimaryNetworkConnectionIndex>
                <NetworkConnection needsCustomization="true"
network="un-managed-external-network">
                    <NetworkConnectionIndex>0</NetworkConnectionIndex>
                    <IpAddress>192.168.2.5</IpAddress>
                    <IsConnected>true</IsConnected>
                    <MACAddress>00:50:56:01:00:c5</MACAddress>
                    <IpAddressAllocationMode>POOL</IpAddressAllocationMode>
                </NetworkConnection>
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/networkConnectionSection/"
rel="edit" type="application/vnd.vmware.vcloud.networkConnectionSection+xml"
/>
            </NetworkConnectionSection>
            <GuestCustomizationSection
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/guestCustomizationSection/"
type="application/vnd.vmware.vcloud.guestCustomizationSection+xml"
ns2:required="false">
                <ns2:Info>Specifies Guest OS Customization Settings</ns2:Info>
                <Enabled>true</Enabled>
                <ChangeSid>false</ChangeSid>
                <VirtualMachineId>ca9f7b28-7473-4293-9a9d-ce836c6017b4</VirtualMachineId>
                <JoinDomainEnabled>false</JoinDomainEnabled>
                <UseOrgSettings>false</UseOrgSettings>
                <AdminPasswordEnabled>true</AdminPasswordEnabled>
                <AdminPasswordAuto>false</AdminPasswordAuto>
                <AdminPassword>jasminadmin</AdminPassword>
                <AdminAutoLogonEnabled>false</AdminAutoLogonEnabled>
                <AdminAutoLogonCount>1</AdminAutoLogonCount>
                <ResetPasswordRequired>false</ResetPasswordRequired>
                <CustomizationScript>#!/bin/sh
if [ x$1 == x"precustomization" ]; then
/root/pre_customisation.sh
elif [ x$1 == x"postcustomization" ]; then
/root/post_customisation.sh
fi</CustomizationScript>
                <ComputerName>centos6</ComputerName>
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/guestCustomizationSection/"
rel="edit" type="application/vnd.vmware.vcloud.guestCustomizationSection+xml"
/>
            </GuestCustomizationSection>
            <RuntimeInfoSection
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/runtimeInfoSection"
type="application/vnd.vmware.vcloud.virtualHardwareSection+xml">
                <ns2:Info>Specifies Runtime info</ns2:Info>
                <VMWareTools version="9344" />
            </RuntimeInfoSection>
            <SnapshotSection
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/snapshotSection"
type="application/vnd.vmware.vcloud.snapshotSection+xml" ns2:required="false">
                <ns2:Info>Snapshot information section</ns2:Info>
            </SnapshotSection>
            <VAppScopedLocalId>centos6</VAppScopedLocalId>
            <VmCapabilities
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/vmCapabilities/"
type="application/vnd.vmware.vcloud.vmCapabilitiesSection+xml">
                <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vm-ca9f7b28-7473-4293-9a9d-ce836c6017b4/vmCapabilities/"
rel="edit" type="application/vnd.vmware.vcloud.vmCapabilitiesSection+xml" />
                <MemoryHotAddEnabled>true</MemoryHotAddEnabled>
                <CpuHotAddEnabled>true</CpuHotAddEnabled>
            </VmCapabilities>
            <StorageProfile
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdcStorageProfile/65c97f16-157d-45bd-89ee-c22b0995b187"
name="Tier2" type="application/vnd.vmware.vcloud.vdcStorageProfile+xml" />
        </Vm>
    </Children>
</VApp>"""

xml_vapp = """
<VApp xmlns="http://www.vmware.com/vcloud/v1.5"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" deployed="false"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-803919bb-25c8-449e-81a8-877732212463"
id="urn:vcloud:vapp:803919bb-25c8-449e-81a8-877732212463" name="test_01"
ovfDescriptorUploaded="true" status="0"
type="application/vnd.vmware.vcloud.vApp+xml"
xsi:schemaLocation="http://www.vmware.com/vcloud/v1.5
http://172.16.151.139/api/v1.5/schema/master.xsd">
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/network/30af3ea4-8b87-4ea7-b5af-457c9e610417"
name="un-managed-external-network" rel="down"
type="application/vnd.vmware.vcloud.vAppNetwork+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-803919bb-25c8-449e-81a8-877732212463/controlAccess/"
rel="down" type="application/vnd.vmware.vcloud.controlAccess+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44"
rel="up" type="application/vnd.vmware.vcloud.vdc+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-803919bb-25c8-449e-81a8-877732212463/owner"
rel="down" type="application/vnd.vmware.vcloud.owner+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-803919bb-25c8-449e-81a8-877732212463/metadata"
rel="down" type="application/vnd.vmware.vcloud.metadata+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-803919bb-25c8-449e-81a8-877732212463/ovf"
rel="ovf" type="text/xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-803919bb-25c8-449e-81a8-877732212463/productSections/"
rel="down" type="application/vnd.vmware.vcloud.productSections+xml" />
    <Description>FIXME: Description</Description>
    <Tasks>
        <Task cancelRequested="false"
expiryTime="2014-09-29T09:09:36.709+01:00"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/task/26a1ff7e-9bdc-4499-b109-50e0063ab95a"
id="urn:vcloud:task:26a1ff7e-9bdc-4499-b109-50e0063ab95a" name="task"
operation="Creating Virtual Application
test_01(803919bb-25c8-449e-81a8-877732212463)"
operationName="vdcInstantiateVapp" serviceNamespace="com.vmware.vcloud"
startTime="2014-07-01T09:09:36.709+01:00" status="running"
type="application/vnd.vmware.vcloud.task+xml">
            <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/task/26a1ff7e-9bdc-4499-b109-50e0063ab95a/action/cancel"
rel="task:cancel" />
            <Owner
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-803919bb-25c8-449e-81a8-877732212463"
name="test_01" type="application/vnd.vmware.vcloud.vApp+xml" />
            <User
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/user/04689d16-a695-4ccd-bce2-7c5a5cf7fff3"
name="system" type="application/vnd.vmware.admin.user+xml" />
            <Organization
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/6483ae7d-2307-4856-a1c9-109751545b4c"
name="un-managed_tenancy_test_org"
type="application/vnd.vmware.vcloud.org+xml" />
            <Progress>1</Progress>
            <Details />
        </Task>
    </Tasks>
    <DateCreated>2014-07-01T09:09:36.030+01:00</DateCreated>
    <Owner type="application/vnd.vmware.vcloud.owner+xml">
        <User
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/user/cc8a9479-be2d-40c2-8347-b5a0a55d160c"
name="system" type="application/vnd.vmware.admin.user+xml" />
    </Owner>
    <InMaintenanceMode>false</InMaintenanceMode>
</VApp>
"""

xml_vapp_error = """
<VApp xmlns="http://www.vmware.com/vcloud/v1.5"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" deployed="false"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a"
id="urn:vcloud:vapp:c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a" name="test_03"
ovfDescriptorUploaded="true" status="-1"
type="application/vnd.vmware.vcloud.vApp+xml"
xsi:schemaLocation="http://www.vmware.com/vcloud/v1.5
http://172.16.151.139/api/v1.5/schema/master.xsd">
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/network/ce49e558-672d-492a-896c-020d27380661"
name="un-managed-external-network" rel="down"
type="application/vnd.vmware.vcloud.vAppNetwork+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a/controlAccess/"
rel="down" type="application/vnd.vmware.vcloud.controlAccess+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a/action/recomposeVApp"
rel="recompose" type="application/vnd.vmware.vcloud.recomposeVAppParams+xml"
/>
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44"
rel="up" type="application/vnd.vmware.vcloud.vdc+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a"
rel="remove" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a/owner"
rel="down" type="application/vnd.vmware.vcloud.owner+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a/metadata"
rel="down" type="application/vnd.vmware.vcloud.metadata+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a/ovf"
rel="ovf" type="text/xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a/productSections/"
rel="down" type="application/vnd.vmware.vcloud.productSections+xml" />
    <Description>FIXME: Description</Description>
    <Tasks>
        <Task cancelRequested="false" endTime="2014-07-02T13:38:20.227+01:00"
expiryTime="2014-09-30T13:38:19.603+01:00"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/task/00ca94a8-d53e-4eba-810a-ab701c518633"
id="urn:vcloud:task:00ca94a8-d53e-4eba-810a-ab701c518633" name="task"
operation="Created Virtual Application
test_03(c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a)"
operationName="vdcInstantiateVapp" serviceNamespace="com.vmware.vcloud"
startTime="2014-07-02T13:38:19.603+01:00" status="error"
type="application/vnd.vmware.vcloud.task+xml">
            <Owner
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-c5c4ddd1-5c37-43bb-a933-6dbf6a0e9a9a"
name="test_03" type="application/vnd.vmware.vcloud.vApp+xml" />
            <Error majorErrorCode="400" message="The requested operation on VM
&quot;vm-172&quot; is not supported since the VM is disconnected."
minorErrorCode="BAD_REQUEST"
stackTrace="com.vmware.vcloud.api.presentation.service.BadRequestException:
The requested operation on VM &quot;vm-172&quot; is not supported since the VM
is disconnected.  at
com.vmware.ssdc.backend.services.impl.VmManagerImpl.validateVmConnected(VmManagerImpl.java:1856)
at sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)  at
sun.reflect.NativeMethodAccessorImpl.invoke(Unknown Source)  at
java.util.concurrent.FutureTask$Sync.innerRun(Unknown Source)  at
java.util.concurrent.FutureTask.run(Unknown Source)  at
java.util.concurrent.ThreadPoolExecutor.runWorker(Unknown Source)  at
java.util.concurrent.ThreadPoolExecutor$Worker.run(Unknown Source)  at
java.lang.Thread.run(Unknown Source) " />
            <User
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/user/04689d16-a695-4ccd-bce2-7c5a5cf7fff3"
name="system" type="application/vnd.vmware.admin.user+xml" />
            <Organization
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/6483ae7d-2307-4856-a1c9-109751545b4c"
name="un-managed_tenancy_test_org"
type="application/vnd.vmware.vcloud.org+xml" />
            <Progress>1</Progress>
            <Details>  The requested operation on VM "vm-172" is not supported
since the VM is disconnected.</Details>
        </Task>
    </Tasks>
    <DateCreated>2014-07-02T13:38:18.777+01:00</DateCreated>
    <Owner type="application/vnd.vmware.vcloud.owner+xml">
        <User
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/user/cc8a9479-be2d-40c2-8347-b5a0a55d160c"
name="system" type="application/vnd.vmware.admin.user+xml" />
    </Owner>
    <InMaintenanceMode>false</InMaintenanceMode>
</VApp>
"""

xml_vdc = """
<Vdc xmlns="http://www.vmware.com/vcloud/v1.5"
xmlns:ns2="http://www.vmware.com/vcloud/extension/v1.5"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44"
id="urn:vcloud:vdc:4cfa412c-41a8-483b-ad05-62e1ea72da44"
name="un-managed_tenancy_test_org-std-compute-PAYG" status="1"
type="application/vnd.vmware.vcloud.vdc+xml"
xsi:schemaLocation="http://www.vmware.com/vcloud/extension/v1.5
http://172.16.151.139/api/v1.5/schema/vmwextensions.xsd
http://www.vmware.com/vcloud/v1.5
http://172.16.151.139/api/v1.5/schema/master.xsd">
    <VCloudExtension required="false">
        <ns2:VimObjectRef>
            <ns2:VimServerRef
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/extension/vimServer/d901b67e-55ba-4f52-9025-df4a577f3615"
name="VC" type="application/vnd.vmware.admin.vmwvirtualcenter+xml" />
            <ns2:MoRef>resgroup-58</ns2:MoRef>
            <ns2:VimObjectType>RESOURCE_POOL</ns2:VimObjectType>
        </ns2:VimObjectRef>
    </VCloudExtension>
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/6483ae7d-2307-4856-a1c9-109751545b4c"
rel="up" type="application/vnd.vmware.vcloud.org+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/metadata"
rel="down" type="application/vnd.vmware.vcloud.metadata+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/action/uploadVAppTemplate"
rel="add" type="application/vnd.vmware.vcloud.uploadVAppTemplateParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/media"
rel="add" type="application/vnd.vmware.vcloud.media+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/action/instantiateOvf"
rel="add" type="application/vnd.vmware.vcloud.instantiateOvfParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/action/instantiateVAppTemplate"
rel="add"
type="application/vnd.vmware.vcloud.instantiateVAppTemplateParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/action/cloneVApp"
rel="add" type="application/vnd.vmware.vcloud.cloneVAppParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/action/cloneVAppTemplate"
rel="add" type="application/vnd.vmware.vcloud.cloneVAppTemplateParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/action/cloneMedia"
rel="add" type="application/vnd.vmware.vcloud.cloneMediaParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/action/captureVApp"
rel="add" type="application/vnd.vmware.vcloud.captureVAppParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/action/composeVApp"
rel="add" type="application/vnd.vmware.vcloud.composeVAppParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/disk"
rel="add" type="application/vnd.vmware.vcloud.diskCreateParams+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/edgeGateways"
rel="edgeGateways" type="application/vnd.vmware.vcloud.query.records+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/networks"
rel="add" type="application/vnd.vmware.vcloud.orgVdcNetwork+xml" />
    <Link
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/admin/vdc/4cfa412c-41a8-483b-ad05-62e1ea72da44/networks"
rel="orgVdcNetworks" type="application/vnd.vmware.vcloud.query.records+xml" />
    <Description />
    <AllocationModel>AllocationVApp</AllocationModel>
    <ComputeCapacity>
        <Cpu>
            <Units>MHz</Units>
            <Allocated>0</Allocated>
            <Limit>0</Limit>
            <Reserved>0</Reserved>
            <Used>36000</Used>
            <Overhead>0</Overhead>
        </Cpu>
        <Memory>
            <Units>MB</Units>
            <Allocated>0</Allocated>
            <Limit>0</Limit>
            <Reserved>0</Reserved>
            <Used>13312</Used>
            <Overhead>235</Overhead>
        </Memory>
    </ComputeCapacity>
    <ResourceEntities>
        <ResourceEntity
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vAppTemplate/vappTemplate-affdc157-9f88-4773-b566-c155721bee81"
name="Ubuntu 64-bit" type="application/vnd.vmware.vcloud.vAppTemplate+xml" />
        <ResourceEntity
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-1edf2730-d1c0-4e4d-9807-69198f3f9f75"
name="Charlie-TEST2" type="application/vnd.vmware.vcloud.vApp+xml" />
        <ResourceEntity
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-636d2e95-052e-462f-b03c-2bf8e5088383"
name="test-it" type="application/vnd.vmware.vcloud.vApp+xml" />
        <ResourceEntity
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-83dd775b-ec2c-42c6-8b1b-5d081ea7367a"
name="Charlie-TEST5" type="application/vnd.vmware.vcloud.vApp+xml" />
        <ResourceEntity
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-8d49538b-d2f5-4936-9cef-28d882ed8f22"
name="Ubuntu 64-bit" type="application/vnd.vmware.vcloud.vApp+xml" />
        <ResourceEntity
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-94a268a6-2f1b-46f0-b057-de8af0c06483"
name="guest-cust-test" type="application/vnd.vmware.vcloud.vApp+xml" />
        <ResourceEntity
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-b1be4caf-6665-481a-a189-e074a4f97db7"
name="test-2" type="application/vnd.vmware.vcloud.vApp+xml" />
        <ResourceEntity
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vApp/vapp-bac2d468-f514-42a7-8579-4f46b6d6d596"
name="Charlie-TEST3" type="application/vnd.vmware.vcloud.vApp+xml" />
    </ResourceEntities>
    <AvailableNetworks>
        <Network
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/network/9604bd58-b05c-4fa3-9f9b-4e7991376f21"
name="un-managed-external-network"
type="application/vnd.vmware.vcloud.network+xml" />
    </AvailableNetworks>
    <Capabilities>
        <SupportedHardwareVersions>
            <SupportedHardwareVersion>vmx-04</SupportedHardwareVersion>
            <SupportedHardwareVersion>vmx-07</SupportedHardwareVersion>
            <SupportedHardwareVersion>vmx-08</SupportedHardwareVersion>
            <SupportedHardwareVersion>vmx-09</SupportedHardwareVersion>
            <SupportedHardwareVersion>vmx-10</SupportedHardwareVersion>
        </SupportedHardwareVersions>
    </Capabilities>
    <NicQuota>0</NicQuota>
    <NetworkQuota>20</NetworkQuota>
    <UsedNetworkCount>3</UsedNetworkCount>
    <VmQuota>100</VmQuota>
    <IsEnabled>true</IsEnabled>
    <VdcStorageProfiles>
        <VdcStorageProfile
href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/vdcStorageProfile/65c97f16-157d-45bd-89ee-c22b0995b187"
name="Tier2" type="application/vnd.vmware.vcloud.vdcStorageProfile+xml" />
    </VdcStorageProfiles>
</Vdc>
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

    def test_querycatalogitems_by_name(self):
        tree = ET.fromstring(xml_catalog)
        self.assertEqual(
            1, len(list(find_catalogueitems(
                tree, name="centos6-stemcell"))))

    def test_queryresultrecords_by_name(self):
        tree = ET.fromstring(xml_queryresultrecords)
        self.assertEqual(
            1, len(list(find_results(
                tree, name="un-managed-external-network"))))

    def test_vapp_from_vapp(self):
        tree = ET.fromstring(xml_vapp)
        bits = list(find_xpath(".", tree, name="test_01"))
        self.assertEqual(1, len(bits))

    def test_vapptemplate_from_vdc(self):
        tree = ET.fromstring(xml_vdc)
        bits = list(find_templates(tree))
        self.assertEqual(1, len(bits))
        self.assertEqual(
            1, len(list(find_templates(
                tree, name="Ubuntu 64-bit"))))


class APITemplateTests(unittest.TestCase):

    def setUp(self):
        self.macro = PageTemplateFile(pkg_resources.resource_filename(
            "cloudhands.burst.drivers", "InstantiateVAppTemplateParams.pt"))

    def test_render(self):
        data = {
            "appliance": {
                "name": "My Test VM",
                "description": "This VM is for testing",
            },
            "network": {
                "name": "managed-external-network",
                "href": "http://cloud/api/networks/12345678"
            },
            "template": {
                "name": "Ubuntu",
                "href": "http://cloud/api/items/12345678"
            }
        }
        self.assertEqual(733, len(self.macro(**data)))
