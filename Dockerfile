# syntax=docker/dockerfile:1

FROM python:3.9-slim-buster

ENV POETRY_VERSION=1.4 \
    POETRY_VIRTUALENVS_CREATE=false


RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y \
    curl \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && curl https://sh.rustup.rs -sSf | bash -s -- -y

ENV PATH="/root/.cargo/bin:${PATH}"

# Install poetry
RUN pip install "poetry==$POETRY_VERSION"

# Copy only requirements to cache them in docker layer
WORKDIR /code
COPY poetry.lock pyproject.toml /code/

# Project initialization:
RUN poetry install --no-interaction --no-ansi --no-root --no-dev

# Copy Python code to the Docker image
COPY paradex_py /code/paradex_py/

CMD [ "python", "paradex_py/foo.py"]
