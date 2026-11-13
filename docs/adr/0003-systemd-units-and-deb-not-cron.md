# Ship as systemd units in a .deb, not a cron job

The tool is delivered as a Debian package that installs and enables systemd units, rather than a
Python package scheduled by cron. The .deb owns the unit files, the config directory, and the
credential location. A path unit reacts to newly appearing conflict files, and a low-frequency
timer re-scans as a safety net for files that appeared while the service was down.

We chose systemd over cron because file-watch immediacy matches the "a sync-conflict file just
appeared" trigger, and systemd-creds integrates directly with unit credentials. The .deb follows
from wanting systemd units installed and enabled by a package manager.
