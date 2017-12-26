# -*- coding: utf-8 -*-

import smtplib
from email.mime.text import MIMEText

msg = MIMEText('What the fox say')
msg['Subject'] = 'The contents of email'
msg['From'] = 'Fox'
msg['To'] = 'biaocy@foxmail.com'

s = smtplib.SMTP('localhost')
s.send_message(msg)
s.quit()
