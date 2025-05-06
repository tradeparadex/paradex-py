# syntax=docker/dockerfile:1

FROM ubuntu:24.04

# Install dependencies
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

# Copy uv binary from the official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /home/ubuntu

# Copy project files with ubuntu ownership
COPY --chown=ubuntu:ubuntu pyproject.toml uv.lock* ./
COPY --chown=ubuntu:ubuntu . ./paradex-py/

# Switch to ubuntu user
USER ubuntu:ubuntu

# Set virtual environment path
ENV VIRTUAL_ENV=/home/ubuntu/.venv

# Project initialization
RUN uv sync --no-install-project --quiet && \
    uv pip install 'file:///home/ubuntu/paradex-py#egg=paradex-py'
