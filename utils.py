from easysnmp import Session
import paramiko
import json
import time
from grafana_api.grafana_face import GrafanaFace
import requests
import shutil
import os
import bisect


with open('conf.json') as file:
        data = json.load(file)

dashboard_uid = data['dashboard_uid']
datasource_uid = data['datasource_uid']

grafanaToken = ''


def create_UDPJitter_op(host, receiver):

    id = get_next_op(host)
    operation = build_udpJitter_op(id, receiver)

    if not run_command(host, operation):
        return False

    with open('conf.json') as file:
        data = json.load(file)

    data[host]['udpJitter_op'].append(str(id))

    js = json.dumps(data, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)

    return id


def create_HTTPThroughput_op(host, url):

    id = get_next_op(host)
    operation = build_httpThroughput_op(id, url)
    run_command(host, operation)

    with open('conf.json') as file:
        data = json.load(file)

    if data[host]['httpThroughput_op']:
        return -1

    data[host]['httpThroughput_op'] = str(id)

    js = json.dumps(data, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)

    return id


def test_bandwidth(host):

    id = get_next_op(host)
    url = 'http://10.0.0.103:5000/get_file/initialTest'
    base_url = 'http://10.0.0.103:5000/get_file/'

    operation = build_httpThroughput_op(id, url)
    run_command(host, operation)

    time.sleep(1)
    body = '0'
    download_time = '0'
    while body == '0' or download_time == '0':

        session = Session(hostname=host, community='public', version=2, timeout=10)
        snmp = session.walk('.1.3.6.1.4.1.9.9.42.1.5.1')
        
        for item in snmp:

            oid_parts = str(item.oid).split(".")
            entry = oid_parts[-1]
            rtt_info_type = oid_parts[-2]
            value=item.value

            if entry == str(id):

                if rtt_info_type == '4':
                    download_time = value
                elif rtt_info_type == '5':
                    body = value

    delete_op(host, id)

    min_size = int(((float(body)*8)/(float(download_time)/1000)) * 2)

    with open('conf.json') as file:
        data = json.load(file)
    data['download_files']

    index = next((idx for idx, size in enumerate(data['download_files']) if size > min_size), -1)
    if index == -1 or data['download_files'][index]/2 > min_size:
        new_size = 1024
        while new_size < min_size:
            new_size *= 2
        os.system('head -c '+ str(int(new_size/8)) +' </dev/urandom > downloadFiles/'+str(new_size))
        bisect.insort(data['download_files'],new_size)
        file_size = new_size
        js = json.dumps(data, indent=4)
        with open('conf.json', 'w') as file:
            file.write(js)

        return base_url+str(file_size)
        
    else:

        return base_url+str(data['download_files'][index])


def build_udpJitter_op(id, receiver):

    return ['ip sla '+str(id),
            'udp-jitter '+receiver+' 5000 codec g711alaw advantage-factor 10',
            'frequency 30',
            'ip sla schedule '+str(id)+' life forever start-time now',
            'end']


def build_httpThroughput_op(id, url):

    return ['ip sla '+str(id),
            'http get '+url,
            'frequency 60',
            'ip sla schedule '+str(id)+' life forever start-time now',
            'end']


def run_command(host, commands):

    with open('conf.json') as file:
        data = json.load(file)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, username=data[host]['user'], password=data[host]['password'], timeout = 3)
    except:
        return False

    try:
        shell = ssh.invoke_shell()
    except:
        return False
    
    shell.send('conf t\n')

    for comm in commands:
        shell.send(comm + '\n')
        time.sleep(.1)

    return True


def get_next_op(host):

    session = Session(hostname=host, community='public', version=2, timeout=10)
    table = session.walk('1.3.6.1.4.1.9.9.42.1.2.1.1')

    operations=[]
    for elem in table:
        parts = str(elem.oid).split(".")
        if parts[-2] == '4':
            operations.append(parts[-1])

    if operations:
        return max([eval(i) for i in operations])+1
    else:
        return 1


