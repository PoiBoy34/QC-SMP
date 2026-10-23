# shellcheck shell=bash disable=SC2034
# Fonctions partagées par deploy.sh et outils.sh (à sourcer, pas à exécuter).

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$RACINE/config.yml"
CLE="${MC_CLE_SSH:-$HOME/.ssh/mc_homelab_ed25519}"

info()   { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()     { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
avert()  { printf '\033[1;33m !!\033[0m %s\n' "$*"; }
erreur() { printf '\033[1;31mERREUR :\033[0m %s\n' "$*" >&2; exit 1; }

# Lit une clé simple (« cle: valeur ») de config.yml, sans guillemets ni commentaire.
valeur() {
  sed -n "s/^$1:[[:space:]]*//p" "$CONFIG" | head -n1 \
    | sed -E 's/[[:space:]]+#.*$//; s/^["'\'']//; s/["'\'']$//'
}

ip_valide() { [[ $1 =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; }

[[ -f $CONFIG ]] || erreur "config.yml introuvable dans $RACINE"

PROXMOX_IP="$(valeur proxmox_ip)"
VM_IP="$(valeur vm_ip)"
VM_ID="$(valeur vm_id)"
VM_USER="$(valeur vm_user)"
VM_USER="${VM_USER:-mcadmin}"

SSH_OPTS=(-i "$CLE" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8)
