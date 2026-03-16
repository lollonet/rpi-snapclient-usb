FROM debian:bookworm-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    git \
    libasound2-dev \
    libboost-dev \
    libavahi-client-dev \
    libflac-dev \
    libogg-dev \
    libvorbis-dev \
    libopus-dev \
    libexpat1-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Clone and build snapclient from santcasp fork (matches server)
# SANTCASP_SHA busts the Docker cache when santcasp has new commits
ARG SANTCASP_SHA=latest
WORKDIR /build
RUN echo "santcasp SHA: $SANTCASP_SHA" && \
    git clone --depth 1 --branch develop https://github.com/lollonet/santcasp.git snapcast && \
    sed -i 's/VERSION [0-9.]*-santcasp/VERSION 0.34.1/' snapcast/CMakeLists.txt && \
    grep -q 'VERSION 0.34.1' snapcast/CMakeLists.txt

WORKDIR /build/snapcast
RUN cmake -S . -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SERVER=OFF \
    -DBUILD_CLIENT=ON \
    -DBUILD_TESTS=OFF

RUN cmake --build build --parallel "$(nproc)"

# Runtime image
FROM debian:bookworm-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 \
    alsa-utils \
    libboost-system-dev \
    libboost-program-options-dev \
    libavahi-client3 \
    libflac12 \
    libogg0 \
    libvorbis0a \
    libopus0 \
    libexpat1 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled snapclient binary
COPY --from=builder /build/snapcast/bin/snapclient /usr/bin/snapclient

RUN groupadd -r -g 1000 snapclient && useradd -r -u 1000 -g snapclient -d / -s /sbin/nologin snapclient

# Entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER snapclient

ENTRYPOINT ["/entrypoint.sh"]