def create_logstash_conf(host, t):

    with open('conf.json') as file:
        data = json.load(file)

    if t=="0":
        snmp_oid = '1.3.6.1.4.1.9.9.42.1.5.2.1'
        operations = list_toString(data[host]['udpJitter_op'])
        script = 'udpJitter.rb'
    elif t=="1":
        snmp_oid = '1.3.6.1.4.1.9.9.42.1.5.1'
        operations = '"'+data[host]['httpThroughput_op']+'"'
        script = 'httpThroughput.rb'

    fileName = host+'_'+t

    with open('logstashTemplates/logstashConfig.conf', 'r') as file :
        data = file.read()
    
    data = data.replace('<router>', host)
    data = data.replace('<snmp_oid>', snmp_oid)
    data = data.replace('<operations>', operations)
    data = data.replace('<script>', script)
    
    with open('/etc/logstash/conf.d/'+fileName+'.conf', 'w') as file:
        file.write(data)

    src = 'logstashTemplates/'+script
    dest = '/etc/logstash/conf.d/scripts/'
    shutil.copy(src, dest)

    with open('/etc/logstash/pipelines.yml', 'r') as file:
        lines = file.readlines()

    if '- pipeline.id: '+fileName+'\n' not in lines:
        with open('/etc/logstash/pipelines.yml', 'a') as file:
            file.write('\n\n- pipeline.id: '+fileName+'\n  path.config: "/etc/logstash/conf.d/'+fileName+'.conf"')


def list_toString(l):
    res = "["
    for elem in l:
        res+=('"'+elem+'", ')
    res = res[:-2]
    return res+']'


def test_ssh(ip, user, passwd):

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=user, password=passwd, timeout = 3)
    except TimeoutError:
        return False

    return True


def add_router(ip, user, passwd):
    
    with open('conf.json') as file:
        data = json.load(file)

    if data.get(ip):
        return False
    else:
        data[ip] = {'user': user, 'password': passwd, 'udpJitter_op':[], 'httpThroughput_op': []}
    
    js = json.dumps(data, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)

    return True


def delete_database(ip):

    with open('conf.json') as file:
        data = json.load(file)

    grafana_delete_datasource(ip+'_0')
    grafana_delete_datasource(ip+'_1')

    response = requests.delete('https://localhost:9200/'+ip+'_0', auth=('elastic','MkbzQ7=--NsplUIi-yFc'), verify='/etc/elasticsearch/certs/http_ca.crt')
    data = response.json()
    if data.get('error'):
        return -1
    response = requests.delete('https://localhost:9200/'+ip+'_1', auth=('elastic','MkbzQ7=--NsplUIi-yFc'), verify='/etc/elasticsearch/certs/http_ca.crt')
    data = response.json()
    if data.get('error'):
        return -1


def get_next_position():

    db = grafana_get_dashboard(dashboard_uid)

    pos = 0
    for panel in db['panels']:
        if panel['id'] >= 2000 and panel['id'] < 3000:
            new_pos = panel['gridPos']['y'] + panel['gridPos']['h']+1
        
    return new_pos
   

def add_row(ip):

    db = grafana_get_dashboard(dashboard_uid)

    with open('conf.json') as file:
        data = json.load(file)

    id = data['next_row_id']

    gridPos = {"h": 1,"w": 24,"x": 0,"y": get_next_position()}
    
    row = {'collapsed': True, 'gridPos': gridPos, 'id': id, 'panels': [], 'title': ip, 'type': 'row'}

    db['panels'].append(row)

    grafana_update_dashboard(db)

    data[ip]['row_id'] = id
    data['next_row_id'] += 1000

    js = json.dumps(data, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)

    return True


