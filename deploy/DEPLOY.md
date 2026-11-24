# Putting TradingAgent online

This runs the dashboard on a small cloud server with HTTPS. Anyone with the link sees the
**Stocks** screen (charts from Yahoo). Only you, with the owner password, see the robot,
its trades and Zerodha.

## 1. Rent a server (you do this)

Any Ubuntu 22.04 or 24.04 server with 1 GB of memory is enough, for example DigitalOcean,
AWS Lightsail, Hetzner or Oracle Cloud. Pick a region in India (Mumbai) for speed, and make
sure the plan gives a **static IP** (Lightsail and DigitalOcean: attach a static/reserved IP).

## 2. Run the setup script

Log in with SSH, then:

```bash
curl -fsSLO https://raw.githubusercontent.com/hemanthsamudrala55/TradingAgent/main/deploy/setup.sh
sudo bash setup.sh                 # no domain: uses <your-ip>.sslip.io
sudo bash setup.sh trade.example.com   # or with your own domain (point its A record at the IP first)
```

It installs Python and Caddy, copies the app to `/opt/tradingagent`, gets an HTTPS
certificate, and opens only ports 22, 80 and 443.

## 3. Set your password and start

```bash
cd /opt/tradingagent && sudo -u trader .venv/bin/python -m web.set_password
sudo systemctl start tradingagent
```

The password needs at least 12 characters. Only a hash is stored, in `/opt/tradingagent/.env`.
The app refuses to start without it. Five wrong tries lock logins from that address for 15 minutes.

## 4. Zerodha (only if you want the robot on the server)

- **Static IP:** since 1 April 2026 Zerodha accepts API orders only from an IP you register.
  Add the server IP in your Kite developer console (developers.kite.trade, your app's settings).
- **Redirect URL:** set it to `https://<your-address>/kite/callback`.
- **Keys:** add `KITE_API_KEY=...` and `KITE_API_SECRET=...` to `/opt/tradingagent/.env`
  yourself (`sudo -u trader nano /opt/tradingagent/.env`), then `sudo systemctl restart tradingagent`.
- Zerodha's login lasts one trading day. Log in from the Robot tab each morning.

Visitors never see Zerodha data; Zerodha's terms do not allow showing it to others.

## Everyday commands

```bash
sudo systemctl status tradingagent          # is it running?
sudo journalctl -u tradingagent -n 100      # recent logs
cd /opt/tradingagent && sudo -u trader git pull && sudo systemctl restart tradingagent   # update
```
