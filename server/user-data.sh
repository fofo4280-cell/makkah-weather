#!/bin/bash
# Paste this whole text into the "Cloud config" box when creating the server.
exec > /var/log/swrf-bootstrap.log 2>&1
export DEBIAN_FRONTEND=noninteractive
apt-get update -q && apt-get install -y -q git
git clone --single-branch --depth 30 --branch saudi-wrf https://github.com/Fofo4280-cell/makkah-weather /opt/swrf/repo
bash /opt/swrf/repo/server/install.sh
