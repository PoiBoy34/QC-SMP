#!/usr/bin/env bash
# Commandes du quotidien, depuis ton PC. Lance « ./outils.sh » sans argument pour l'aide.
set -euo pipefail
source "$(dirname "$0")/lib/commun.sh"

vm()      { ssh "${SSH_OPTS[@]}" "$VM_USER@$VM_IP" "$@"; }
vm_tty()  { ssh -t "${SSH_OPTS[@]}" "$VM_USER@$VM_IP" "$@"; }
proxmox() { ssh "${SSH_OPTS[@]}" "root@$PROXMOX_IP" "$@"; }
compose() { vm "cd /opt/minecraft && docker compose $*"; }
# Envoie une commande à la console d'un serveur (spawn, smp, proxy, minijeu1…)
cmd()     { vm "docker exec mc-$1 rcon-cli $(printf '%q' "$2")"; }
paper()   { vm "docker ps --format '{{.Names}}' | sed -n 's/^mc-//p' | grep -vx -e proxy -e mariadb -e ddns"; }

aide() {
  cat <<EOF
Usage : ./outils.sh <commande>

  etat                     conteneurs, mémoire et CPU
  logs <serveur>           journal en direct (proxy, spawn, smp, minijeu1…)  Ctrl+C pour quitter
  console <serveur>        console interactive (rcon)                        « exit » pour quitter
  cmd <serveur> "<cmd>"    une seule commande, ex. : ./outils.sh cmd smp "say Salut"
  whitelist <pseudo>       autorise un joueur sur tout le réseau
                           Java : JosephMC     Bedrock : .Gamertag (avec le point de Floodgate)
  donner <joueur> <item> [n]  donne un item custom de contenu/items (ex. poutine)
  nethernet                état NetherNet de Geyser (adresses annoncées, signalisation)
  xbox                     dernier code de connexion du compte Xbox (MCXboxBroadcast)
  redemarrer [serveur]     redémarre un serveur, ou tout le réseau sans argument
  maj                      met à jour images, Paper, Geyser et plugins (redémarre tout)
  sauvegarde               lance une sauvegarde maintenant
  snapshot [nom]           instantané Proxmox de la VM (avant un tournage)
  snapshots                liste les instantanés
  ssh                      shell sur la VM
EOF
}

case "${1:-}" in
  etat)
    compose ps
    vm "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'" ;;
  logs)
    vm_tty "docker logs -f --tail 100 mc-${2:?serveur ?}" ;;
  console)
    echo "Console de ${2:?serveur ?} — tape « exit » pour quitter (le serveur continue de tourner)."
    vm_tty "docker exec -it mc-$2 rcon-cli" ;;
  cmd)
    cmd "${2:?serveur ?}" "${3:?commande ?}" ;;
  whitelist)
    pseudo="${2:?pseudo ?}"
    if [[ $pseudo == .* ]]; then
      cmd spawn "fwhitelist add ${pseudo#.}"     # Floodgate retrouve le compte Xbox
    else
      cmd spawn "whitelist add $pseudo"
    fi
    # Liste partagée : les autres serveurs la relisent
    for s in $(paper); do [[ $s == spawn ]] || cmd "$s" "whitelist reload" >/dev/null; done
    ok "$pseudo autorisé sur tout le réseau" ;;
  donner)
    joueur="${2:?joueur ?}"; objet="${3:?item ? (voir contenu/items)}"; quantite="${4:-1}"
    commande=$(python3 -c '
import json, sys
items = json.load(open(sys.argv[1], encoding="utf-8"))
if sys.argv[2] not in items:
    sys.exit("item inconnu, au choix : " + ", ".join(sorted(items)))
print(items[sys.argv[2]]["commande"])' "$RACINE/../contenu/generes/items.json" "$objet") || exit 1
    commande="${commande/<joueur>/$joueur}"; commande="${commande/<quantite>/$quantite}"
    # Le joueur n'est que sur un serveur : on tente partout, un seul répondra « Gave ».
    for s in $(paper); do cmd "$s" "$commande" | grep -i "gave\|donné" && exit 0; done
    erreur "$joueur n'est connecté sur aucun serveur Paper" ;;
  nethernet)
    cmd proxy "geyser nethernet status"
    cmd proxy "geyser nethernet advertised" ;;
  xbox)
    code=$(vm "docker logs mc-proxy 2>&1 | grep -o 'enter the code [A-Z0-9]*' | tail -n 1 | awk '{print \$4}'")
    if [[ -n $code ]]; then
      echo "Ouvre https://www.microsoft.com/link, entre le code $code et connecte le compte Xbox DÉDIÉ au serveur."
    else
      echo "Aucun code dans le journal : le compte est déjà connecté (ou xbox_broadcast est désactivé)."
    fi ;;
  redemarrer)
    if [[ -n ${2:-} ]]; then compose restart "$2"; else compose restart; fi ;;
  maj)
    info "Mise à jour : les joueurs seront déconnectés environ une minute"
    compose pull
    compose up -d --remove-orphans
    compose restart ;;
  sauvegarde)
    vm "sudo /opt/minecraft/bin/sauvegarde.sh" ;;
  snapshot)
    nom="${2:-avant_tournage_$(date +%Y%m%d_%H%M)}"
    info "Instantané « $nom » de la VM $VM_ID (sans la RAM)"
    proxmox "qm snapshot $VM_ID $(printf '%q' "$nom") --description 'mc-homelab ./outils.sh'"
    ok "retour arrière possible dans Proxmox : VM $VM_ID > Snapshots > $nom > Rollback" ;;
  snapshots)
    proxmox "qm listsnapshot $VM_ID" ;;
  ssh)
    vm_tty ;;
  *)
    aide ;;
esac
