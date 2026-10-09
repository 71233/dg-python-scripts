#!/bin/sh
# CI-only disposable container: genuine OS Python 3.6.8 + bundled Python 3.11.5.
set -eu
cd /tmp
/usr/local/bin/python3 -I -c 'import urllib.request; urllib.request.urlretrieve("https://www.python.org/ftp/python/3.6.8/Python-3.6.8.tar.xz", "Python-3.6.8.tar.xz")'
tar -xf Python-3.6.8.tar.xz
cd Python-3.6.8
./configure --without-ensurepip > /tmp/configure.log 2>&1
make -j2 python > /tmp/make.log 2>&1 || { cat /tmp/make.log; exit 1; }
mkdir -p /tmp/os-bin /opt/Autodesk/python/2025.2.7/bin
ln -s /tmp/Python-3.6.8/python /tmp/os-bin/python3
ln -s /usr/local/bin/python3 /opt/Autodesk/python/2025.2.7/bin/python3
export PATH=/tmp/os-bin:/usr/bin:/bin
unset DGPY_PYTHON
python3 -I -c 'import sys; assert sys.version_info[:3] == (3, 6, 8); print("OS Python:", sys.version)'
cd /work
if DGPY_PYTHON=/tmp/os-bin/python3 /bin/sh tools/dgpy status --help > /tmp/rejected.log 2>&1; then
    echo 'Old Python was not rejected' >&2
    exit 1
fi
grep 'Python 3.9+ required' /tmp/rejected.log
if grep 'SyntaxError' /tmp/rejected.log; then exit 1; fi
/opt/Autodesk/python/2025.2.7/bin/python3 -I -c 'import sys; assert sys.version_info[:3] == (3, 11, 5); print("Bundled Python:", sys.version)'
/opt/Autodesk/python/2025.2.7/bin/python3 tests/test_dev_workflow.py ShellRuntimeTests -v
