# Image to host a python telegram daemon

FROM python:3 AS builder

WORKDIR /usr/local/overlord-docker

RUN python3 -m venv .venv --system-site-packages
COPY requirements.txt .
RUN .venv/bin/pip install -r requirements.txt --disable-pip-version-check

FROM python:3-slim
WORKDIR /usr/local/overlord-docker

COPY --from=builder /usr/local/overlord-docker/.venv ./.venv
COPY ./src .
COPY overlord.conf .

CMD [ ".venv/bin/python", "./overlord.py" ]
