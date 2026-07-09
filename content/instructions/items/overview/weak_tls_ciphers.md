# Weak TLS Ciphers

This item reports weak or medium-strength cipher classes allowed by `ssl_ciphers`.

## What this item shows
- Current `ssl_ciphers` value.
- Cipher classes that allow weak, anonymous, export, or medium-strength classes.
- Risk level for each class.

## Checklist
- Remove weak cipher classes such as `LOW`, `EXP`, `NULL`, `MD5`, `RC4`, `DES`, and `3DES`.
- Prefer a policy that allows only modern strong ciphers.
- Test client compatibility after tightening TLS ciphers.
