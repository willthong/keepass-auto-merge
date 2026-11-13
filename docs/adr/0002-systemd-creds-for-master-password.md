# Store the master password with systemd-creds

The master password shared by all databases is encrypted with `systemd-creds encrypt` into
`/etc/credstore.encrypted/`, and the service reads it at runtime via `LoadCredentialEncrypted=` (exposed
as `$CREDENTIALS_DIRECTORY/...`). The password never appears in a config file, an environment
file, or the unit file.

We chose this because the service runs as a systemd unit, so host-credential encryption
(TPM2-backed where available) is native and decrypts without any unlocked keyring or GPG agent.
We rejected `pass` and Secret Service: both require an agent that is typically locked in a
headless service context.
