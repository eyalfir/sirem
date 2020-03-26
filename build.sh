#! /bin/bash

set -o errexit
set -o nounset
set -o pipefail

python3.7 setup.py bdist_wheel
