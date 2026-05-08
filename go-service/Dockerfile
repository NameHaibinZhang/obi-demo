FROM golang:1.23 AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y protobuf-compiler \
    && rm -rf /var/lib/apt/lists/* \
    && go install google.golang.org/protobuf/cmd/protoc-gen-go@latest \
    && go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

COPY proto/ ./proto/
RUN protoc --go_out=. --go_opt=module=obi-demo \
    --go-grpc_out=. --go-grpc_opt=module=obi-demo \
    proto/demo.proto

COPY go.mod .
COPY main.go .
RUN go mod tidy && go build -o server .

FROM golang:1.23
WORKDIR /app
COPY --from=builder /app/server .
EXPOSE 8084
CMD ["./server"]