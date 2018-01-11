#!/bin/bash
# Runs the entire test suite locally.
# To run a specific command:
#
#   tox -c tox-full.ini -- -s burlap/tests/test_common.py::CommonTests::test_iter_sites
#
set -e
time ./pep8.sh
rm -Rf ./burlap/*.pyc
time tox -c tox-full.ini
