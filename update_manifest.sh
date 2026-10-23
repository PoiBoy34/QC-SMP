#!/usr/bin/env bash
# Régénère les manifests (nom, URL et sha1 de chaque fichier) que lit le launcher,
# à partir de modrinth.lock.json et des fichiers déposés à la main dans modpacks/<pack>/.
# Met aussi à jour servers.dat et le defaults_sha1 du catalog.json.
set -euo pipefail
cd "$(dirname "$0")"
python3 outils/manifests.py
