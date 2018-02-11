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
import logging.handlers
from datetime import datetime
from web import app
try:
    import threading
except ImportError:
    import dummy_threading as threading

TSFORMAT = '%Y-%m-%d %X'
LOGGING_FILE_PATH = 'log/huobi/{0}.log'
LOGGER_FORMAT = '%(asctime)s, %(message)s, %(levelname)s'
LAST_TIME_SEND_MAIL = {}    # last timestamp send mail
SEND_MAIL_INTERVAL = 1800   # send mail interval(seconds)

class Monitor:
    def __init__(self, url, config):
        self.url = url
        self.config = config
        self.ws = None
        self.reset(config)
        # setup root logger
        logging.basicConfig(
                filename=LOGGING_FILE_PATH.format('monitor'), 
                format=LOGGER_FORMAT, 
                level=logging.INFO)

    def reset(self, config):
        if self.ws and self.config['currencies'] != \
                config.get('currencies', self.config['currencies']):
            # currencies change, should unsubscribe then subscribe
            # but server will close connection after unsubscribe
            # so close directly and re-connect in callback on_close
            global LAST_TIME_SEND_MAIL
            LAST_TIME_SEND_MAIL = {}
            self.ws.close()
        self.config.update(config)
        self.reset_logger()

    def reset_logger(self):
        formatter = logging.Formatter(LOGGER_FORMAT, datefmt=TSFORMAT)
        for c in self.config["currencies"].keys():
            logger = logging.getLogger(c)
            logger.propagate = False            # disable logger propagate
            if not logger.hasHandlers():
                fh = logging.handlers.RotatingFileHandler(
                        LOGGING_FILE_PATH.format(c), 
                        maxBytes=5242880, backupCount=10) #50M
                fh.setLevel(logging.INFO)
                fh.setFormatter(formatter)
                logger.addHandler(fh)

    def notify_if_exceed_threshold(self, price, currency):
        c = self.config['currencies'][currency]
        if not c.get('notify', False):
            return
        if not (self.config['email'] and (c.get('lowop') or c.get('highop'))):
            temp = 'email: %s. Something not set, email not send'
            logging.getLogger(currency).info(temp, self.config['email'])
            return
        
        exprs = []
        opth = {'lowop': 'low', 'highop': 'high'}
        for op, th in opth.items():
            expr = '{0}{1}{2}'.format(price, c.get(op), c.get(th))
            if se.seval(expr):
                exprs.append(expr)

        if not len(exprs):
            return

        mailopt = {}
        mailopt['content'] = '\n'.join(exprs)
        mailopt['to'] = self.config['email']
        global LAST_TIME_SEND_MAIL
        lasttime = LAST_TIME_SEND_MAIL.get(currency)
        if not lasttime:
            LAST_TIME_SEND_MAIL[currency] = datetime.now().timestamp()
            if self.config['debug']:
                logging.info(mailopt)
            else:
                mail.sendmail(**mailopt)
        else:
            interval = datetime.now().timestamp() - lasttime
            if interval > SEND_MAIL_INTERVAL:
                LAST_TIME_SEND_MAIL[currency] = datetime.now().timestamp()
                if self.config['debug']:
                    logging.info(mailopt)
                else:
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
            price_format = self.config['currencies'][ch]['price_format']
            price = '{{0:{0}}}'.format(price_format).format(data['tick'].get('close'))
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
        self.subscribe()

    def subscribe(self):
        temp = '{{"sub": "market.{0}.detail", "id": "{0}.detail"}}'
        for c in self.config['currencies'].keys():
            self.ws.send(temp.format(c))

    def unsubscribe(self):
        temp = '{{"unsub": "market.{0}.detail", id": "{0}.detail"}}'
        for c in self.config['currencies'].keys():
            self.ws.send(temp.format(c))

    def start(self):
        if self.config['debug']:
            websocket.enableTrace(True)
        ws = websocket.WebSocketApp(self.url, 
                on_open = self.on_open, 
                on_message = self.on_message, 
                on_error = self.on_error, 
                on_close = self.on_close)
        self.ws = ws
        ws.run_forever()

def check_config():
    global _LAST_MTIME_
    # while configuration file specified and exists
    while os.path.exists(os.path.expanduser(CONFIG['config'])):  
        lastmtime = os.stat(CONFIG['config']).st_mtime
        if lastmtime > _LAST_MTIME_:
            _LAST_MTIME_ = lastmtime
            parse_config()
            _MONITOR_.reset(CONFIG)
            logging.info('refresh config %s', _MONITOR_.config)
        time.sleep(1)

def parse_config():
    global _LAST_MTIME_
    global CONFIG

    if not os.path.exists(os.path.expanduser(CONFIG['config'])):
        sys.exit("config file: {0}, not exists!")
    else:
        if not _LAST_MTIME_:        # first time read
            _LAST_MTIME_ = os.stat(CONFIG['config']).st_mtime
        with open(CONFIG['config']) as f:
            CONFIG.update(json.load(f))

def parse_arg():
    global CONFIG
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', dest='config',
            default='config.json',
            help='configuration file, json format. See config.json.template')
    parser.add_argument('-s', '--symbols', dest='symbols',
            default='symbols.json',
            help='currency symbols configuration file, json format. '+
            'See symbols.json.template')
    parser.add_argument('-d', '--debug', action='store_true', 
            dest='debug', help='Debug flag, default off')
    parser.add_argument('--host', dest='host', default='0.0.0.0',
            help='flask host')
    parser.add_argument('--port', dest='port', default='15000', type=int,
            help='flask port')
    args = parser.parse_args()

    CONFIG['config'] = args.config
    CONFIG['symbols'] = args.symbols
    CONFIG['debug'] = args.debug
    CONFIG['host'] = args.host
    CONFIG['port'] = args.port

def run_web():
    os.environ['CONFIG'] = CONFIG['config']
    os.environ['SYMBOLS'] = CONFIG['symbols']
    args = {
            'debug': CONFIG['debug'],
            'host': CONFIG['host'],
            'port': CONFIG['port']}
    threading.Thread(target=app.run, kwargs=args, daemon=True).start()

if __name__ == '__main__':
    _LAST_MTIME_ = None     # configuration file last modifed time, if exists
    _MONITOR_ = None        # Monitor instance
    CONFIG = {}             # config dict
    parse_arg()
    parse_config()
    run_web()
    _MONITOR_ = Monitor('wss://api.huobi.pro/ws', CONFIG)
    threading.Thread(target=check_config, daemon=True).start()
    _MONITOR_.start()
