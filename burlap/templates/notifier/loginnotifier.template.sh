#!/bin/bash
# 2012.3.27 CKS
# Custom operations run anytime anyone logs in.
# Usually installed to /etc/profile.d/custom.sh

SYSADMIN_EMAIL={{loginnotifier_sysadmin_email}}
export SYSADMIN_EMAIL

# Send an email recording login.
HOST=`who am i | sed -r "s/.*\((.*)\).*/\\1/"`
DOMAIN=`host $HOST`
echo -e "$DOMAIN" | mailx -s "SSH: Login from $HOST" $SYSADMIN_EMAIL &> /dev/null
