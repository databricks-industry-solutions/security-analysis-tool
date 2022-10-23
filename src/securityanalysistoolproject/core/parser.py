'''parser module'''
import json
import re
from itertools import cycle
from core.logging_utils import LoggingUtils
LOGGR=None

if LOGGR is None:
    LOGGR = LoggingUtils.get_logger()

def set_defaults(args):
    '''set defaults if not detected in incoming json'''
    if 'url' not in args.keys():
        args.update({'url':''})
    if 'verbosity' not in args.keys():
        args.update({'verbosity':'info'})


def url_validation(url):
    '''validate url patterns'''
    # pylint: disable=anomalous-backslash-in-string
    if '/?o=' in url:
        # if the workspace_id exists, lets remove it from the URL
        url = re.sub("\/\?o=.*", '', url)
    elif 'net/' == url[-4:]:
        url = url[:-1]
    elif 'com/' == url[-4:]:
        url = url[:-1]
    return url.rstrip("/")
    # pylint: enable=anomalous-backslash-in-string



def str2bool(vinput):
    '''convert string to bool'''
    return vinput.lower() in ("yes", "true", "t", "1")

#dummy values. Not real values
# {'account_id': 'dadbb045-e629-4e8c-b408-dc6b3ac3d4eb', 'export_db': 'logs', 'verify_ssl': 'False', 'verbosity': 'info',
# 'email_alerts': '', 'master_name_scope': 'sat_master_scope', 'master_name_key': 'user', 'master_pwd_scope': 'sat_master_scope',
# 'master_pwd_key': 'pass', 'workspace_pat_scope': 'sat_master_scope', 'workspace_pat_token_prefix': 'sat_token', '
# url': 'https://canada.cloud.databricks.com', 'workspace_id': 'accounts', 'cloud_type': 'aws', 'clusterid': '1315-184342-atswg8ll',
# 'token':'dapix', 'mastername':'dummymaster', 'masterpwd':'dummypwd', 'use_mastercreds':'False'}

def parse_input_jsonargs(inp_configs):
    '''parse and validate incoming json string and return json'''
    if isinstance(inp_configs, str):
        inp_configs =json.loads(inp_configs)
    set_defaults(inp_configs)
    url = url_validation(inp_configs['url'])
    inp_configs.update({'url':url})
    ## validate values are present
    if inp_configs['account_id'] == '':
        raise ValueError('Account ID cannot be empty')
    if inp_configs['clusterid'] == '':
        raise ValueError('Cluster ID cannot be empty')
    if inp_configs['mastername'] == '':
        raise ValueError('Master name cannot be empty')
    if inp_configs['masterpwd'] == '':
        raise ValueError('Master pwd cannot be empty')
    if (inp_configs['token'] == '') and (inp_configs['use_mastercreds'] is False):
        raise ValueError('Pass valid Token')
    return inp_configs


def simple_sat_fn(message:str, key:str) -> str:
    """
    Encrypt
    :param message:
        plaintext or cipher text.
    :param cipher_key:
        key chosen by create_key function.
    :return:
        return a string either cipher text or plain text.
    """
    return "".join(chr(ord(x) ^ ord(y)) for x, y in zip(message, cycle(key)))


def get_decrypted_json_key(obscured: str, key:str, workspace_id:str) -> str:
    '''get decrypted json'''
    inp_configs = simple_sat_fn(obscured, workspace_id)
    jsonobj = json.loads(inp_configs)
    return jsonobj[key]
