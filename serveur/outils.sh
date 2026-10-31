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
  verifier                 le serveur vu d'Internet (comme le site) : DNS, Java, Bedrock
  xbox                     dernier code de connexion du compte Xbox (MCXboxBroadcast)
  xbox nouveau             déconnecte le compte Xbox du serveur et donne un nouveau code
                           (pour changer de compte, ou si le code a expiré)
  redemarrer [serveur]     redémarre un serveur, ou tout le réseau sans argument
  maj                      met à jour images, Paper, Geyser et plugins (redémarre tout)
  sauvegarde               lance une sauvegarde maintenant
  snapshot [nom]           instantané Proxmox de la VM (avant un tournage)
  snapshots                liste les instantanés
  tailscale                connecte l'hôte Proxmox à ton Tailscale, ou affiche son état
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
  verifier)
    # Même source que l'état affiché sur le site : mcsrvstat.us teste depuis Internet.
    domaine="$(valeur domaine)"; domaine="${domaine:-$VM_IP}"
    ip_maison=$(vm "curl -4 -fsS --max-time 10 https://api.ipify.org" || true)
    echo "IP publique de la maison : ${ip_maison:-?}"
    info "1. Le nom $domaine, vu par ce PC et par les DNS publics (Google, Cloudflare)"
    ip_dns=$(python3 -c 'import socket, sys; print(socket.gethostbyname(sys.argv[1]))' "$domaine" 2>/dev/null || true)
    echo "ce PC      : ${ip_dns:-introuvable}"
    for resolveur in "Google|https://dns.google/resolve" "Cloudflare|https://cloudflare-dns.com/dns-query"; do
      curl -fsS --max-time 10 -H 'accept: application/dns-json' "${resolveur#*|}?name=$domaine&type=A" | python3 -c '
import json, sys
d = json.load(sys.stdin)
etats = {0: "OK", 2: "ÉCHEC (SERVFAIL, souvent un problème DNSSEC)", 3: "NOM INCONNU (NXDOMAIN)"}
ips = [a["data"] for a in d.get("Answer", []) if a.get("type") == 1]
ligne = sys.argv[1].ljust(10) + " : " + etats.get(d.get("Status"), str(d.get("Status")))
if ips:
    ligne += " -> " + ", ".join(ips)
if d.get("Comment"):
    ligne += " (" + str(d["Comment"]) + ")"
print(ligne)' "${resolveur%%|*}" || echo "${resolveur%%|*} : pas de réponse"
    done
    teste() {  # $1 = libellé, $2 = adresse
      for edition in java bedrock; do
        chemin=$([[ $edition == java ]] && echo "3" || echo "bedrock/3")
        curl -fsS --max-time 20 -A "LQDM-outils/1.0 (github.com/PoiBoy34/QC-SMP)" \
          "https://api.mcsrvstat.us/$chemin/$2" | python3 -c '
import json, sys
d = json.load(sys.stdin)
debug = d.get("debug", {})
ligne = sys.argv[1].ljust(8) + " : " + ("EN LIGNE" if d.get("online") else "HORS LIGNE")
ligne += " (" + str(d.get("ip", "?")) + ":" + str(d.get("port", "?")) + ")"
if debug.get("cachehit"):
    ligne += " [résultat en cache]"
if debug.get("error"):
    ligne += " : " + json.dumps(debug["error"], ensure_ascii=False)
print(ligne)' "$edition" || echo "$edition : mcsrvstat.us ne répond pas"
      done
    }
    info "2. Par le nom $domaine (comme le site)"
    teste nom "$domaine"
    if [[ -n $ip_maison ]]; then
      info "3. Directement par l'IP $ip_maison (teste les redirections de ports, sans le DNS)"
      teste ip "$ip_maison"
    fi
    echo "Par l'IP en ligne mais par le nom hors ligne : c'est le DNS (voir l'étape 1)."
    echo "Hors ligne même par l'IP : ce sont les redirections de ports du modem."
    echo "Un résultat « en cache » peut dater de quelques minutes : relance dans 5 min." ;;
  nethernet)
    # Démarrage de la signalisation (http ou https) puis adresses annoncées aux joueurs
    vm "docker logs mc-proxy 2>&1 | grep -a 'Built-in signaling' | tail -n 1"
    cmd proxy "geyser nethernet advertised" ;;
  xbox)
    depuis=""
    if [[ ${2:-} == nouveau ]]; then
      info "Déconnexion du compte Xbox du serveur, puis redémarrage du proxy (les joueurs sont déconnectés)"
      depuis=$(vm "date -u +%Y-%m-%dT%H:%M:%SZ")
      vm "sudo rm -f /opt/minecraft/proxy/plugins/Geyser-Velocity/extensions/mcxboxbroadcast/cache.json"
      compose restart proxy
      info "Attente du nouveau code (jusqu'à 3 minutes)…"
    fi
    # Dernier événement du journal : un code à entrer, ou le compte connecté
    for _ in $(seq 36); do
      etat=$(vm "docker logs ${depuis:+--since $depuis} mc-proxy 2>&1 | grep -o -E 'enter the code [A-Z0-9]+|Successfully authenticated as [^(]+' | tail -n 1")
      [[ -n $etat || -z $depuis ]] && break
      sleep 5
    done
    case "$etat" in
      "enter the code "*)
        echo "Dans une fenêtre de navigation PRIVÉE, ouvre https://www.microsoft.com/link, entre le code ${etat##* }"
        echo "et connecte-toi avec le compte Xbox DÉDIÉ au serveur (pas le tien)."
        echo "Code expiré ? ./outils.sh xbox nouveau" ;;
      "Successfully authenticated as "*)
        ok "compte Xbox du serveur connecté : ${etat#Successfully authenticated as }"
        echo "     Pour changer de compte : ./outils.sh xbox nouveau" ;;
      *)
        echo "Rien dans le journal du proxy (xbox_broadcast désactivé, ou proxy en train de démarrer)." ;;
    esac ;;
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
  tailscale)
    proxmox "command -v tailscale >/dev/null" \
      || erreur "Tailscale n'est pas installé sur l'hôte : mets « tailscale: true » dans config.yml puis ./deploy.sh --tags tailscale"
    if proxmox "tailscale status >/dev/null 2>&1"; then
      proxmox "tailscale status; echo; echo \"Adresse Tailscale de l'hôte : \$(tailscale ip -4)\""
    else
      pont="$(valeur vm_bridge)"
      reseau=$(proxmox "ip -4 route show dev ${pont:-vmbr0} proto kernel scope link | awk '{print \$1; exit}'")
      info "Ouvre le lien affiché et connecte-toi à ton compte Tailscale (réseau annoncé : $reseau)"
      ssh -t "${SSH_OPTS[@]}" "root@$PROXMOX_IP" "tailscale up --advertise-routes=$reseau --accept-dns=false"
      ok "hôte connecté. Une seule fois, sur https://login.tailscale.com/admin/machines, menu « … » de l'hôte :"
      echo "     « Edit route settings » → coche $reseau, puis « Disable key expiry »."
    fi ;;
  ssh)
    vm_tty ;;
  *)
    aide ;;
esac
