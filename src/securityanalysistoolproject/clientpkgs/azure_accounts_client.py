'''Helper functions for Azure accounts client module'''
import re
import datetime
import time

def getItem(parentitem, listofnames, noneType=False):
    """
    Traverses a hierarchical dict to get a value
    :param dict parentitem: dictionary object from which to get value
    :param list listofnames: all the parameter names to traverse to get value in sequence.
    :return: the value of the child key
    :rtype: str
    """
    localitem = parentitem
    for l in listofnames:
        localitem = localitem.get(l)
        if localitem is None:
            if noneType:
                return None
            else:
                return ''
    if localitem == parentitem:
        if noneType:
            return None
        else:
            return ''
    return localitem


def str2time(strtime):
    try:
        format_data = "%Y-%m-%dT%H:%M:%S.%fZ"
        strtime=strtime[:26] 
        if strtime[-1] != 'Z':
            strtime = strtime + 'Z'
        t = time.mktime(datetime.datetime.strptime(strtime, format_data).timetuple())
        return t    
    except Exception as e:
        print(strtime)
        raise(e)

def remap_workspace_list(subslist):
    subslistMapped = []
    for rec in subslist:
        if getItem(rec, ['type']) != 'Microsoft.Databricks/workspaces' \
                or getItem(rec, ['properties', 'workspaceId'], True) is None:
            continue
        
        rec['account_id']=''
        rec['aws_region']=getItem(rec, ['location'])
        rec['region']=getItem(rec, ['location'])
        rec['creation_time']=str2time(getItem(rec, ['properties', 'createdDateTime']))
        #regex = "([\S]+).azuredatabricks.+"
        regex = "(?:(\\S*).azuredatabricks.(\\S*))+"
        dn=re.findall(regex, getItem(rec, ['properties', 'workspaceUrl']))
        if dn is None or dn is False:
            rec['deployment_name']=''
        else:
            rec['deployment_name']=dn[0]
        rec['pricing_tier']=getItem(rec, ['sku', 'name'])           
        rec['workspace_id']=getItem(rec, ['properties', 'workspaceId'])
        rec['workspace_name']=getItem(rec, ['name'])
        ps = getItem(rec, ['properties', 'provisioningState'])
        if ps=='Succeeded':
            rec['workspace_status']='RUNNING'
        else:
            rec['workspace_status']=ps
        pvtlinklist = getItem(rec, ['properties', 'privateEndpointConnections'])
        if  pvtlinklist is None:
            rec['private_access_settings_id']=None
        else:
            for pvtlinkitem in pvtlinklist:
                rec['private_access_settings_id'] = getItem(pvtlinkitem, ['id'])  #only the first one for id purposes
                break          
        rec['workspace_url']=getItem(rec, ['properties', 'workspaceUrl'])
        rec['network_id']=getItem(rec, ['properties', 'parameters', 'customVirtualNetworkId', 'value'])
        rec['network_id_pvtsubnet']=getItem(rec, ['properties', 'parameters', 'customPrivateSubnetName', 'value'])
        rec['network_id_pvtsubnet']=getItem(rec, ['properties', 'parameters', 'customPublicSubnetName', 'value'])
        rec['enableFedRampCertification'] = getItem(rec, ['properties', 'parameters', 'enableFedRampCertification', 'value'])
        rec['enableNoPublicIp'] = getItem(rec, ['properties', 'parameters', 'enableNoPublicIp', 'value'])
        rec['prepareEncryption'] = getItem(rec, ['properties', 'parameters', 'prepareEncryption', 'value'])
        rec['relayNamespaceName'] = getItem(rec, ['properties', 'parameters', 'relayNamespaceName', 'value'])
        rec['requireInfrastructureEncryption'] = getItem(rec, ['properties', 'parameters', 'requireInfrastructureEncryption', 'value'])      
        subslistMapped.append(rec)
    return subslistMapped


