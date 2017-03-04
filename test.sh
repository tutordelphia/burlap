#!/bin/bash
# To run a specific command:
#
#   tox -c tox-full.ini -- -s burlap/tests/test_common.py::CommonTests::test_iter_sites
#
tox -c tox-full.ini
