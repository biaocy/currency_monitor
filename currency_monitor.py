#!/usr/bin/python3

# -*- coding: utf-8 -*-

import os
import sys
import websocket
import gzip
import json
import time
import safeeval as se
import argparse
import mail
import logging
from datetime import datetime
try:
    import threading
except ImportError:
    import dummy_threading as threading

tsformat = '%Y-%m-%d %X'
logging_file_path='/var/log/huobi/{0}.log'

class Monitor:
    def __init__(self, config):
        self.config = {}
        self.ws = None
        self.reset(config)

    def reset(self, config):
        if self.ws and self.currency != config.get('currency', self.currency):
            # currency change, should unsubscribe then subscribe
            # but server will close connection after unsubscribe
            # so close directly and re-conect in callback on_close
            self.ws.close()
        self.config.update(config)
        self.url = self.config['url']
        self.currency = self.config['currency']
        self.reset_logger()
        # {0:.2F}
        self.price_format = '{{0:{0}}}'.format(self.config['price_format']) 
        self.threshold = self.config['threshold']
        self.email = self.config['email']
        self.operator = self.config['operator']

    def reset_logger(self):
        logger = logging.getLogger()
        for hdlr in logger.handlers[:]:
            logger.removeHandler(hdlr)
        logging.basicConfig(filename=logging_file_path.format(self.currency), format='%(message)s, %(levelname)s', level=logging.INFO)

    def notify_if_exceed_threshold(self, price):
        expr = '{0}{1}{2}'.format(price, self.operator, self.threshold)
        if not se.seval(expr):
            return

        if not self.config.get('notify', False):
            return
        if not (self.threshold and self.email and self.operator):
            temp = 'threshold: %s, email: %s, operator: %s. \
                    Something not set, email not send'
            logging.info(temp, self.threshold, self.email, self.operator)
            return
        
        logging.info('sent mail')

        #mailopt = {}
        #mailopt['content'] = self.config.get('mail.content', expr)
        #mailopt['to'] = self.email
        #mail.sendmail(**mailopt)

    def on_message(self, ws, msg):
        demsg = gzip.decompress(msg).decode('utf-8')
        data = json.loads(demsg)
        ts = data.get('ts', datetime.now().timestamp()*1000)
        dts = datetime.fromtimestamp(ts/1000).strftime(tsformat)
        if data.get('ping'):
            ts = data['ping']
            pong = '{{"pong": {0}}}'.format(ts)
            ws.send(pong)
        elif data.get('tick'):
            price = self.price_format.format(data['tick'].get('close'))
            ch = data['ch'].split('.')[1]
            logging.info('%s, %s: %s', dts, ch, price)
            self.notify_if_exceed_threshold(price)
        else:
            logging.info('unknown message %s', demsg)

    def on_error(self, ws, error):
        logging.info('on_error: %s', error)

    def on_close(self, ws):
        logging.info('%s, close connection, wait 5 sec to re-connect', datetime.now().strftime(tsformat))
        time.sleep(5)
        self.start()

    def on_open(self, ws):
        self.subscribe(self.currency)

    def subscribe(self, currency):
        temp = '{{"sub": "market.{0}.detail", "id": "{0}.detail"}}'
        self.ws.send(temp.format(currency))

    def unsubscribe(self, currency):
        temp = '{{"unsub": "market.{0}.detail", id": "{0}.detail"}}'
        self.ws.send(temp.format(currency))

    def start(self):
        #websocket.enableTrace(True)
        ws = websocket.WebSocketApp(self.url, 
                on_open = self.on_open, 
                on_message = self.on_message, 
                on_error = self.on_error, 
                on_close = self.on_close)
        self.ws = ws
        ws.run_forever()

def run():
    global _CONF_PATH_
    global _LAST_MTIME_
    # while configuration file specified and exists
    while os.path.exists(os.path.expanduser(_CONF_PATH_)):  
        lastmtime = os.stat(_CONF_PATH_).st_mtime
        if lastmtime > _LAST_MTIME_:
            _LAST_MTIME_ = lastmtime
            _MONITOR_.reset(parse_config())
            logging.info('refresh config %s', _MONITOR_.config)
        time.sleep(1)

def parse_config():
    global _LAST_MTIME_
    config = {}
    if not _CONF_PATH_:
        return config

    if not os.path.exists(os.path.expanduser(_CONF_PATH_)):
        sys.exit("config file: {0}, not exists!")
    else:
        if not _LAST_MTIME_:        # first time read
            _LAST_MTIME_ = os.stat(_CONF_PATH_).st_mtime
        with open(_CONF_PATH_) as f:
            config = json.load(f)

    return config


def set_arg(args, config, attr, default_val):
    """Set config's attribute
    Precedent: args > config > default_val
    
    args        --  arguments parse from command line
    config      --  program config object
    attr        --  attribute name
    default_val --  attribute default value
    """
    val = getattr(args, attr)
    if val:
        config[attr] = val
    else:
        config.setdefault(attr, default_val)

def parse_arg():
    default_url = 'wss://api.huobi.pro/ws'
    default_currency = 'btcusdt'
    default_price_format = '.2F'
    default_operator = '>='
    default_threshold = 10000
    
    """argument precedence: optional argument > config file > default"""
    parser = argparse.ArgumentParser(description='cryptocurrency monitor')
    parser.add_argument('-c', '--currency', dest='currency', 
            help='currency to monitor, default: '+default_currency)
    parser.add_argument('-f', '--price-format', dest='price_format', 
            help='price convert format, default: '+default_price_format)
    parser.add_argument('-l', '--url', dest='url', 
            help='api url, default: '+default_url)
    parser.add_argument('-C', '--config', dest='config', 
            help='configuration file, json format. If same argument exists \
            in config and optional augment, optional argument takes \
            precedence!')
    parser.add_argument('-t', '--threshold', dest='threshold',
            help='threshold price to notify, default: '+str(default_threshold))
    parser.add_argument('-o', '--operator', dest='operator',
            choices=['>', '>=', '<', '<='],
            help='operator to compare threshold price, default: '
            +default_operator)
    parser.add_argument('-e', '--email', dest='email', 
            help='email address to notify')
    parser.add_argument('-n', '--notify', dest='notify', action='store_true',
            help='If present, notify when currency price exceed threshold, \
                    otherwise not notify')
    args = parser.parse_args()
  
    global _CONF_PATH_
    _CONF_PATH_ = args.config
    config = parse_config()

    argdict = {
            'currency':     default_currency,
            'price_format': default_price_format,
            'url':          default_url,
            'operator':     default_operator,
            'notify':       False,
            'email':        None,
            'threshold':    default_threshold
            }

    for k, v in argdict.items():
        set_arg(args, config, k, v)

    return config

if __name__ == '__main__':
    _CONF_PATH_ = None   # configuration file path
    _LAST_MTIME_ = None  # configuration file last modifed time, if exists
    _MONITOR_ = None     # Monitor instance

    config = parse_arg()
    #print(config)
    _MONITOR_ = Monitor(config)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    _MONITOR_.start()
