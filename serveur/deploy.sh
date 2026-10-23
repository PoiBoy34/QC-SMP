#!/usr/bin/env bash
# Déploie tout le réseau Minecraft sur Proxmox, depuis ton PC (Linux, macOS ou WSL).
#
#   ./deploy.sh                    tout : clés SSH, VM, sécurité, Docker, serveurs
#   ./deploy.sh --tags serveur     reconfigurer seulement la VM (après un changement de config.yml)
#
# Relançable autant de fois que tu veux : rien n'est recréé ni écrasé si c'est déjà en place.
set -euo pipefail
source "$(dirname "$0")/lib/commun.sh"
cd "$RACINE"

# --- 0. Vérifications --------------------------------------------------------
ip_valide "$PROXMOX_IP" || erreur "proxmox_ip invalide dans config.yml : « $PROXMOX_IP »"
ip_valide "$VM_IP"      || erreur "vm_ip invalide dans config.yml : « $VM_IP »"
[[ $PROXMOX_IP != "$VM_IP" ]] || erreur "proxmox_ip et vm_ip doivent être différentes"

for outil in ssh ssh-keygen ssh-copy-id; do
  command -v "$outil" >/dev/null || erreur "« $outil » est introuvable (paquet openssh-client)"
done
if ! command -v ansible-playbook >/dev/null; then
  erreur "Ansible n'est pas installé. Au choix :
    Debian/Ubuntu/WSL : sudo apt install ansible
    macOS             : brew install ansible
    partout           : pipx install --include-deps ansible"
fi

# --- 1. Clé SSH dédiée au projet ---------------------------------------------
if [[ ! -f $CLE ]]; then
  info "Création de la clé SSH $CLE"
  mkdir -p "$(dirname "$CLE")" && chmod 700 "$(dirname "$CLE")"
  ssh-keygen -q -t ed25519 -a 100 -N "" -C "mc-homelab $(whoami)@$(hostname)" -f "$CLE"
  ok "clé créée (ajoute une phrase de passe plus tard avec : ssh-keygen -p -f $CLE)"
else
  ok "clé SSH existante : $CLE"
fi

# --- 2. Clé installée sur l'hôte Proxmox -------------------------------------
if ssh "${SSH_OPTS[@]}" -o BatchMode=yes "root@$PROXMOX_IP" true 2>/dev/null; then
  ok "accès par clé à Proxmox ($PROXMOX_IP)"
else
  info "Copie de la clé sur Proxmox : entre le mot de passe root de Proxmox (une seule fois)"
  ssh-copy-id -i "$CLE.pub" -o StrictHostKeyChecking=accept-new "root@$PROXMOX_IP"
  ssh "${SSH_OPTS[@]}" -o BatchMode=yes "root@$PROXMOX_IP" true \
    || erreur "la connexion par clé à Proxmox ne marche toujours pas"
  ok "clé installée sur Proxmox"
fi

# --- 3. Ansible : VM + configuration -----------------------------------------
info "Lancement d'Ansible (le premier déploiement prend 10 à 20 minutes)"
SECRETS=()
[[ -f secrets.yml ]] && SECRETS=(-e @secrets.yml)
ansible-playbook site.yml -e @config.yml ${SECRETS[@]+"${SECRETS[@]}"} -e "ssh_key=$CLE" "$@"

# --- 4. Raccourcis « ssh mc » et « ssh mc-proxmox » ---------------------------
SSH_CONFIG="$HOME/.ssh/config"
touch "$SSH_CONFIG" && chmod 600 "$SSH_CONFIG"
sed -i.bak '/^# >>> mc-homelab/,/^# <<< mc-homelab/d' "$SSH_CONFIG" && rm -f "$SSH_CONFIG.bak"
cat >>"$SSH_CONFIG" <<EOF
# >>> mc-homelab (géré par deploy.sh)
Host mc
  HostName $VM_IP
  User $VM_USER
  IdentityFile $CLE
  IdentitiesOnly yes
Host mc-proxmox
  HostName $PROXMOX_IP
  User root
  IdentityFile $CLE
  IdentitiesOnly yes
# <<< mc-homelab
EOF
ok "raccourcis ajoutés : « ssh mc » (la VM) et « ssh mc-proxmox » (l'hôte)"
