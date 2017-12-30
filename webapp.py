#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import crypt
import getpass
from datetime import timedelta
from functools import wraps
from hmac import compare_digest as compare_hash
from flask import Flask, session, request, redirect, url_for, escape, json

if not os.environ.get('CONFIG'):
    raise ValueError('CONFIG must specified!')

config_path = os.path.expanduser(os.environ['CONFIG'])
rhashed=crypt.crypt(getpass.getpass())
app = Flask(__name__)
app.secret_key = os.urandom(24)
pass_field = 'dwssap'

def read_config():
    with open(config_path) as f:
        return json.load(f)

def write_config(config):
    with open(config_path, 'w') as f:
        json.dump(config, f, indent='\t', sort_keys=True)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        phashed = session.get(pass_field)
        if not phashed or not compare_hash(rhashed, phashed):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=30)


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        hashed = crypt.crypt(request.form[pass_field], rhashed)
        if not compare_hash(rhashed, hashed):
            return 'user or password wrong'
        else:
            session[pass_field] = hashed
            return redirect(url_for('showconfig'))
    else:
        phashed = session.get(pass_field)
        if phashed and compare_hash(rhashed, phashed):
            return redirect(url_for('showconfig'))
        return '''
            <form method="post">
                <p><input type=password name=dwssap>
            </form>
        '''

@app.route('/logout')
def logout():
    session.pop(pass_field, None)
    return redirect(url_for('login'))

@app.route('/config')
@login_required
def showconfig():
    config = read_config()
    return json.jsonify(config)

@app.route('/config/del/<string:keys>')
@login_required
def delconfig(keys):
    config = read_config()
    for k in keys.split(','):
        if k in config:
            del config[k]
    
    write_config(config)
    return redirect(url_for('showconfig'))

@app.route('/config/<string:conf>')
@login_required
def config(conf):
    bool_val = {
                'false': False,
                'true': True
                }
    d = {}
    for p in conf.split(','):
        idx = p.find('=')
        if idx >= 1:    # key-pair exists, key at least 1 character
            val = p[idx+1:]
            if val in bool_val:
                rval = bool_val[val]
            elif val.isnumeric():
                rval = nums(val)
            else:
                rval = val
            d[p[:idx]] = rval

    with open(config_path) as f:
        config = json.load(f)

    config.update(d)

    with open(config_path, 'w') as f:
        json.dump(config, f, indent='\t', sort_keys=True)
    
    return json.jsonify(config)

def nums(str):
    """Convert a numeric string to number

    str -- numeric string
    """
    try:
        return int(str)
    except ValueError:
        return float(str)
