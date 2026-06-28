FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake git ninja-build python3 \
    bison flex pkg-config libglib2.0-dev libpixman-1-dev libfdt-dev \
    zlib1g-dev libzstd-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
