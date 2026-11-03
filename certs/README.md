# Extra CA certificates (optional)

If your network uses a TLS-inspecting proxy, Docker builds fail with
`CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain` when downloading packages.
Put your organisation's root CA certificate(s) here as PEM files ending in `.crt`; both images then
trust them for the build (pip/npm) and at runtime (crawler, LLM and OAuth calls).
`*.crt` files in this folder are git-ignored. Never disable TLS verification instead.
