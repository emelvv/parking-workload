package main

import (
	"fmt"
	"net/http"
)

const port = "12300"

func main() {
    http.Handle("/", http.FileServer(http.Dir("./public")))

    fmt.Println("Server is listening on port ", port+".")
    http.ListenAndServe(":"+port, nil)
}