#!/bin/bash
pylint --version
pylint --rcfile=pylint.rc burlap setup.py bin/burlap-admin