def UDPJitter_add_panels(ip, op_id):

    row_id = get_row_id(ip)
    db = grafana_get_dashboard(dashboard_uid)

    with open('conf.json') as file:
        data = json.load(file)

    index = 0
    for idx,elem in enumerate(db['panels']):
        if elem['id'] == row_id:
            index = idx

    ypos = db['panels'][index]['gridPos']['y']

    panels = [new_panel(row_id+1, datasource_uid, 'Packet Loss SD', 'Lost Packets (%)', ip+'_PacketLossSD_'+str(op_id), op_id, ypos),
                new_panel(row_id+2, datasource_uid, 'Packet Loss DS', 'Lost Packets (%)', ip+'_PacketLossDS_'+str(op_id), op_id, ypos),
                new_panel(row_id+3, datasource_uid, 'MOS', 'Score', ip+'_MOS_'+str(op_id), op_id, ypos),
                new_panel(row_id+4, datasource_uid, 'ICMPF', 'Score', ip+'_ICMPF_'+str(op_id), op_id, ypos)]

    if db['panels'][index]['collapsed']:
        db['panels'][index]['panels'].extend(panels)
    else:
        db['panels'].extend(panels)

    js = json.dumps(data, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)

    index = 0
    for idx,elem in enumerate(db['panels']):
        if elem['id'] == 2000:
            index = idx

    ypos = db['panels'][index]['gridPos']['y']

    panels = [new_panel(2001, datasource_uid, 'Packet Loss SD', 'Lost Packets (%)', ip+'_PacketLossSD', ip, ypos),
                new_panel(2002, datasource_uid, 'Packet Loss DS', 'Lost Packets (%)', ip+'_PacketLossDS', ip, ypos),
                new_panel(2003, datasource_uid, 'MOS', 'Score', ip+'_MOS', ip, ypos),
                new_panel(2004, datasource_uid, 'ICMPF', 'Score', ip+'_ICMPF', ip, ypos)]

    if data['general']['udpJitter_op'] == 0:
        if db['panels'][index]['collapsed']:
            db['panels'][index]['panels'].extend(panels)
        else:
            db['panels'].extend(panels)

    else:
        if db['panels'][index]['collapsed']:
            
            for idx,elem in enumerate(db['panels'][index]['panels']):
                if elem['id'] == 2001:
                    field = {'field': ip+'_PacketLossSD', 'id': ip, 'type': 'avg'}
                    db['panels'][index]['panels'][idx]['targets'][0]['metrics'].append(field)
                elif elem['id'] == 2002:
                    field = {'field': ip+'_PacketLossDS', 'id': ip, 'type': 'avg'}
                    db['panels'][index]['panels'][idx]['targets'][0]['metrics'].append(field)
                elif elem['id'] == 2003:
                    field = {'field': ip+'_MOS', 'id': ip, 'type': 'avg'}
                    db['panels'][index]['panels'][idx]['targets'][0]['metrics'].append(field)
                elif elem['id'] == 2004:
                    field = {'field': ip+'_ICMPF', 'id': ip, 'type': 'avg'}
                    db['panels'][index]['panels'][idx]['targets'][0]['metrics'].append(field)

        else:

            for idx,elem in enumerate(db['panels']):
                if elem['id'] == 2001:
                    field = {'field': ip+'_PacketLossSD', 'id': ip, 'type': 'avg'}
                    db['panels'][idx]['targets'][0]['metrics'].append(field)
                elif elem['id'] == 2002:
                    field = {'field': ip+'_PacketLossDS', 'id': ip, 'type': 'avg'}
                    db['panels'][idx]['targets'][0]['metrics'].append(field)
                elif elem['id'] == 2003:
                    field = {'field': ip+'_MOS', 'id': ip, 'type': 'avg'}
                    db['panels'][idx]['targets'][0]['metrics'].append(field)
                elif elem['id'] == 2004:
                    field = {'field': ip+'_ICMPF', 'id': ip, 'type': 'avg'}
                    db['panels'][idx]['targets'][0]['metrics'].append(field)


    data['general']['udpJitter_op'] += 1
    js = json.dumps(data, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)
    grafana_update_dashboard(db)


