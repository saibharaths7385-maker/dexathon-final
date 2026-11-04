# Encrypted Local Storage

SKYNEX stores V2 engine checkpoints, telemetry history, mission snapshots, fault
history, recommendations, and operator decisions in the SQLCipher database
configured by `TWIN_DATABASE`.

The backend uses `sqlcipher3==0.6.4`, which bundles SQLCipher 4.x for supported
Windows Python environments. The application does not fall back to standard
SQLite when encryption is enabled.

## Windows setup

Set the key in the Laptop 2 server process environment. Do not place it in Git,
the frontend environment, `.env.example`, source code, logs, or command output.
For local development, Windows Credential Manager or a managed deployment
secret provider is preferable. If an environment variable is used, it is
visible to processes and administrators that can inspect that process
environment.

```powershell
$env:TWIN_DATABASE = "data\twin.sqlite3"
$env:TWIN_DATABASE_ENCRYPTION_REQUIRED = "true"
$env:TWIN_DATABASE_KEY = "<set-a-long-random-secret-outside-the-repository>"
python -m uvicorn backend.api.main:api --host 127.0.0.1 --port 8000
```

Never print the key. Use a securely generated random value and keep a
protected recovery copy. Key loss cannot be recovered by the application.

## Verification

The backend validates the SQLCipher connection before creating or reading
tables. A missing or incorrect key causes startup/storage failure. A normal
Python `sqlite3` connection cannot read an encrypted database.

## Migrating an existing plaintext database

Migration is explicit and creates a separate destination. It never deletes or
overwrites the source:

```powershell
python -m backend.twin.storage_migration `
  --source data\twin.sqlite3 `
  --destination C:\Protected\SKYNEX\twin-encrypted.sqlite3
```

The migration command requires the key through `TWIN_DATABASE_KEY` and verifies
source integrity, schema, record counts, destination integrity, and source
immutability. Test the destination before changing `TWIN_DATABASE` and obtain
owner approval before replacing the runtime database.

## Backup and restore

Backups must be created with the encrypted SQLite backup API after committed
WAL data is included. Do not copy only the main database file while writes are
active. Store backups outside Git and public frontend directories, restrict
access, and apply an operational retention policy.

```powershell
python -m backend.twin.storage_backup backup `
  --source data\twin.sqlite3 `
  --destination C:\Protected\SKYNEX\backups\twin-backup.sqlite3

python -m backend.twin.storage_backup restore `
  --source C:\Protected\SKYNEX\backups\twin-backup.sqlite3 `
  --destination C:\Protected\SKYNEX\restore-check\twin.sqlite3
```

Restoration always targets a separate destination. Verify the restored database
with the correct key before any controlled deployment change. The SQLite
`-shm` file is coordination metadata and is not claimed to be encrypted.

## Key rotation and recovery

Changing `TWIN_DATABASE_KEY` does not rotate an existing database key. Perform a
controlled SQLCipher rekey or encrypted-copy migration into a new destination,
verify it, and retain the original protected backup until acceptance.

If the key is missing or incorrect, the service fails closed. If the key is
lost, recovery requires a protected backup of the key and an intact encrypted
database/backup. Database encryption does not replace HTTPS/WSS, authentication,
authorization, or Windows volume encryption.

## Troubleshooting

- `TWIN_DATABASE_KEY is required`: set the key in the server process environment.
- `Unable to open encrypted database`: verify the key and SQLCipher version.
- Integrity failure: stop writes and restore only from a verified protected backup.
- Existing plaintext database: migrate explicitly; do not disable encryption in
  the production server.
