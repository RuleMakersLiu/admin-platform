package main

import (
	"log"
	"net/http"
	"os"
	"time"

	"admin-egress-gateway/internal/server"
)

func main() {
	handler, err := server.FromEnvironment()
	if err != nil {
		log.Fatal(err)
	}
	address := os.Getenv("EGRESS_LISTEN_ADDRESS")
	if address == "" {
		address = ":8093"
	}
	srv := &http.Server{Addr: address, Handler: handler.Handler(), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 70 * time.Second, WriteTimeout: 70 * time.Second, IdleTimeout: 30 * time.Second}
	log.Printf("admin-egress-gateway listening on %s", address)
	log.Fatal(srv.ListenAndServe())
}
