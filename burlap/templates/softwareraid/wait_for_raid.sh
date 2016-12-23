#!/bin/bash
# 2016.10.29 CKS Blocks until RAID finishes rebuilding.
echo "Waiting for RAID array to synchronize..."
until ${mdstat_done:-false} ; do
    if grep \"\[UU\]\" /proc/mdstat > /dev/null ; then
        break
    else
        grep [UU] /proc/mdstat
        echo "Waiting..."
        sleep ${sleepSecs:-10}
    fi
done
