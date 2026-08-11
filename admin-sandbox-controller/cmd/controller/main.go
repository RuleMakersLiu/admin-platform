package main

import (
	"log"
	"net/http"
	"os"
	"time"

	"admin-sandbox-controller/internal/server"
)

func main() {
	address := os.Getenv("SANDBOX_LISTEN_ADDRESS")
	if address == "" {
		address = ":8092"
	}
	srv := &http.Server{
		Addr:              address,
		Handler:           server.FromEnvironment().Handler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       30 * time.Second,
	}
	log.Printf("admin-sandbox-controller listening on %s", address)
	log.Fatal(srv.ListenAndServe())
}