def remap_pvtlink_list(subslist):
    pvtlistMapped = []
    for rec in subslist:
        if getItem(rec, ['type']) != 'Microsoft.Databricks/workspaces' \
                or getItem(rec, ['properties', 'workspaceId'], True) is None:
            continue
        pvtlinklist = getItem(rec, ['properties', 'privateEndpointConnections'])
        if  pvtlinklist is None:
            pvtlink={}
            pvtlink['private_access_settings_id']=None
            pvtlistMapped.append(pvtlink)
            continue
        for pvtlinkitem in pvtlinklist:
            pvtlink = {}
            pvtlink['private_access_settings_id'] = getItem(pvtlinkitem, ['id'])
            pvtlink['account_id']=getItem(rec, ['properties', 'workspaceId'])
            pvtlink['private_access_level']='WORKSPACE'
            pvtlink['private_access_settings_name'] = getItem(pvtlinkitem, ['name'])
            pn = getItem(rec, ['properties', 'publicNetworkAccess'])
            if pn != 'Enabled':
                pn = False
            else:
                pn = True

            pvtlink['public_access_enabled']=pn
            pvtlink['region']=getItem(rec, ['location'])
            pvtlistMapped.append(pvtlink)
    return pvtlistMapped

def remap_storage_list(subslist):
    netlistMapped = []
    for rec in subslist:
        if getItem(rec, ['type']) != 'Microsoft.Databricks/workspaces' \
                or getItem(rec, ['properties', 'workspaceId'], True) is None:
            continue
        stglink = {}
        stglink['account_id']=getItem(rec, ['properties', 'workspaceId'])
        stglink['creation_time']=str2time(getItem(rec, ['properties', 'createdDateTime']))
        stglink['root_bucket_info']={"bucket_name": getItem(rec, ['properties','parameters', 'storageAccountName', 'value'])}
        stglink['storage_configuration_id']=getItem(rec, ['properties','parameters', 'storageAccountName', 'value'])
        stglink['storage_configuration_name']=getItem(rec, ['properties','parameters', 'storageAccountName', 'value'])
        netlistMapped.append(stglink)
    return netlistMapped



def remap_cmk_list(subslist):
    cmklistMapped = []
    for rec in subslist:
        if getItem(rec, ['type']) != 'Microsoft.Databricks/workspaces' \
                or getItem(rec, ['properties', 'workspaceId'], True) is None \
                or getItem(rec, ['properties','parameters', 'encryption'], True) is None:
            continue
        cmklink = {}
        cmklink['account_id']=getItem(rec, ['properties', 'workspaceId'])
        cmklink['workspace_id']=getItem(rec, ['properties', 'workspaceId'])        
        cmklink['creation_time']=str2time(getItem(rec, ['properties', 'createdDateTime']))
        cmklink['customer_managed_key_id']=getItem(rec, ['properties','parameters', 'encryption', 'value', "keyvaulturi"])
        cmklink['use_cases']=['STORAGE']
        keyalias = getItem(rec, ['properties','parameters', 'encryption', 'value', "KeyName"])
        keyarn = getItem(rec, ['properties','parameters', 'encryption', 'value', "keySource"])
        cmklink['aws_key_info']={"key_alias": keyalias, "key_arn": keyarn}
        cmklistMapped.append(cmklink)
    return {'satelements':cmklistMapped}

   

#Test code not used.
# pip install msal
import msal
import sys
def get_msal_token():
    """
    validate client id and secret from microsoft and google
    """

    client_id = ''
    tenant_id = ''
    client_secret = ''    
    try:
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )

        # call for default scope in order to verify client id and secret.
        scopes = [ 'https://management.azure.com/.default' ]
        # The pattern to acquire a token looks like this.
        token = None

        # Firstly, looks up a token from cache
        # Since we are looking for token for the current app, NOT for an end user,
        # notice we give account parameter as None.
        token = app.acquire_token_silent(scopes=scopes, account=None)

        if not token:
            token = app.acquire_token_for_client(scopes=scopes)
        
        print(token)
        if token.get("access_token") is None:
            print(['no token'])
        else:
            print(token.get("access_token"))


    except Exception as error:
        print(f"Exception {error}")
        print(str(error))





