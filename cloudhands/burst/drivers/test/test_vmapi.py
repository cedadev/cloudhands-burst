#!/usr/bin/env python
# encoding: UTF-8

import functools
import unittest
import xml.etree.ElementTree as ET

from chameleon import PageTemplateFile
import pkg_resources

from cloudhands.burst.appliance import find_catalogueitems
from cloudhands.burst.appliance import find_customizationscript
from cloudhands.burst.appliance import find_orgs
from cloudhands.burst.appliance import find_results
from cloudhands.burst.appliance import find_templates
from cloudhands.burst.utils import find_xpath
from cloudhands.burst.utils import unescape_script

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

text_customizationscript = """
#!/bin/sh&#13;if [ x$1 ==
x&quot;precustomization&quot; ]; then&#13;mkdir /root/.ssh/&#13;echo
&quot;ssh-rsa
AAAAB3NzaC1yc2EAAAABIwAAAQEAzDpup+XwRKfAq5PtDYrsefyOFqWeAra3rONBzfdKub0Aa2imNjNFk+Q1Eeoqfn92A9bTx024EzoCg7daIswbi+ynXtzda+DT1RnpKcuOyOt3Jy8413ZOd+Ks3AovBzCQPpALiNwPu5zieCvBrd9lD4BNZo4tG6ELIv9Qv+APXPheGdDIMzwkhOf/8och4YkFGcVeYhTCjOdO3sFF8WkFmdW/OJP87RH9FBHLWMirdTz4x2tT+Cyfe47NUYCmxRkdulexy71OSIZopZONYvwx3jmradjt2Hq4JubO6wbaiUbF+bvyMJapRIPE7+f37tTSDs8W19djRf7DEz7MANprbw==
cl@eduserv.org.uk&quot; &gt;&gt;
/root/.ssh/authorized_keys&#13;/root/pre_customisation.sh&#13;elif [ x$1 ==
x&quot;postcustomization&quot; ];
then&#13;/root/post_customisation.sh&#13;fi
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

    def test_customization_script_unescape(self):
        self.assertEqual(
            8, len(unescape_script(text_customizationscript).splitlines()))

    def test_customization_script_from_vapp(self):
        data = pkg_resources.resource_string(
            "cloudhands.burst.drivers.test", "vapp-test_02.xml")
        tree = ET.fromstring(data)
        elems = list(find_customizationscript(tree))
        self.assertEqual(1, len(elems))
        self.assertEqual(150, len(elems[0].text))

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
