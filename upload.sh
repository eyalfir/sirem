#! /bin/bash

set -o errexit
set -o nounset
set -o pipefail

python3.7 setup.py sdist --formats=gztar
FNAME=dist/`python3.7 setup.py --fullname`.tar.gz
twine upload ${FNAME}
