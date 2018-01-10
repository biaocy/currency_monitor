#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import crypt
import getpass
from datetime import timedelta
from functools import wraps
from hmac import compare_digest as compare_hash
from flask import Flask, session, request, redirect, url_for, escape, json
from flask import render_template
import logging

app = Flask(__name__)
app.secret_key = os.urandom(24)
pass_field = 'dwssap'
# redirect werkzeug logging
logger = logging.getLogger('werkzeug')
logger.propagate = False # disable werkzeug logger propagate up through hierarchy
logger.addHandler(logging.FileHandler(filename="flask.log"))

def run(host=None, port=None, debug=None, **options):
    global config_path, rhashed, symbols
    config_path = os.path.expanduser(os.environ['CONFIG'])
    symbol_path = os.path.expanduser(os.environ['SYMBOLS'])
    if debug:
        rhashed=crypt.crypt('5')
    else:
        rhashed=crypt.crypt(getpass.getpass())

    with open(symbol_path) as f:
        symbols = json.load(f)

    app.run(host=host, port=port, debug=debug, **options)

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

@app.route('/config', methods=['GET', 'POST'])
@login_required
def showconfig():
    bool_val = {'False': False, 'True': True}
    config = read_config()
    if request.method == 'POST':
        params = list(request.form.items(multi=True))    # list of parameters(tuple(name, value))
        c = [params.pop(params.index(t))[1] for t in params[:] if t[0] == 'currency']   # pop parameter 'currency'
        state = [params.pop(params.index(t))[1] for t in params[:] if t[0] == 'state']     # pop parameter 'state'
        state = {c[i]: s for i, s in enumerate(state)}  # to dict(currency: state)
        for i in range(0, len(params), len(c)):
            for j, k in zip(c, params[i:i+len(c)]):
                if state[j] == 'del':   # delete currencies that state is del
                    if config.get('currencies') and config['currencies'].get(j):
                        del config['currencies'][j]
                    continue

                if not config.get('currencies'):
                    config['currencies'] = {}
                if not config['currencies'].get(j):
                    config['currencies'][j] = {}
                config['currencies'][j][k[0]] = k[1] if k[1].capitalize() not in bool_val else bool_val[k[1].capitalize()]

        write_config(config)

    return render_template('config.html', config=config, symbols=symbols)

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
            if val in bool_val:     # boolean value
                rval = bool_val[val]
            elif '|' in val:        # list value
                rval = [v for v in val.split('|') if v] # non empty
            elif val.isnumeric():
                rval = nums(val)
            else:
                rval = val
            d[p[:idx]] = rval

    config = read_config()
    config.update(d)
    write_config(config)
    return json.jsonify(config)

def nums(str):
    """Convert a numeric string to number

    str -- numeric string
    """
    try:
        return int(str)
    except ValueError:
        return float(str)
