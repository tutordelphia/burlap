#!/bin/bash
# 2016.9.25 Creates a virtual environment for testing and local development
# of the burlap core code.
virtualenv .env
.env/bin/pip install burlap
rm -Rf $PWD/.env/lib/python2.7/site-packages/burlap
ln -s $PWD/burlap $PWD/.env/lib/python2.7/site-packages
