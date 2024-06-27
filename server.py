from flask import Flask, request, send_file
from flask_cors import CORS, cross_origin
import json
import utils
import ipaddress
import requests
import time

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
@cross_origin(supports_credentials=True)
def none():
    return ('', 204)


@app.route('/add_Router', methods=['GET', 'POST'])
@cross_origin(supports_credentials=True)
def add_Router():
    body = request.data
    tmp = body.decode('utf8')
    data = json.loads(tmp)

    ip = data['ip']
    user = data['username']
    passwd = data['password']

    try:
        ipaddress.IPv4Network(ip)
    except ValueError:
        return ('', "400 Incorrect IP format")

    if not utils.test_ssh(ip, user, passwd):
        return ('', "400 Unable to connect with "+ip)

    if not utils.add_router(ip, user, passwd):
        return ('', "400 Unable to add "+ip)

    if not utils.add_row(ip):
        return ('', "400 Unable to add row")
    
    return ('', "204 ok")


@app.route('/add_UDPJitter', methods=['GET', 'POST'])
@cross_origin(supports_credentials=True)
def add_UDPJitter():
    body = request.data
    tmp = body.decode('utf8')
    data = json.loads(tmp)
    
    host = data['host']
    receiver = data['receiver']

    try:
        ipaddress.IPv4Network(host)
        ipaddress.IPv4Network(receiver)
    except ValueError:
        return ('', "400 Incorrect IP format")

    with open('conf.json') as file:
        data = json.load(file)
    if not data.get(host):
        return ('', "400 "+host+" not found")
    
    elif not data.get(receiver):
        return ('', "400 "+receiver+" not found")

    op_id = utils.create_UDPJitter_op(host, receiver)

    utils.create_logstash_conf(host, "0")

    if len(data[host].get('udpJitter_op')) >= 1:
        print('metrics')
        utils.UDPJitter_add_metrics(host, op_id)
    else:
        print('panels')
        utils.UDPJitter_add_panels(host, op_id)
    
    return ('', "204 ok")



@app.route('/add_HTTPThroughput', methods=['GET', 'POST'])
@cross_origin(supports_credentials=True)
def add_HTTPThroughput():

    body = request.data
    tmp = body.decode('utf8')
    data = json.loads(tmp)

    host = data['host']

    try:
        ipaddress.IPv4Network(host)
    except ValueError:
        return ('', "400 Incorrect IP format")

    with open('conf.json') as file:
        data = json.load(file)
    if not data.get(host):
        return ('', "400 "+host+" not found")

    url = utils.test_bandwidth(host)

    op_id = utils.create_HTTPThroughput_op(host, url)
    if(op_id == -1):
        return ('', "400 Can not have 2 throughput operations")

    utils.create_logstash_conf(host, "1")

    utils.HTTPThroughput_add_panel(host, op_id)
    
    return ('', "204 ok")


@app.route('/del_Router', methods=['GET', 'POST'])
@cross_origin(supports_credentials=True)
def del_Router():

    body = request.data
    tmp = body.decode('utf8')
    data = json.loads(tmp)

    ip = data['ip']

    with open('conf.json') as file:
        data = json.load(file)
    if not data.get(ip):
        return ('', "400 "+ip+" not found")

    utils.delete_router(ip)

    return ('', "204 ok")


@app.route('/del_Operation', methods=['GET', 'POST'])
@cross_origin(supports_credentials=True)
def del_Operation():

    body = request.data
    tmp = body.decode('utf8')
    data = json.loads(tmp)

    ip = data['ip']
    op_id = data['op_id']

    with open('conf.json') as file:
        data = json.load(file)
    if not data.get(ip):
        return ('', "400 "+ip+" not found")

    if utils.delete_operation(ip, op_id) == -1:
        return ('', "400 The operation does not exist")

    return ('', "204 ok")


@app.route('/get_file/<f>', methods=['GET'])
def get_file(f):

    print(f)

    return send_file('downloadFiles/'+f)