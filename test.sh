#!/bin/bash
# Runs the entire test suite locally.
# To run a specific command:
#
#   tox -c tox-full.ini -- -s burlap/tests/test_common.py::CommonTests::test_iter_sites
#
set -e
./pep8.sh
tox -c tox-full.ini
