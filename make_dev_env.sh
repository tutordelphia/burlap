#!/bin/bash
# 2016.9.25 Creates a virtual environment for testing and local development
# of the burlap core code.
set -e
[ -d .env ] && rm -Rf .env
virtualenv .env
.env/bin/pip install burlap pylint
rm -Rf $PWD/.env/lib/python2.7/site-packages/burlap
ln -s $PWD/burlap $PWD/.env/lib/python2.7/site-packages
