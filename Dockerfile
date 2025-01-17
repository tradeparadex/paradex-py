# syntax=docker/dockerfile:1

FROM ubuntu:24.04

RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cargo \
        curl \
        python3-dev \
        python3-pip \
        python3-poetry \
        rustc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements to cache them in docker layer
WORKDIR /code
COPY poetry.lock pyproject.toml /code/

# Project initialization:
RUN poetry install --no-interaction --no-ansi --no-root --no-dev

# Copy Python code to the Docker image
COPY paradex_py /code/paradex_py/
