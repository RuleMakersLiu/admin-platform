# Go代码生成器Dockerfile
FROM golang:1.24-alpine AS builder
ENV GOPROXY=https://goproxy.cn,direct
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o main ./cmd/server

FROM alpine:latest
RUN apk --no-cache add ca-certificates git tzdata
WORKDIR /app
COPY --from=builder /app/main .
COPY config.yaml .
EXPOSE 8082
ENTRYPOINT ["./main"]
