FROM ubuntu:bionic

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-setuptools libxslt1.1

RUN pip3 install --pre rx && pip3 install --upgrade onvif_zeep

ENTRYPOINT "/home/watchdog.py"
