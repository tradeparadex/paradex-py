# syntax=docker/dockerfile:1

FROM ubuntu:24.04

RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cargo \
        curl \
        git \
        python3-dev \
        python3-pip \
        python3-poetry \
        rustc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements to cache them in docker layer
COPY --chown=ubuntu:ubuntu poetry.lock pyproject.toml /home/ubuntu/

USER ubuntu:ubuntu

WORKDIR /home/ubuntu

COPY --chown=paradex:paradex . /home/ubuntu/paradex-py

# Project initialization:
RUN poetry install --no-interaction --no-ansi --no-root \
    && poetry run pip install 'file:///home/ubuntu/paradex-py#egg=paradex-py' \
