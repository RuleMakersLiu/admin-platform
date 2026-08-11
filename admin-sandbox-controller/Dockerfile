# Both images must be supplied as approved internal-registry digests.
ARG GO_BASE_IMAGE
FROM ${GO_BASE_IMAGE} AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/admin-sandbox-controller ./cmd/controller

ARG RUNTIME_BASE_IMAGE
FROM ${RUNTIME_BASE_IMAGE}
COPY --from=build --chown=65532:65532 /out/admin-sandbox-controller /admin-sandbox-controller
USER 65532:65532
EXPOSE 8092
ENTRYPOINT ["/admin-sandbox-controller"]