def UDPJitter_add_metrics(ip, op_id):

    row_id = get_row_id(ip)
    db = grafana_get_dashboard(dashboard_uid)

    for idx,elem in enumerate(db['panels']):
        if elem['id'] == row_id:
            row_index = idx

    if db['panels'][row_index]['collapsed']:

        for idx,elem in enumerate(db['panels'][row_index]['panels']):
            if elem['id'] == row_id+1:
                field = {'field': 'PacketLossSD_'+str(op_id), 'id': str(op_id), 'type': 'avg'}
                db['panels'][row_index]['panels'][idx]['targets'][0]['metrics'].append(field)
            elif elem['id'] == row_id+2:
                field = {'field': 'PacketLossDS_'+str(op_id), 'id': str(op_id), 'type': 'avg'}
                db['panels'][row_index]['panels'][idx]['targets'][0]['metrics'].append(field)
            elif elem['id'] == row_id+3:
                field = {'field': 'MOS_'+str(op_id), 'id': str(op_id), 'type': 'avg'}
                db['panels'][row_index]['panels'][idx]['targets'][0]['metrics'].append(field)
            elif elem['id'] == row_id+4:
                field = {'field': 'ICMPF_'+str(op_id), 'id': str(op_id), 'type': 'avg'}
                db['panels'][row_index]['panels'][idx]['targets'][0]['metrics'].append(field)

    else:

        for idx,elem in enumerate(db['panels']):
            if elem['id'] == row_id+1:
                field = {'field': 'PacketLossSD_'+str(op_id), 'id': str(op_id), 'type': 'avg'}
                db['panels'][idx]['targets'][0]['metrics'].append(field)
            elif elem['id'] == row_id+2:
                field = {'field': 'PacketLossDS_'+str(op_id), 'id': str(op_id), 'type': 'avg'}
                db['panels'][idx]['targets'][0]['metrics'].append(field)
            elif elem['id'] == row_id+3:
                field = {'field': 'MOS_'+str(op_id), 'id': str(op_id), 'type': 'avg'}
                db['panels'][idx]['targets'][0]['metrics'].append(field)
            elif elem['id'] == row_id+4:
                field = {'field': 'ICMPF_'+str(op_id), 'id': str(op_id), 'type': 'avg'}
                db['panels'][idx]['targets'][0]['metrics'].append(field)

    grafana_update_dashboard(db)


def HTTPThroughput_add_panel(ip, op_id):

    row_id = get_row_id(ip)
    db = grafana_get_dashboard(dashboard_uid)

    with open('conf.json') as file:
        data = json.load(file)

    for idx,elem in enumerate(db['panels']):
        if elem['id'] == row_id:
            index = idx

    ypos = db['panels'][index]['gridPos']['y']

    if db['panels'][index]['collapsed']:
        db['panels'][index]['panels'].append(
            new_panel(row_id+5, datasource_uid, 'Throughput', 'bits/s', ip+'_Throughput', op_id, ypos))
    
    else:
        db['panels'].append(
            new_panel(row_id+5, datasource_uid, 'Throughput', 'bits/s', ip+'_Throughput', op_id, ypos))

    index = 0
    for idx,elem in enumerate(db['panels']):
        if elem['id'] == 2000:
            index = idx

    ypos = db['panels'][index]['gridPos']['y']

    if data['general']['httpThroughput_op'] == 0:

        if db['panels'][index]['collapsed']:
            db['panels'][index]['panels'].append(
                new_panel(2005, datasource_uid, 'Throughput', 'bits/s', ip+'_Throughput', ip, ypos))
        
        else:
            db['panels'].append(
                new_panel(2005, datasource_uid, 'Throughput', 'bits/s', ip+'_Throughput', ip, ypos))

    else:

        if db['panels'][index]['collapsed']:

            for idx,elem in enumerate(db['panels'][index]['panels']):
                if elem['id'] == 2005:
                    field = {'field': ip+'_Throughput', 'id': ip, 'type': 'avg'}
                    db['panels'][index]['panels'][idx]['targets'][0]['metrics'].append(field)

        else:

            for idx,elem in enumerate(db['panels']):
                if elem['id'] == 2005:
                    field = {'field': ip+'_Throughput', 'id': ip, 'type': 'avg'}
                    db['panels'][idx]['targets'][0]['metrics'].append(field)


    data['general']['httpThroughput_op'] +=1
    js = json.dumps(data, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)
    grafana_update_dashboard(db)


def new_panel(id, datasource_uid, title, axis_label, field_name, field_id, ypos):

    with open('grafanaTemplates/panel.json') as file:
        panel = json.load(file)

    field = {'field': field_name, 'id': field_id, 'type': 'avg'}

    panel['id'] = id
    panel['title'] = title
    panel['fieldConfig']['defaults']['custom']['axisLabel'] = axis_label
    panel['gridPos']['y'] = ypos+1
    panel['datasource'] = {'type': 'elasticsearch', 'uid': datasource_uid}
    panel['targets'][0]['datasource'] = {'type': 'elasticsearch', 'uid': datasource_uid}
    panel['targets'][0]['metrics'].append(field)

    return panel


