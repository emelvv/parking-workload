package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
)

var (
	frontendPort  = envOr("FRONTEND_PORT", "12300")
	parserBaseURL = envOr("PARSER_BASE_URL", "http://127.0.0.1:8001")
	epoBaseURL    = envOr("EPO_BASE_URL", "http://127.0.0.1:5000")
	staticDir     = envOr("STATIC_DIR", "./public")
)

func main() {
	http.HandleFunc("/api/parking/nearest", func(w http.ResponseWriter, r *http.Request) {
		proxyGet(w, r, parserBaseURL+"/parking/nearest")
	})

	http.HandleFunc("/api/parking/occupancy", func(w http.ResponseWriter, r *http.Request) {
		proxyGet(w, r, epoBaseURL+"/api/parking/occupancy")
	})

	http.Handle("/", http.FileServer(http.Dir(staticDir)))

	fmt.Println("Server is listening on port", frontendPort+".")
	fmt.Println("Parser base URL:", parserBaseURL)
	fmt.Println("EPO base URL:", epoBaseURL)
	if err := http.ListenAndServe(":"+frontendPort, nil); err != nil {
		fmt.Println("server error:", err)
	}
}

func proxyGet(w http.ResponseWriter, r *http.Request, target string) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}

	proxyURL := target
	if r.URL.RawQuery != "" {
		proxyURL += "?" + r.URL.RawQuery
	}

	req, err := http.NewRequest(http.MethodGet, proxyURL, nil)
	if err != nil {
		w.WriteHeader(http.StatusBadGateway)
		return
	}
	req.Header.Set("Accept", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		w.WriteHeader(http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	for key, values := range resp.Header {
		for _, value := range values {
			w.Header().Add(key, value)
		}
	}
	w.Header().Set("Access-Control-Allow-Origin", "*")

	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
