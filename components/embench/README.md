# Embench-IoT component

`manifests/components.lock.toml` pins the upstream source used by the
ML-032a functional sweep.

The one-patch series makes the MD5 implementation decode its input and length
using MD5's specified little-endian byte order.  The upstream code used native
`uint32_t` loads and stores and documented its expected value as generated on
x86; it therefore failed unchanged on big-endian DADAO in both QEMU and gem5.
The patch does not change the benchmark input or expected result.

Target-specific board support belongs to this repository under
`tests/embench/`, not in the upstream checkout.
