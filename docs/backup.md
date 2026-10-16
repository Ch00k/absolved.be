# Backing up the database

## What is backed up

One file: `/app/data/db.sqlite3`, on the Fly volume `absolved_data` (`vol_r1jg2xgxjm9dwq3r`, region `fra`). Nothing else on the volume or in the image needs
keeping.

It holds usernames, the hashes of login keys, confession dates, and examinations as ciphertext. Restoring needs no
secret of the app's: `DJANGO_SECRET_KEY` only signs sessions, so a restore under a new one logs everyone out and
loses nothing else.

## Retention: 30 days

The app promises that recording a confession, or deleting the account, deletes the data for good, and the privacy
text says the backups forget it within a month. So every copy expires:

| Where                      | How long                                                                   |
| -------------------------- | -------------------------------------------------------------------------- |
| Fly volume snapshots       | 5 days, Fly's default                                                      |
| Tigris                     | 30 days, by the bucket's lifecycle rule (rounded to the next UTC midnight) |
| Storage Box                | 30 days, pruned by the workflow after each upload                          |
| Storage Box snapshots      | 2 days more, the most the BX10 keeps                                       |

Whatever is deleted is gone from all of them within 32 days. Raising any of these breaks the promise in
`absolved/templates/absolved/_privacy.html` and the account page.

## The daily copy

`.github/workflows/backup.yml` runs at 03:17 UTC. It needs the GitHub repository, which does not exist yet; until it
does, only Fly's snapshots back anything up.

1. `manage.py backup_database` writes a copy with `VACUUM INTO`, which is safe against the live database and produces
   one self-contained file even in WAL mode. It runs as the app's user: an SSH session is root, and a root process
   that opens the database can leave its `-wal` and `-shm` files owned by root, which the app then cannot write.
2. The runner fetches it with `fly sftp get`, checks `pragma integrity_check` and that `django_migrations` is
   populated, gzips it, and encrypts it with [age](https://github.com/FiloSottile/age) to a public key. The private
   key is in the password store, as `other/absolved.be_backup_key`, and nowhere else, so neither storage provider can read usernames or confession
   dates. The encryption runs on the runner; the Fly machine only runs `VACUUM INTO`.
3. It uploads `db-<UTC timestamp>.sqlite3.gz.age` to both destinations, deletes Storage Box copies older than 30
   days, and removes the copy from the volume, whether or not the rest worked.

### Tigris

`s3://app-backups/absolved/database/`, at `https://fly.storage.tigris.dev`, the bucket WAD backs up to, under its own
prefix. The workflow's key may only put objects there:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "s3:PutObject", "Resource": "arn:aws:s3:::app-backups/absolved/database/*" }
  ]
}
```

A leaked key cannot read the backups or delete them. The lifecycle rule that expires them belongs to the bucket, set
with the owner's credentials.

### The Storage Box

A sub-account of its own, whose home directory, `app_backups/absolved`, is where the copies land, reached by `rsync` over port 23 (the
Storage Box's SSH service; port 22 speaks only SCP and SFTP). Unlike the Tigris key it can delete what is in its
directory, which the pruning needs and a leaked key could abuse; the box's snapshots, which belong to the main
account, cover the two days after that.

### Secrets

Every one is in the password store, under `absolved/`, until the repository exists and they are set on it.

| Secret                     | From the password store                                   | What it is                                                     |
| -------------------------- | --------------------------------------------------------- | -------------------------------------------------------------- |
| `FLY_SSH_TOKEN`            | `absolved/fly-ssh-token`                                  | `fly tokens create ssh -a absolved --name backup-workflow`     |
| `TIGRIS_ACCESS_KEY_ID`     | `absolved/tigris-backup-key`, its `access_key_id:` line    | The key `absolved-backup-workflow`, with the policy above only |
| `TIGRIS_SECRET_ACCESS_KEY` | `absolved/tigris-backup-key`, its first line              | Its secret half                                                |
| `STORAGE_BOX_SSH_KEY`      | `absolved/storage-box-ssh-key`                            | The key the sub-account accepts                                |
| `STORAGE_BOX_KNOWN_HOSTS`  | `absolved/storage-box-known-hosts`                        | The box's host keys, pinned rather than trusted on sight       |
| `STORAGE_BOX_HOST`         | none                                                      | `uXXXXXX-subN@uXXXXXX.your-storagebox.de`; a secret only because the repository is public and the name carries the account number |

The age key that decrypts the backups is `other/absolved.be_backup_key`; the workflow carries its public half, which is not
a secret. A failed run emails the repository owner, which is the only alarm there is. Actions cron is best-effort and
can run an hour or more late. The repository is public, and GitHub disables the schedule of a public repository after
60 days without a commit, with an email first; a quiet two months would otherwise stop the backups silently.

## Setting it up

Done:

- **The age key**, generated into the password store; nothing else holds it.
- **The Tigris policy** `absolved-backup-write` and the key `absolved-backup-workflow`, which has no bucket role and
  that policy alone. Tried: it can put an object under `absolved/database/`, and cannot read, list or delete one, nor
  write anywhere else.
- **The lifecycle rule** on `app-backups`: objects under `absolved/database/` expire after 30 days. WAD's copies in the
  same bucket have no rule and keep forever.
- **The Fly SSH token**, for the app alone; it cannot deploy.
- **The Storage Box directory** `app_backups/absolved`, laid out as WAD's, with the backup key already in its
  `.ssh/authorized_keys`, and the box's host keys recorded. Automatic snapshots were already on for the box.
- **Fly's volume snapshots**: on for `vol_r1jg2xgxjm9dwq3r`, kept 5 days.
- **The Storage Box sub-account**, with `app_backups/absolved` as its home directory, SSH support and external
  reachability. Tried with the workflow's key and pinned host keys: rsync uploads, `ls` lists and `rm` removes.
- **The secrets**, on the repository, from the password store:

  ```bash
  pass show absolved/fly-ssh-token | gh secret set FLY_SSH_TOKEN
  pass show absolved/tigris-backup-key | sed -n 's/^access_key_id: //p' | gh secret set TIGRIS_ACCESS_KEY_ID
  pass show absolved/tigris-backup-key | head -1 | gh secret set TIGRIS_SECRET_ACCESS_KEY
  pass show absolved/storage-box-ssh-key | gh secret set STORAGE_BOX_SSH_KEY
  pass show absolved/storage-box-known-hosts | gh secret set STORAGE_BOX_KNOWN_HOSTS
  printf '%s' "uXXXXXX-subN@uXXXXXX.your-storagebox.de" | gh secret set STORAGE_BOX_HOST
  ```

Left, in this order:

1. **The code on the repository's default branch**, which is where a schedule runs from, and **a deploy**, so the
   image has `backup_database`.
2. **Run it by hand and watch it:** `gh workflow run backup.yml`, then `gh run watch`. The same filename in
   `tigris ls t3://app-backups/absolved/database/` and in the sub-account's `ls` is the setup confirmed.
