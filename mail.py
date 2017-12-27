# -*- coding: utf-8 -*-

import smtplib
from email.mime.text import MIMEText

def sendmail(content, to, mfrom='Fox', subject='Currency Monitor'):
    msg = MIMEText(content)
    msg['Subject'] = subject
    msg['From'] = mfrom
    msg['To'] = to

    s = smtplib.SMTP('localhost')
    s.send_message(msg)
    s.quit()
