#!/usr/bin/python3

# -*- coding: utf-8 -*-

import os
import sys
import websocket
import gzip
import json
import time
from datetime import datetime
import safeeval as se
import argparse
try:
    import threading
except ImportError:
    import dummy_threading as threading

class Monitor:
    def __init__(self, config):
        self.config = {}
        self.reset(config)

    def reset(self, config):
        self.config.update(config)
        self.url = self.config['url']
        self.currency = self.config['currency']
        self.price_format = '{{0:{0}}}'.format(self.config['price_format']) # {0:.2F}
        self.threshold = self.config['threshold']
        self.email = self.config['email']
        self.operator = self.config['operator']

    def notify_if_exceed_threshold(self, price):
        if not (self.threshold and self.email and self.operator):
            return
        expr = '{0}{1}{2}'.format(price, self.operator, self.threshold)
        if se.seval(expr):  # notify
            print(expr, True)
        else:
            print(expr, False)

    def on_message(self, ws, msg):
        demsg = gzip.decompress(msg).decode('utf-8')
        data = json.loads(demsg)
        if data.get('ping'):
            ts = data['ping']
            pong = '{{"pong": {0}}}'.format(ts)
            ws.send(pong)
        elif data.get('tick'):
            tsformat = '%Y-%m-%d %X'
            ts = data.get('ts')
            dts = datetime.fromtimestamp(ts / 1000).strftime(tsformat) if ts else datetime.now().strftime(tsformat)
            price = self.price_format.format(data['tick'].get('close'))
            print(dts+',', self.currency+':', price)
            self.notify_if_exceed_threshold(price)
        else:
            print('unknown message', demsg)

    def on_error(self, ws, error):
        print(error)

    def on_close(self, ws):
        print('### closed ###')
        t.join()

    def on_open(self, ws):
        ws.send('{{"sub": "market.{0}.detail", "id": "{0}.detail"}}'.format(self.currency))

    def start(self):
        #websocket.enableTrace(True)
        ws = websocket.WebSocketApp(self.url, 
                on_open = self.on_open, 
                on_message = self.on_message, 
                on_error = self.on_error, 
                on_close = self.on_close)
        ws.run_forever()

def run():
    global _CONF_PATH_
    global _LAST_MTIME_
    while os.path.exists(os.path.expanduser(_CONF_PATH_)):  # while configuration file specified and exists
        lastmtime = os.stat(_CONF_PATH_).st_mtime
        if lastmtime > _LAST_MTIME_:
            _LAST_MTIME_ = lastmtime
            _MONITOR_.reset(parse_config())
            print('refresh config', _MONITOR_.config)
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

def parse_arg():
    default_url = 'wss://api.huobi.pro/ws'
    default_currency = 'btcusdt'
    default_price_format = '.2F'
    default_operator = '>='
    
    """argument precedence: optional argument > config file > default"""
    parser = argparse.ArgumentParser(description='monitor cryptocurrency')
    parser.add_argument('-c', '--currency', dest='currency', help='currency to monitor, default: '+default_currency)
    parser.add_argument('-f', '--price-format', dest='price_format', help='price convert format, default: '+default_price_format)
    parser.add_argument('-l', '--url', dest='url', help='api url, default: '+default_url)
    parser.add_argument('-C', '--config', dest='config', help='configuration file, json format. If same argument specified in config and optional augment, optional argument takes precedence!')
    parser.add_argument('-t', '--threshold', dest='threshold', help='threshold price to notify')
    parser.add_argument('-o', '--operator', dest='operator', help='operator to compare threshold price, default: '+default_operator)
    parser.add_argument('-e', '--email', dest='email', help='email address to notify')
    args = parser.parse_args()
  
    global _CONF_PATH_
    _CONF_PATH_ = args.config
    config = parse_config()

    if args.currency:
        config['currency'] = args.currency
    else:
        config.setdefault('currency', default_currency)

    if args.price_format:
        config['price_format'] = args.price_format
    else:
        config.setdefault('price_format', default_price_format)
    
    if args.url:
        config['url'] = args.url
    else:
        config.setdefault('url', default_url)

    if args.operator:
        config['operator'] = args.operator
    else:
        config.setdefault('operator', default_operator)

    if args.email:
        config['email'] = args.email
    else:
        config.setdefault('email')

    if args.threshold:
        config['threshold'] = args.threshold
    else:
        config.setdefault('threshold')

    return config

if __name__ == '__main__':
    _CONF_PATH_ = None   # configuration file path
    _LAST_MTIME_ = None  # configuration file last modifed time, if exists
    _MONITOR_ = None     # Monitor instance

    config = parse_arg()
    print(_CONF_PATH_, _LAST_MTIME_)
    print(config)
    _MONITOR_ = Monitor(config)
    t = threading.Thread(target=run)
    t.start()
    #_MONITOR_.start();
