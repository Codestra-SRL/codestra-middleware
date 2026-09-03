# Mesh-key rotation

1. Generate a new per-source ED25519 identity with a dated comment.
2. Keep the private file root-owned mode 0600 and the `.ssh` directory mode 0700.
3. Verify the new public-key fingerprint out of band.
4. Install the new public key beside the old key with exact source and
   forwarding restrictions.
5. Test every authorized destination with `IdentitiesOnly=yes`, batch mode, and
   strict host checking.
6. Remove the old public key on each destination.
7. Prove the old identity fails and the new identity succeeds.
8. Shred the retired private file only after rollback and access evidence is
   preserved.

Application mTLS/HMAC, deployment, backup, and repository credentials must
never be reused as mesh SSH identities.
