# Deploying the paper daemon to DigitalOcean

This runs `paper_trader.py` continuously on a small Droplet under `systemd`, so
it keeps watching followed wallets and logging paper fills 24/7.

**Scope / safety.** This deploys the *paper* daemon only. It holds **no private
keys and signs nothing** — consistent with the project's zero-capital rule. The
only secret on the server is your free Helius API key. Don't add wallet keys to
this box.

**What you need:** a DigitalOcean account, an SSH key added to it, and your free
[Helius](https://helius.dev) API key.

---

## Sizing & cost

The daemon is one lightweight Python process polling a few HTTP APIs every ~15s.
The smallest Droplet is plenty:

- **Basic / Regular, 1 vCPU, 512 MB–1 GB RAM** (~$4–6/mo).
- Ubuntu 24.04 LTS.
- Pick a region near you for lower SSH latency (trade latency is irrelevant —
  this is paper trading).

---

## Fast path (cloud-init)

1. **Create the Droplet.** Control panel → Create → Droplets → Ubuntu 24.04,
   Basic plan, cheapest tier. Under **Advanced options → Add Initialization
   scripts (user data)**, paste the entire contents of
   [`cloud-init.yaml`](cloud-init.yaml). Add your SSH key. Create.

2. **Push the code** from your laptop (repo root), once the Droplet is up:

   ```bash
   deploy/sync.sh root@<DROPLET_IP>
   ```

   This rsyncs the project to `/opt/beerfund` (excluding secrets, caches, and
   local state) and runs `setup.sh` on the box.

3. **Set your key and start it:**

   ```bash
   ssh root@<DROPLET_IP>
   nano /etc/beerfund/beerfund.env      # set HELIUS_API_KEY and WALLETS
   systemctl start beerfund-paper
   journalctl -u beerfund-paper -f      # watch the loop
   ```

Done. The service auto-starts on reboot and restarts on crash.

---

## Manual path (no cloud-init)

If you'd rather create a plain Droplet and do it by hand:

```bash
# from the repo root, after the Droplet exists:
deploy/sync.sh root@<DROPLET_IP>           # copies code + runs setup.sh
ssh root@<DROPLET_IP>
nano /etc/beerfund/beerfund.env            # add HELIUS_API_KEY + WALLETS
systemctl start beerfund-paper
```

`setup.sh` is idempotent — it installs python3, creates the `beerfund` system
user, makes `data/` and `results/` writable, installs the systemd unit, and
enables it. Re-running it after a code push is safe.

---

## Day-to-day

```bash
systemctl status beerfund-paper          # is it up?
journalctl -u beerfund-paper -f          # live log (entries/exits/closes)
journalctl -u beerfund-paper --since today
systemctl restart beerfund-paper         # after editing the env file
systemctl stop beerfund-paper            # sends SIGINT; state is saved first
```

**Ship a code change:** re-run `deploy/sync.sh root@<IP>` from your laptop — it
syncs, re-runs setup, and restarts the service. Your `state.json` and
`paper_trades.csv` on the server are excluded from the sync, so they survive.

**Pull the results back** for analysis:

```bash
scp root@<DROPLET_IP>:/opt/beerfund/results/paper_trades.csv ./results/
scp root@<DROPLET_IP>:/opt/beerfund/data/paper/state.json ./data/paper/
```

**Change followed wallets or tuning:** edit `WALLETS` / `PAPER_*` in
`/etc/beerfund/beerfund.env`, then `systemctl restart beerfund-paper`. Note the
daemon arms on each wallet's *latest* tx at start — it never replays history, so
a newly added wallet only triggers on its next buy.

---

## Files in this directory

| file | purpose |
|---|---|
| `cloud-init.yaml` | One-shot Droplet provisioning (user-data at create time) |
| `setup.sh` | Idempotent provisioner run on the Droplet (python, user, dirs, unit) |
| `sync.sh` | Local helper: rsync code to the Droplet + re-provision + restart |
| `beerfund-paper.service` | The systemd unit (hardened; only `data/`+`results/` writable) |
| `beerfund.env.example` | Template for `/etc/beerfund/beerfund.env` (secrets live here) |

---

## Troubleshooting

- **`systemctl start` fails immediately** → `journalctl -u beerfund-paper -n 50`.
  Usually `HELIUS_API_KEY not set` (env file not filled in) or `no wallets given`
  (empty `WALLETS`).
- **`ReadWritePaths` / read-only filesystem errors** → the unit only allows
  writes to `/opt/beerfund/data` and `/opt/beerfund/results`. Make sure both
  exist and are owned by `beerfund` (setup.sh handles this).
- **Helius 401/429** → bad or rate-limited key; the daemon logs a warning per
  failed call and keeps looping rather than crashing.
- **Nothing ever enters** → expected when followed wallets are quiet, or their
  buys are below `PAPER_MIN_SIGNAL`, or pools are too thin (impact > 8% is
  skipped by design). Watch the `open=/closed=/skipped=` heartbeat line.
