FROM ubuntu:22.04 AS builder

RUN apt-get update && apt-get install -y \
    build-essential cmake libhiredis-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /usr/local/include \
    && curl -sL https://github.com/yhirose/cpp-httplib/archive/refs/tags/v0.18.3.tar.gz | tar xz -C /tmp \
    && cp /tmp/cpp-httplib-0.18.3/httplib.h /usr/local/include/ \
    && mkdir -p /usr/local/include/nlohmann \
    && curl -sL https://github.com/nlohmann/json/releases/download/v3.11.3/json.hpp \
    -o /usr/local/include/nlohmann/json.hpp

WORKDIR /app
COPY main.cpp CMakeLists.txt .
RUN cmake -B build && cmake --build build -j$(nproc)

FROM ubuntu:22.04

RUN apt-get update && apt-get install -y libhiredis-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/build/obi-demo-cpp .

EXPOSE 8086
CMD ["./obi-demo-cpp"]