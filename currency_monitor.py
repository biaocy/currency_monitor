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
logging_file_path = '/var/log/huobi/{0}.log'
logger_format = '%(asctime)s, %(message)s, %(levelname)s'
last_time_send_mail = None  # last timestamp send mail
send_mail_interval = 1800   # send mail interval(seconds)

class Monitor:
    def __init__(self, config):
        self.config = {}
        self.ws = None
        self.reset(config)
        # setup root logger
        logging.basicConfig(
                filename=logging_file_path.format('monitor'), 
                format=logger_format, 
                level=logging.INFO)

    def reset(self, config):
        if self.ws and self.currencies != \
                config.get('currencies', self.currencies):
            # currencies change, should unsubscribe then subscribe
            # but server will close connection after unsubscribe
            # so close directly and re-connect in callback on_close
            self.ws.close()
        self.config.update(config)
        self.url = self.config['url']
        self.currencies = self.config['currencies']
        self.cid = {v:i for i, v in enumerate(self.currencies)} #currency index
        self.reset_logger()
        # {0:.2F}
        self.price_format = ['{{0:{0}}}'.format(p) for p in self.config['price_format'] if p]
        self.threshold = self.config['threshold']
        self.email = self.config['email']
        self.operator = self.config['operator']

    def reset_logger(self):
        formatter = logging.Formatter(logger_format, datefmt=tsformat)
        for c in self.currencies:
            logger = logging.getLogger(c)
            logger.propagate = False            # disable logger propagate
            if not logger.hasHandlers():
                fh = logging.FileHandler(logging_file_path.format(c))
                fh.setLevel(logging.INFO)
                fh.setFormatter(formatter)
                logger.addHandler(fh)

    def get_config_value(self, l, cid, default):
        """
        l       - value list
        cid     - currency index
        default - default value
        """
        if len(l) > cid:
            return l[cid]
        return default

    def default(self, key):
        """
        return default key's value
        key - config key
        """
        return self.config['default'][key]

    def notify_if_exceed_threshold(self, price, currency):
        cid = self.cid[currency]
        op = self.get_config_value(self.operator, cid, 
                self.default('operator'))
        ths = self.get_config_value(self.threshold, cid, 
                self.default('threshold'))
        expr = '{0}{1}{2}'.format(price, op, ths)
        if not se.seval(expr):
            return

        if not self.config.get('notify', False):
            return
        if not (ths and op and self.email):
            temp = 'threshold: %s, email: %s, operator: %s. \
                    Something not set, email not send'
            logging.getLogger(currency).info(temp, ths, self.email, op)
            return
        
        mailopt = {}
        content = '{0}: {1}'.format(currency, expr)
        mailopt['content'] = self.config.get('mail.content', content)
        mailopt['to'] = self.email
        global last_time_send_mail
        if not last_time_send_mail:
            last_time_send_mail = datetime.now().timestamp()
            mail.sendmail(**mailopt)
        else:
            interval = datetime.now().timestamp() - last_time_send_mail
            if interval > send_mail_interval:
                last_time_send_mail = datetime.now().timestamp()
                mail.sendmail(**mailopt)

    def on_message(self, ws, msg):
        demsg = gzip.decompress(msg).decode('utf-8')
        data = json.loads(demsg)
        if data.get('ping'):
            ts = data['ping']
            pong = '{{"pong": {0}}}'.format(ts)
            ws.send(pong)
        elif data.get('tick'):
            ch = data['ch'].split('.')[1]
            cid = self.cid[ch]
            price_format = self.get_config_value(self.price_format, cid, 
                    self.default('price_format'))
            price = price_format.format(data['tick'].get('close'))
            logging.getLogger(ch).info('%s: %s', ch, price)
            self.notify_if_exceed_threshold(price, ch)
        elif data.get('subbed'):
            ch = data['subbed'].split('.')[1]
            logging.getLogger(ch).info('%s: subscribe success', ch)
        else:
            logging.info('unknown message %s', demsg)

    def on_error(self, ws, error):
        logging.info('on_error: %s', error)

    def on_close(self, ws):
        logging.info('close connection, wait 5 sec to re-connect')
        time.sleep(5)
        self.start()

    def on_open(self, ws):
        logging.info('open connection')
        self.subscribe(self.currencies)

    def subscribe(self, currencies):
        temp = '{{"sub": "market.{0}.detail", "id": "{0}.detail"}}'
        for c in currencies:
            self.ws.send(temp.format(c))

    def unsubscribe(self, currencies):
        temp = '{{"unsub": "market.{0}.detail", id": "{0}.detail"}}'
        for c in currencies:
            self.ws.send(temp.format(c))

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
    while _CONF_PATH_ and os.path.exists(os.path.expanduser(_CONF_PATH_)):  
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
    h = """
    Currencies to monitor, default: %s;
    Support multiple currencies, -c c1 -c c2 ...
    """ % default_currency
    parser.add_argument('-c', '--currencies', action='append', 
            dest='currencies', help=h)
    
    h = """
    Price convert format, default: %s;
    Argument count should be same as currencies count, 
    otherwise use default format, -f f1 -f f2 ...
    """ % default_price_format
    parser.add_argument('-f', '--price-format', action='append', 
            dest='price_format', help=h)

    h= """
    Threshold price to notify, default: %s;
    Argument count should be same as currencies count,
    -t t1 -t t2 ...
    """ % default_threshold
    parser.add_argument('-t', '--threshold', action='append', 
            dest='threshold', help=h)

    h = """
    Operator to compare threshold price, default: %s;
    Argument count should be same as currencies count,
    -o o1 -o o2 ...
    """ % default_operator
    parser.add_argument('-o', '--operator', action='append', 
            dest='operator', choices=['>', '>=', '<', '<='], help=h)
    parser.add_argument('-e', '--email', dest='email', 
            help='email address to notify')
    parser.add_argument('-n', '--notify', dest='notify', action='store_true',
            help='If present, notify when currency price exceed threshold, \
                    otherwise not notify')
    parser.add_argument('-l', '--url', dest='url', 
            help='api url, default: '+default_url)
    parser.add_argument('-C', '--config', dest='config', 
            help='configuration file, json format. If same argument exists \
            in config and optional augment, optional argument takes \
            precedence!')
    args = parser.parse_args()
  
    global _CONF_PATH_
    _CONF_PATH_ = args.config
    config = parse_config()

    argdict = {
            'currencies':   [default_currency],
            'price_format': [default_price_format],
            'url':          default_url,
            'operator':     [default_operator],
            'notify':       False,
            'email':        None,
            'threshold':    [default_threshold]
            }

    for k, v in argdict.items():
        set_arg(args, config, k, v)
    
    config['default'] = {
            'price_format': default_price_format,
            'operator': default_operator,
            'threshold': default_threshold
            }

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
