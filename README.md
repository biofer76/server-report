# server-report

A lightweight Python script that collects system metrics from a Linux Server and sends a periodic status report via email using the Mailgun API.

No external dependencies. Pure Python standard library only.

## Features

- CPU usage and load average
- RAM and swap usage
- Disk usage for all relevant partitions
- Top 5 processes by CPU and RAM
- Network summary
- Recent SSH logins
- Failed systemd services
- Recent error logs (last 24h)
- Available apt updates
- Automatic alerts for disk, RAM, CPU thresholds
- `--dry-run` mode for previewing the report without sending

## Project structure

```
server_report/
├── config.py    # all configuration (SMTP, thresholds)
├── metrics.py   # system metrics collection
├── alerts.py    # alert threshold logic
├── report.py    # report body composition
├── mailer.py    # email sending via Mailgun API
└── main.py      # entry point and CLI arguments
```

## Setup

**1. Clone the repository**

```bash
git clone https://github.com/your-username/server-report.git
cd server-report
```

**2. Configure**

Copy the example config and fill in your values:

```bash
cp config.example.py config.py
```

Edit `config.py` with your Mailgun credentials and alert thresholds.

**3. Get a Mailgun API key**

- Sign up at [mailgun.com](https://www.mailgun.com)
- Add and verify your sending domain
- Copy your API key from **Settings > API Security**
- If your domain is in the EU region, set `MAILGUN_API_URL` to `https://api.eu.mailgun.net/v3`

**4. Test**

```bash
python3 main.py --dry-run
```

**5. Schedule with cron**

```bash
crontab -e
```

Add a line, for example to run every day at 8:00 AM:

```
0 8 * * * /usr/bin/python3 /path/to/server-report/main.py >> /var/log/server_report.log 2>&1
```

## Usage

```bash
# Preview report in terminal (no email sent)
python3 main.py --dry-run

# Send report to the configured recipient
python3 main.py

# Override recipient address
python3 main.py --to other@email.com
```

## Requirements

- Python 3.10+
- Linux (tested on Debian/Ubuntu)
- A Mailgun account with a verified sending domain

## License

[MIT](https://raw.githubusercontent.com/biofer76/server-report/refs/heads/main/LICENSE)
