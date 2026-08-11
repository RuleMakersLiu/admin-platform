# Both images must be supplied as approved internal-registry digests.
ARG GO_BASE_IMAGE
FROM ${GO_BASE_IMAGE} AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/admin-egress-gateway ./cmd/gateway

ARG RUNTIME_BASE_IMAGE
FROM ${RUNTIME_BASE_IMAGE}
COPY --from=build --chown=65532:65532 /out/admin-egress-gateway /admin-egress-gateway
USER 65532:65532
EXPOSE 8093
ENTRYPOINT ["/admin-egress-gateway"]
