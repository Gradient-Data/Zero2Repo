set -eux
python3 /env-assets/install-python.py
export PIP_NO_INDEX=1 PIP_FIND_LINKS=/opt/wheels
/opt/product-env/bin/python /env-assets/install-git-files.py
