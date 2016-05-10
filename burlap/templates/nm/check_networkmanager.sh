#!/bin/bash
# 2015.7.26 CKS
# Meant to be periodically called by cron.
# If network-manager indicates there's no network connection
# it will be restarted.
# This is to fix cases when the wireless connection will hang
# or disconnect due to poor drivers and not automatically reconnect.
# Yes, it would be nice if we didn't have to do this.

CONNECTED=`nmcli nm status | sed -n 2p | awk '{print $2}'`
if [ $CONNECTED = "connected" ]
then
    echo "Connected! No need to do anything."
else
    echo "Disconnected! Restarting Network Manager..."
    service network-manager restart
fi
