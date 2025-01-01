# Image to host a python telegram daemon

FROM ubuntu:22.04 AS builder

RUN export DEBIAN_FRONTEND=noninteractive; \
    export DEBCONF_NONINTERACTIVE_SEEN=true; \
    apt-get update -qqy && apt-get install -qqy --option Dpkg::Options::="--force-confnew" --no-install-recommends \
    autoconf automake build-essential pkgconf libtool libzip-dev libjpeg-dev tzdata python3 python3.10-venv \
    git libavformat-dev libavcodec-dev libavutil-dev libswscale-dev libavdevice-dev \
    libwebp-dev gettext autopoint libmicrohttpd-dev ca-certificates imagemagick curl wget \
    libavformat-dev libavcodec-dev libavutil-dev libswscale-dev libavdevice-dev ffmpeg x264 && \
    apt-get --quiet autoremove --yes && \
    apt-get --quiet --yes clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /usr/local/overlord-docker

RUN python3 -m venv .venv --system-site-packages
COPY requirements.txt .
RUN .venv/bin/pip install -r requirements.txt --disable-pip-version-check

WORKDIR /usr/local/overlord-docker
COPY ./src .
COPY overlord.conf .

CMD [ ".venv/bin/python", "./overlord.py" ]
