# SuddWatch — Pipeline Scheduling Setup

This document explains how to schedule the SuddWatch flood detection
pipeline to run automatically every 12 hours on macOS (development)
and Linux (production server).

---

## Overview

The pipeline runs `run_pipeline.py` which:
1. Checks for new Sentinel-1 scenes over the Sudd Basin
2. Downloads and preprocesses any new scenes
3. Runs flood detection and risk assessment
4. Sends SMS + email alerts if thresholds are exceeded
5. Logs all results to the SQLite database

**Recommended schedule:** Every 12 hours (Sentinel-1 revisit time is ~6–12 days,
but running more frequently ensures new scenes are caught promptly).

---

## macOS — launchd (Recommended for Development)

launchd is macOS's native scheduler. It is more reliable than cron on macOS
because it respects sleep/wake cycles and restarts missed jobs.

### Step 1: Create the plist file

```bash
cat > ~/Library/LaunchAgents/com.suddwatch.pipeline.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.suddwatch.pipeline</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/billawan/suddwatch/venv/bin/python</string>
        <string>/Users/billawan/suddwatch/run_pipeline.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/billawan/suddwatch</string>

    <!-- Run every 12 hours (43200 seconds) -->
    <key>StartInterval</key>
    <integer>43200</integer>

    <!-- Also run once immediately when loaded -->
    <key>RunAtLoad</key>
    <false/>

    <!-- Log stdout and stderr -->
    <key>StandardOutPath</key>
    <string>/Users/billawan/suddwatch/logs/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/billawan/suddwatch/logs/launchd_stderr.log</string>

    <!-- Restart if it crashes -->
    <key>KeepAlive</key>
    <false/>

    <!-- Environment variables -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/Users/billawan/suddwatch/venv/bin</string>
    </dict>
</dict>
</plist>
EOF
```

### Step 2: Create the logs directory

```bash
mkdir -p ~/suddwatch/logs
```

### Step 3: Load the job

```bash
launchctl load ~/Library/LaunchAgents/com.suddwatch.pipeline.plist
```

### Step 4: Verify it loaded

```bash
launchctl list | grep suddwatch
```

You should see `com.suddwatch.pipeline` in the output.

### Step 5: Run it manually once to test

```bash
launchctl start com.suddwatch.pipeline
```

Then check the logs:

```bash
tail -f ~/suddwatch/logs/launchd_stdout.log
```

### To stop/unload

```bash
launchctl unload ~/Library/LaunchAgents/com.suddwatch.pipeline.plist
```

---

## Linux / macOS — cron (Alternative)

If you prefer cron, add the following entry using `crontab -e`:

```cron
# SuddWatch flood detection pipeline — every 12 hours
0 */12 * * * cd /Users/billawan/suddwatch && \
    /Users/billawan/suddwatch/venv/bin/python run_pipeline.py \
    >> /Users/billawan/suddwatch/logs/pipeline.log 2>&1
```

**Important for macOS cron:** Grant cron Full Disk Access in
System Preferences → Security & Privacy → Privacy → Full Disk Access.

---

## Linux Production Server (Ubuntu)

For a production deployment on a Linux server, use systemd:

### Create the service file

```bash
sudo cat > /etc/systemd/system/suddwatch-pipeline.service << 'EOF'
[Unit]
Description=SuddWatch Flood Detection Pipeline
After=network.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/suddwatch
ExecStart=/home/ubuntu/suddwatch/venv/bin/python run_pipeline.py
StandardOutput=append:/home/ubuntu/suddwatch/logs/pipeline.log
StandardError=append:/home/ubuntu/suddwatch/logs/pipeline.log

[Install]
WantedBy=multi-user.target
EOF
```

### Create the timer file

```bash
sudo cat > /etc/systemd/system/suddwatch-pipeline.timer << 'EOF'
[Unit]
Description=Run SuddWatch pipeline every 12 hours
Requires=suddwatch-pipeline.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=12h
Unit=suddwatch-pipeline.service

[Install]
WantedBy=timers.target
EOF
```

### Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable suddwatch-pipeline.timer
sudo systemctl start suddwatch-pipeline.timer
sudo systemctl status suddwatch-pipeline.timer
```

---

## Testing the Schedule

### Process one local scene without sending alerts

```bash
python run_pipeline.py --scene data/raw/S1A_IW_GRDH_....zip --no-alerts
```

### Dry run (no downloads, just connectivity check)

```bash
cd ~/suddwatch && source venv/bin/activate
python run_pipeline.py --dry-run
```

### Manual run with verbose logging

```bash
python run_pipeline.py --verbose
```

### Check today's log

```bash
tail -100 ~/suddwatch/logs/pipeline_$(date +%Y%m%d).log
```

### Check pipeline results JSON

```bash
ls -lt ~/suddwatch/logs/results_*.json | head -5
cat ~/suddwatch/logs/results_$(ls -t ~/suddwatch/logs/results_*.json | head -1 | xargs basename)
```

---

## Log Rotation

To prevent logs from growing indefinitely, add log rotation:

```bash
cat > /etc/logrotate.d/suddwatch << 'EOF'
/Users/billawan/suddwatch/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
EOF
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError` | Wrong Python path | Use full venv path: `venv/bin/python` |
| `No new scenes` | No new Sentinel-1 passes | Normal — check again in 6 days |
| SMS not delivered | Twilio geo permissions | Enable Kenya in Twilio console |
| Email timeout | Port 587 blocked | Confirmed using port 465 SSL |
| Raw scenes fail at preprocessing | SNAP GPT not found | Install SNAP, or set `SNAP_GPT_PATH` in `.env` |
| Dashboard still shows "DEMO DATA" | No completed event with a flood mask yet | Run the pipeline once; also run `python scripts/clean_test_data.py --apply` to remove old test rows |
| A downloaded scene was never processed | Run crashed after download (scene is in the registry) | Re-run it directly: `python run_pipeline.py --scene data/raw/<scene>.zip` |
| DB locked | Concurrent pipeline runs | Only one instance should run at a time |

---

## Environment Variables Required

All credentials must be set in `.env` at the project root.
See `.env.example` for the full list. Key variables:

```
COPERNICUS_USER=your_copernicus_email
COPERNICUS_PASSWORD=your_copernicus_password
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx
SMTP_USER=your_gmail@gmail.com
SMTP_PASSWORD=your_gmail_app_password
SMS_RECIPIENTS=+211921000001,+211921000002
EMAIL_RECIPIENTS=coord@ocha.org
```

**Never commit `.env` to git.** It is already listed in `.gitignore`.
