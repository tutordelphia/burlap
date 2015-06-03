"""
Helper functions for sending a notification email after each deployment.
"""
from fabric.api import (
    task, env, local, run, sudo, get, put, runs_once, execute, settings, task
)

from burlap.common import (
    put_or_dryrun,
    get_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    run_or_dryrun,
)
from burlap.decorators import task_or_dryrun

if 'notifier_email_enabled' not in env:
    env.notifier_email_enabled = False
    env.notifier_email_host = None
    env.notifier_email_port = 587
    env.notifier_email_host_user = None
    env.notifier_email_host_password = None
    env.notifier_email_use_tls = True
    env.notifier_email_recipient_list = []

def send_email(subject, message, from_email=None, recipient_list=[]):
    import smtplib
    from email.mime.text import MIMEText
    
    if not recipient_list:
        return
    
    from_email = from_email or env.notifier_email_host_user
    
    msg = MIMEText(message)
    
    # me == the sender's email address
    # you == the recipient's email address
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = '; '.join(recipient_list)
    
    # Send the message via our own SMTP server, but don't include the
    # envelope header.
    print('Attempting to send mail using %s...' % env.notifier_email_host)
    s = smtplib.SMTP(env.notifier_email_host, env.notifier_email_port)
    s.ehlo()
    s.starttls()
    s.ehlo()
    s.login(env.notifier_email_host_user, env.notifier_email_host_password)
    s.sendmail(from_email, recipient_list, msg.as_string())
    s.quit()

@task_or_dryrun
#@runs_once
def notify_post_deployment():
    if env.notifier_email_enabled and env.host_string == env.hosts[-1]:
        send_email(
            subject='%s Deployment Complete' % env.ROLE.title(),
            message='Deployment to %s is complete.' % env.ROLE,
            recipient_list=env.notifier_email_recipient_list)
