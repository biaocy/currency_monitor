#!/usr/bin/env python

# -*- coding: utf-8 -*-

import websocket
import gzip
import json
from datetime import datetime
try:
    import thread
except ImportError:
    import _thread as thread

class Monitor:
    def __init__(self, currency, price_format):
        self.currency = currency
        self.price_format = '{{0:{0}}}'.format(price_format) # {0:.2F}

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
            print(dts + ',', self.price_format.format(data['tick'].get('close')))
        else:
            print('unknown message', demsg)

    def on_error(self, ws, error):
        print(error)

    def on_close(self, ws):
        print('### closed ###')

    def on_open(self, ws):
        def run(*args):
            ws.send('{{"sub": "market.{0}.detail", "id": "{0}.detail"}}'.format(self.currency))
        thread.start_new_thread(run, ())


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='monitor cryptocurrency')
    parser.add_argument('-c', '--currency', dest='currency', default='btcusdt', help='currency to monitor, default btcusdt')
    parser.add_argument('-pf', '--price-format', dest='price_format', default='.2F', help='price convert format, default .2F')
    args = parser.parse_args()
    
    print('monitor currency: {0}, price format: {1}'.format(args.currency, args.price_format))

    monitor = Monitor(args.currency, args.price_format);

    #websocket.enableTrace(True)
    ws = websocket.WebSocketApp('wss://api.huobipro.com/ws', 
            on_open = monitor.on_open, on_message = monitor.on_message, 
            on_error = monitor.on_error, on_close = monitor.on_close)
    ws.run_forever()