3. **Restore one, on purpose**, as below, before the day it matters.

## Restore

Restoring replaces the database the app serves, so the app comes off it first: the machine stays up, since SSH needs
it, with a command that serves nothing. Whatever was written after the copy was taken is lost. `fly machine list -a
absolved` gives the machine ID.

### From a Fly snapshot

Restoring a snapshot creates a new volume, which needs a new machine:

```bash
fly volumes snapshots list vol_r1jg2xgxjm9dwq3r
fly volumes create absolved_data --snapshot-id <snapshot-id> --region fra --size 1 -a absolved
fly machine cordon <machine-id> -a absolved
fly machine stop <machine-id> -a absolved
fly machine clone <machine-id> --attach-volume <new-volume-id>:/app/data --override-cmd "sleep inf" -a absolved
```

Check it (below), then `fly machine update <new-machine-id> --command /app/run.sh --yes -a absolved` and destroy the
old machine. Keep the old volume until the restore has proved itself.

### From a daily copy

Fetch one, from Tigris with a key that can read the prefix (not the workflow's), or from the Storage Box:

```bash
aws s3 cp s3://app-backups/absolved/database/db-<timestamp>.sqlite3.gz.age . --endpoint-url https://fly.storage.tigris.dev
rsync -e "ssh -p 23" uXXXXXX@uXXXXXX.your-storagebox.de:app_backups/absolved/db-<timestamp>.sqlite3.gz.age .
```

Decrypt it with the key from the password store, take the app off the database, and swap the copy in, removing the
WAL sidecars, which would corrupt the copy on reopen. The upload arrives owned by root, and the app's user has to be
able to write it.

```bash
age --decrypt --identity <(pass show other/absolved.be_backup_key) db-<timestamp>.sqlite3.gz.age | gunzip > restore.sqlite3
fly machine update <machine-id> --command "sleep inf" --yes -a absolved
fly sftp put restore.sqlite3 /app/data/import.sqlite3 -a absolved
fly ssh console -a absolved -C "sh -c 'rm -f /app/data/db.sqlite3 /app/data/db.sqlite3-wal /app/data/db.sqlite3-shm && mv /app/data/import.sqlite3 /app/data/db.sqlite3 && chown absolved:absolved /app/data/db.sqlite3'"
```

Check it, then give the machine its command back: `fly machine update <machine-id> --command /app/run.sh --yes -a
absolved`. Delete `restore.sqlite3` from the laptop.

### Checking a restore

The image has no `sqlite3` CLI:

```bash
fly ssh console -a absolved -C "/app/.venv/bin/python -c \"import sqlite3; c=sqlite3.connect('/app/data/db.sqlite3'); print(c.execute('pragma integrity_check').fetchone()); print(c.execute('select count(*) from absolved_user').fetchone())\""
```

## Why not Litestream

Litestream would lose seconds in a disaster where this loses up to a day, but since 0.5 it replicates each database
to one destination only, so the Storage Box would still need this job; and its storage key, which must be able to
read and delete, would live in the app machine. A day of autosaves and signups is what is at stake here.