def get_row_id(ip):

    with open('conf.json') as file:
        data = json.load(file)
    return data[ip]['row_id']



def grafana_get_dashboard(uid):

    headers = {'Authorization': 'Bearer '+grafanaToken}
    response = requests.get('http://localhost:3000/api/dashboards/uid/'+uid, headers=headers)
    data = response.json()
    return data['dashboard']


def grafana_update_dashboard(db):
    """
    headers = {'Authorization': 'Bearer '+grafanaToken}
    body = {
        'dashboard': db,
        'title': 'Update',
        'uid': dashboard_uid
    }

    for idx,elem in enumerate(db['panels']):
        if elem['id'] == 14000:
            index = idx

    print(db['panels'][index]['panels'])

    response = requests.post('http://localhost:3000/api/dashboards/db', headers=headers, json=body)
    data = response.json()
    if data.get('status') == 'success':
        return True
    else:
        return False
    """

    with open('conf.json') as file:
        data = json.load(file)
    
    grafana_api = GrafanaFace(auth=grafanaToken, host='localhost:3000')
    grafana_api.dashboard.update_dashboard(dashboard={'dashboard': db, 'folderId': data['folder_id'], 'overwrite': True})
    

def delete_router(ip):

    operations = []

    with open('conf.json') as file:
        data = json.load(file)
    
    db = grafana_get_dashboard(dashboard_uid)

    if data[ip]['udpJitter_op']:
        db, data = general_delete_udpJitter_op(ip, db, data)

    if data[ip]['httpThroughput_op']:
        db, data = general_delete_httpThroughput_op(ip, db, data)

    grafana_update_dashboard(db)

    operations.extend(data[ip]['udpJitter_op'])
    operations.extend(data[ip]['httpThroughput_op'])
    row_id = data[ip]['row_id']

    for op in operations:
        delete_op(ip, op)

    delete_row(row_id)
    data.pop(ip)
    js = json.dumps(data, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)


def delete_row(row_id):

    db = grafana_get_dashboard(dashboard_uid)

    for idx,elem in enumerate(db['panels']):
        if elem['id'] == row_id:
            row_index = idx

    if db['panels'][row_index]['collapsed']:

        db['panels'].pop(row_index)

    else:

        elim = []
        for idx,elem in reversed(list(enumerate(db['panels']))):

            if elem['id'] >= row_id and elem['id'] <= row_id+999:

                db['panels'].pop(idx)

    grafana_update_dashboard(db)


def delete_operation(ip, op):

    db = grafana_get_dashboard(dashboard_uid)
    elim = []

    with open('conf.json') as file:
        data = json.load(file)

    if op not in data[ip]['udpJitter_op'] and op not in data[ip]['httpThroughput_op']:
        return -1

    row_id = data[ip]['row_id']

    for idx,elem in enumerate(db['panels']):
        if elem['id'] == row_id:
            row_index = idx

    if db['panels'][row_index]['collapsed']:

        if op in data[ip]['udpJitter_op']:
            data[ip]['udpJitter_op'].remove(op)
            if not data[ip]['udpJitter_op']:
                db, data = general_delete_udpJitter_op(ip, db, data)
            for idx,elem in reversed(list(enumerate(db['panels'][row_index]['panels']))):
                if elem['id'] > row_id and elem['id'] <= row_id+4:

                    if not data[ip]['udpJitter_op']:
                        db['panels'][row_index]['panels'].pop(idx)
                    else:
                        for m_idx,metric in enumerate(elem['targets'][0]['metrics']):
                            if str(metric['id']) == op:
                                db['panels'][row_index]['panels'][idx]['targets'][0]['metrics'].pop(m_idx)
            
        elif op in data[ip]['httpThroughput_op']:
            data[ip]['httpThroughput_op'] = ""
            for idx,elem in enumerate(db['panels'][row_index]['panels']):
                if elem['id'] == row_id+5:
                    db['panels'][row_index]['panels'].pop(idx)

            db, data = general_delete_httpThroughput_op(ip, db, data)
    
    else:

        if op in data[ip]['udpJitter_op']:
            data[ip]['udpJitter_op'].remove(op)
            if not data[ip]['udpJitter_op']:
                db, data = general_delete_udpJitter_op(ip, db, data)
            for idx,elem in reversed(list(enumerate(db['panels']))):
                if elem['id'] > row_id and elem['id'] <= row_id+4:

                    if not data[ip]['udpJitter_op']:
                        db['panels'].pop(idx)
                    else:
                        for m_idx,metric in enumerate(elem['targets'][0]['metrics']):
                            if str(metric['id']) == op:
                                db['panels'][idx]['targets'][0]['metrics'].pop(m_idx)
        
        elif op in data[ip]['httpThroughput_op']:

            data[ip]['httpThroughput_op'] = ""
            for idx,elem in enumerate(db['panels']):
                if elem['id'] == row_id+5:
                    db['panels'].pop(idx)
            
            db, data = general_delete_httpThroughput_op(ip, db, data)

    js = json.dumps(data, indent=4)
    with open('conf.json', 'w') as file:
        file.write(js)

    delete_op(ip, op)
    grafana_update_dashboard(db)


