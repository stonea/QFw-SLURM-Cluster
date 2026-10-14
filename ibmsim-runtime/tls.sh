#!/bin/sh
#
# Issue the Runtime front's TLS certificate at container start. MQSC's IBM
# QDMI device library sends plain HTTP only to loopback addresses and verifies
# every HTTPS peer, so clients on the cluster network need HTTPS with a
# certificate they can verify.
#
# Each start creates a fresh private CA, signs a server certificate for the
# names in SAN with it, then discards the CA key, so
# nothing can sign another certificate with it. Only the CA certificate leaves
# the container: it is published to /tls/ca.crt (shared-dir/ibmsim-tls/ca.crt
# on the host, /mnt/ibmsim-tls/ca.crt in the cluster), for clients to name in
# CURL_CA_BUNDLE. The server key stays in the container's /run.

set -eu

PRIVATE_DIR=/run/ibmsim-tls
CA_OUT=/tls/ca.crt
# ibmsim-runtime for cluster nodes; localhost and 127.0.0.1 for the host's
# published port.
SAN="DNS:ibmsim-runtime,DNS:localhost,IP:127.0.0.1"
DAYS=825

umask 077
rm -rf "${PRIVATE_DIR}"
mkdir -p "${PRIVATE_DIR}"
cd "${PRIVATE_DIR}"

# Make a new self-signed CA certificate and key. pathlen:0 lets it sign
# server certificates but not intermediate CAs.
openssl req -x509 -new -noenc -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -keyout ca.key -out ca.crt -days "${DAYS}" \
    -subj "/CN=QFw ibmsim-runtime test CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null

# Create the server key and certificate signing request (CSR)
openssl req -new -noenc -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -keyout server.key -out server.csr -subj "/CN=ibmsim-runtime" 2>/dev/null

# Add server certificate extensions
cat > server.ext <<EXT
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=serverAuth
subjectAltName=${SAN}
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EXT
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -days "${DAYS}" \
    -extfile server.ext -out server.crt 2>/dev/null
rm -f ca.key server.csr server.ext

# Replace the published copy in one rename, so a client never reads half a file.
umask 022
mkdir -p "$(dirname "${CA_OUT}")"
cp ca.crt "${CA_OUT}.tmp.$$"
chmod 644 "${CA_OUT}.tmp.$$"
mv -f "${CA_OUT}.tmp.$$" "${CA_OUT}"

echo "ibmsim-runtime: TLS certificate for ${SAN}; CA published to ${CA_OUT}"
