# Deployment example

This is an example, not a prescription. Replace every placeholder in angle brackets.

## Application

Create a system user `evidiff` with home `/var/lib/evidiff` (mode 0700), then:

```sh
git clone <repository URL> /opt/evidiff && cd /opt/evidiff
uv sync --frozen --no-dev
```

Put the environment in `/etc/evidiff/evidiff.env` (mode 0600, owned by root), starting
from `.env.example`. Keep `SECRET_KEY` out of version control. Outside preview mode
`PAIR_FILE` must name the study package; the repository ships only preview pairs.

## Service (systemd)

```ini
[Unit]
Description=evidiff
After=network.target

[Service]
User=evidiff
Group=evidiff
WorkingDirectory=/opt/evidiff
EnvironmentFile=/etc/evidiff/evidiff.env
ExecStart=/opt/evidiff/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 'app:create_app()'
ExecReload=/bin/kill -HUP $MAINPID
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/evidiff
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`systemctl reload` sends HUP: gunicorn starts new workers on the new code while the
old ones finish their requests, so a deploy does not drop submissions. The browser
script also resends a form that meets a gateway error.

## Reverse proxy (nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name <your host name>;
    ssl_certificate     <certificate path>;
    ssl_certificate_key <key path>;
    client_max_body_size 32k;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

The application trusts exactly one proxy hop for the client address and scheme
(`ProxyFix(x_for=1, x_proto=1)`). If another proxy or a CDN sits in front, make sure
`X-Forwarded-For` still carries the client address after one hop.

## Operations

- `flask --app 'app:create_app()' status` reports progress without personal data.
- `flask --app 'app:create_app()' close --reason "..."` closes collection.
- `flask --app 'app:create_app()' snapshot-db --at <ISO instant> --output <new dir>`
  captures a consistent copy of the database.
- See `docs/private-export-operations.md` for the export used in the analysis.
- Back up `/var/lib/evidiff` regularly; it holds personal data.