def general_delete_udpJitter_op(ip, db, data):

    data['general']['udpJitter_op'] -= 1
    for idx,elem in enumerate(db['panels']):
        if elem['id'] == 2000:
            general_row_index = idx

    if db['panels'][general_row_index]['collapsed']:
        for idx,elem in reversed(list(enumerate(db['panels'][general_row_index]['panels']))):
            if elem['id'] > 2000 and elem['id'] <= 2004:
                if data['general']['udpJitter_op'] == 0:
                    db['panels'][general_row_index]['panels'].pop(idx)
                else:
                    for m_idx,metric in reversed(list(enumerate(elem['targets'][0]['metrics']))):
                        if str(metric['id']) == ip:
                            db['panels'][general_row_index]['panels'][idx]['targets'][0]['metrics'].pop(m_idx)
    else:
        for idx,elem in reversed(list(enumerate(db['panels']))):
            if elem['id'] > 2000 and elem['id'] <= 2004:
                if data['general']['udpJitter_op'] == 0:
                    db['panels'].pop(idx)
                else:
                    for m_idx,metric in reversed(list(enumerate(elem['targets'][0]['metrics']))):
                        if str(metric['id']) == ip:
                            db['panels'][idx]['targets'][0]['metrics'].pop(m_idx)

    with open('/etc/logstash/pipelines.yml', 'r') as file:
        lines = file.readlines()

    index = lines.index('- pipeline.id: '+ip+'_0\n')
    lines.pop(index+1)
    lines.pop(index)

    with open('/etc/logstash/pipelines.yml', 'w') as file:
        file.writelines(lines)
    
    return (db, data)


def general_delete_httpThroughput_op(ip, db, data):

    data['general']['httpThroughput_op'] -= 1
    for idx,elem in enumerate(db['panels']):
        if elem['id'] == 2000:
            general_row_index = idx

    if db['panels'][general_row_index]['collapsed']:
        for idx,elem in enumerate(db['panels'][general_row_index]['panels']):
            if elem['id'] == 2005:
                if data['general']['httpThroughput_op'] == 0:
                    db['panels'][general_row_index]['panels'].pop(idx)
                else:
                    for m_idx,metric in enumerate(elem['targets'][0]['metrics']):
                        if str(metric['id']) == ip:
                            db['panels'][general_row_index]['panels'][idx]['targets'][0]['metrics'].pop(m_idx)
    else:
        for idx,elem in enumerate(db['panels']):
            if elem['id'] == 2005:
                if data['general']['httpThroughput_op'] == 0:
                    db['panels'].pop(idx)
                else:
                    for m_idx,metric in enumerate(elem['targets'][0]['metrics']):
                        if str(metric['id']) == ip:
                            db['panels'][idx]['targets'][0]['metrics'].pop(m_idx)

    with open('/etc/logstash/pipelines.yml', 'r') as file:
        lines = file.readlines()
    index = lines.index('- pipeline.id: '+ip+'_1\n')
    lines.pop(index+1)
    lines.pop(index)

    with open('/etc/logstash/pipelines.yml', 'w') as file:
        file.writelines(lines)

    return (db, data)


def delete_op(ip, op):

    command = ['no ip sla '+str(op)]

    run_command(ip, command)

