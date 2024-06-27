import utils
import json
import requests

def setup(elasticUser, elasticPassword, grafanaToken, grafanaFolder):

    with open('setupfile.json') as file:
        data = json.load(file)
        elasticUser = data['elasticUser']
        elasticPassword = data['elasticPassword']
        grafanaToken = data['grafanaToken']
        grafanaFolder = data['grafanaFolder']

    headers = {'Authorization': 'Bearer ' + grafanaToken}
    response = requests.get('http://localhost:3000/api/folders', headers=headers)
    data = response.json()
    for folder in data:
        if folder['title'] == grafanaFolder:
            folder_id = folder['id']
            folder_uid = folder['uid']
    if not folder_id:
        response = requests.post('http://localhost:3000/api/folders', headers=headers, json={"title": grafanaFolder})
        if response.status_code == 200:
            data = response.json()
            folder_id = data['id']
            folder_uid = data['uid']
        else:
            return -1

    with open('grafanaTemplates/baseDashboard.json') as file:
        dashboard = json.load(file)

    headers = {'Authorization': 'Bearer '+grafanaToken}
    body = {'dashboard': dashboard,
            'folderUid': folder_uid,
            'message': 'Dashboard created',
            'overwrite': False}

    response = requests.post('http://localhost:3000/api/dashboards/db', headers=headers, json=body)
    data = response.json()
    dashboard_uid = data.get('uid')
    if not dashboard_uid:
        return -2

    body = {
        'settings': {
            'number_of_shards': 1
        },
        'mappings': {
            'properties': {
                '@timestamp': {'type': 'date'}
            }
        }
    }
    response = requests.put('https://localhost:9200/ipsla_stats', auth=(elasticUser, elasticPassword), verify='/etc/elasticsearch/certs/http_ca.crt', json=body)
    data = response.json()
    if not data.get('acknowledged'):
        requests.delete('http://localhost:3000/api/dashboards/uid/'+dashboard_uid, headers=headers)
        return -3

    with open('/etc/elasticsearch/certs/http_ca.crt') as file:
        cert = file.read()
    secJson = {'basicAuthPassword': elasticPassword, 'tlsCACert': cert}
    body = {
        'name': 'IPSLA_DS',
        'type': 'elasticsearch',
        'url': 'https://localhost:9200',
        'secureJsonData': secJson,
        'basicAuth': True,
        'jsonData': {'tlsAuthWithCACert': True},
        'database': 'ipsla_stats',
        'access': 'proxy',
        'basicAuthUser': elasticUser,
        }

    response = requests.post('http://localhost:3000/api/datasources', headers=headers, json=body)
    data = response.json()
    if data.get('message') != 'Datasource added':
        requests.delete('http://localhost:3000/api/dashboards/uid/'+dashboard_uid, headers=headers)
        requests.delete('https://localhost:9200/ipsla_stats', auth=(elasticUser, elasticPassword), verify='/etc/elasticsearch/certs/http_ca.crt')
        return -4

    config = {'dashboard_uid': dashboard_uid,
                'datasource_uid': data['datasource']['uid'],
                'folder_id': folder_id,
                'next_row_id': 3000,
                'download_files': [],
                'general': {'udpJitter_op': 0, 'httpThroughput_op': 0}}

    js = json.dumps(config, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)




print(setup())

