# Idempotency Runtime Report

Status: `PASS`. The first server request created one intake but its response was deliberately lost. An unchanged retry reused the exact key and returned the same intake as `duplicate`; an edited draft received a new key; explicit same-key/different-payload reuse returned 409.
