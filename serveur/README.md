# mc-homelab : réseau Minecraft Java + Bedrock sur Proxmox

> **Pressé ?** Suis le [mini guide de déploiement](DEPLOIEMENT.md), étape par étape.

Un script, `./deploy.sh`, qui fait tout depuis ton PC :

1. crée une clé SSH dédiée et l'installe sur Proxmox (le mot de passe root est demandé une seule fois) ;
2. crée une VM Debian 13 (image cloud officielle, vérifiée par SHA512) avec IP fixe et ta clé ;
3. sécurise la VM : SSH par clé seulement, pas de root, pare-feu UFW, fail2ban, mises à jour de sécurité automatiques ;
4. installe Docker et lance le réseau du plan :

| Conteneur | Rôle | Joignable |
| --- | --- | --- |
| `mc-proxy` | Velocity + Geyser (NetherNet) + Floodgate + LuckPerms + MCXboxBroadcast | Internet : 25565/tcp, 19132/tcp+udp, 19133/udp, 19140-19149/udp |
| `mc-spawn` | Paper, hub en aventure, sans mobs ni faim (FancyNpcs, FAWE) | 127.0.0.1 seulement |
| `mc-smp` | Paper survie (CoreProtect) | 127.0.0.1 seulement |
| `mc-minijeu1`… | Paper isolé par mini-jeu (Skript, SkBee) | 127.0.0.1 seulement |
| `mc-mariadb` | Base LuckPerms : les rangs sont partagés par tous les serveurs | 127.0.0.1 seulement |
| `mc-ddns` | Garde ton domaine pointé sur l'IP de la maison (si domaine + jeton) | — |

Plus : liste blanche commune à tous les serveurs, sauvegarde chaque nuit, certificat HTTPS
renouvelé automatiquement, et redémarrage automatique du proxy si l'IP de la maison change.

## Pourquoi Docker Compose et pas Crafty Controller

Crafty fait tourner tous les serveurs dans un seul conteneur et garde leur config dans sa propre
base de données. Ton plan veut le contraire : un conteneur par serveur, et un seul
`docker-compose.yml` identique sur le homelab et le dédié OVH. Ici, tout est décrit dans
`config.yml` et généré par Ansible. Passer au dédié revient donc à relancer le même déploiement
sur une autre IP. Crafty n'aide pas non plus pour Geyser et NetherNet, qui sont la partie fragile.
Les images [itzg](https://docker-minecraft-server.readthedocs.io/) téléchargent Paper, Velocity
et les plugins toutes seules. Pour la console, `./outils.sh console smp` remplace le panneau web.

## Démarrage

**Il te faut :** un PC sous Linux, macOS ou Windows avec WSL, et Ansible
(`sudo apt install ansible`, `brew install ansible` ou `pipx install --include-deps ansible`).
Il te faut aussi le mot de passe root de Proxmox et une IP libre sur ton réseau, hors de la plage
DHCP du routeur.

```bash
# 1. Mets tes deux IP dans config.yml (proxmox_ip, vm_ip). Le reste est optionnel.
nano config.yml

# 2. Lance le déploiement (10 à 20 min la première fois)
./deploy.sh

# 3. À la fin, Ansible affiche un résumé : ports à ouvrir, état NetherNet, code Xbox.
```

Le script se relance sans risque : il ne recrée rien de ce qui existe déjà. Après une modification
de `config.yml` (nouveau mini-jeu, RAM, domaine…) :

```bash
./deploy.sh --tags serveur          # reconfigure la VM seulement
```

Il refuse de toucher une VM existante qui porte un autre nom, et de créer la VM si l'IP répond
déjà au ping.

## Routeur : ports à rediriger vers la VM

| Port | Protocole | Pour |
| --- | --- | --- |
| 25565 | TCP | Java |
| 19132 | **TCP et UDP** | Bedrock : signalisation NetherNet (TCP), ancien protocole RakNet (UDP) |
| 19133 | UDP | Bedrock : connexions NetherNet (WebRTC) |
| 19140-19149 | UDP | Méthode « Ami » (MCXboxBroadcast) |

Le tunnel Cloudflare Zero Trust ne peut pas transporter ce trafic : il faut une vraie redirection
de ports. Note que ça expose l'IP de la maison (risque DDoS noté dans le plan). C'est acceptable
pour développer, mais les tournages devraient se faire sur le dédié OVH.

## Domaine et HTTPS (recommandé)

Sans HTTPS, chaque joueur Bedrock voit « faire confiance à ce serveur ? » à sa première connexion.
Pour l'éviter, remplis dans `config.yml` :

- `domaine` : par ex. `mc.qcsmp.mekhorizon.org` ;
- `cloudflare_api_token`, dans **`secrets.yml`** (copie `secrets.yml.exemple`) : Cloudflare →
  *My Profile → API Tokens → Create Token → Edit zone DNS*, limité à la zone `mekhorizon.org`.
  Ce fichier n'est jamais poussé sur GitHub.

Le déploiement obtient alors un certificat Let's Encrypt par défi DNS (aucun port 80/443 à
ouvrir), le renouvelle tout seul, et crée ou met à jour l'enregistrement DNS vers ton IP en mode
**DNS only** (nuage gris : Cloudflare ne peut pas relayer le jeu).

## Latence : Cloudflare et réseau de la maison

Cloudflare DNS n'ajoute pas de lag : le nom est résolu une fois à la connexion, puis le jeu
parle directement à ta maison. Ce qui ajouterait du lag (ou casserait tout), c'est de faire
**passer** le trafic de jeu par Cloudflare. Donc :

| Nom | Type Cloudflare | Pourquoi |
| --- | --- | --- |
| `mc.qcsmp.mekhorizon.org` | A, **DNS only (nuage gris)**, TTL 1 min | Le jeu va en direct. Géré par `mc-ddns`. |
| `qcsmp.mekhorizon.org` | CNAME vers `poiboy34.github.io`, **DNS only** | Site de téléchargement du launcher (GitHub Pages) |
| pages web (carte, panneau…) | Tunnel Zero Trust | Du HTTP seulement, jamais le nom du jeu |

- Jamais de nuage orange, de tunnel ni de Spectrum pour `play.` : le proxy orange ne transporte
  pas le jeu. Spectrum ne couvrirait que Java, et NetherNet (WebRTC en UDP) a besoin d'un accès direct.
- Pas d'enregistrement AAAA (IPv6) tant que l'IPv6 n'est pas ouvert de bout en bout : sinon les
  clients essaient l'IPv6 d'abord et attendent avant de se rabattre sur l'IPv4.
- Pas besoin de SRV : les ports par défaut (25565, 19132) sont utilisés, et Bedrock ne lit pas les SRV.
- Si la zone a des enregistrements CAA, ajoutes-y `letsencrypt.org`, sinon le certificat échoue.
- Ce que le launcher télécharge (manifeste, nouvelles, état du serveur) doit rester public :
  derrière Zero Trust Access, le launcher recevrait la page de connexion au lieu du fichier.

Ce qui compte vraiment pour le lag, par ordre d'importance :

1. **Le CPU.** `proxmox_cpu_performance: true` fixe le gouverneur « performance » sur l'hôte.
   Pré-génère aussi le monde du SMP avant d'ouvrir (la génération de chunks est la première
   cause de lag sur un SMP neuf) :
   ```bash
   ./outils.sh cmd smp "worldborder set 6000"
   ./outils.sh cmd smp "chunky radius 3000"
   ./outils.sh cmd smp "chunky start"        # suivre : ./outils.sh logs smp
   ```
2. **L'upload de la maison.** Compte environ 0,5 à 1 Mbit/s par joueur, avec des pointes au
   chargement des chunks. Si ton forfait a peu d'upload, baisse `VIEW_DISTANCE` du SMP à 8.
   N'envoie pas de vidéo sur YouTube pendant une session : un upload saturé fait exploser le
   ping de tout le monde. Un routeur avec SQM (OpenWrt, OPNsense) règle ce problème.
3. **Les joueurs à la maison.** Si ton routeur ou un Pi-hole/AdGuard le permet, ajoute un DNS
   local `mc.qcsmp.mekhorizon.org → <vm_ip>` : les appareils de la maison passent directement par le
   réseau local au lieu de faire l'aller-retour par le routeur (et ça marche même si le routeur
   ne gère pas le « NAT loopback »). Sans risque pour Geyser, qui annonce des IP, pas le nom.
4. **Vérifie que tu n'es pas derrière un CGNAT** : l'IP WAN affichée par le routeur doit être
   la même que celle de `curl -4 ifconfig.me`. Si le routeur affiche 100.64.x.x ou 10.x.x.x,
   les redirections de ports ne peuvent pas marcher : demande une IP publique à ton FAI.

## NetherNet : à faire avant le 27 octobre

Ce qui est déjà réglé par le déploiement (vérifié dans le code source de Geyser) :

- `transport: both` : Geyser accepte RakNet (consoles pas encore à jour) **et** NetherNet.
  Par défaut, Geyser reste en `raknet` seul : sans ce réglage, plus aucun joueur Bedrock n'entre
  après le 27. Quand toutes les consoles sont en 26.60, mets `geyser_transport: "nethernet"` et
  redéploie.
- Signalisation intégrée sur 19132/TCP, WebRTC sur 19133/UDP, HTTPS si le domaine est configuré.
- Geyser annonce l'IP publique (joueurs d'Internet) **et** l'IP locale (joueurs à la maison, en
  direct). Si l'IP de la maison change, `veille-proxy.sh` met l'annonce à jour en moins de 10 min.
- Geyser est retéléchargé à chaque redémarrage : `./outils.sh maj` prend le dernier build.

Vérification : `./outils.sh nethernet` doit montrer la signalisation démarrée et les adresses annoncées.

**Tests à faire après le 27, avant de publier le guide**, sur Xbox, PlayStation et Switch :

| Test | Xbox | PS | Switch |
| --- | --- | --- | --- |
| Méthode 1 : ajouter le compte du serveur en ami → onglet Amis → Rejoindre | ☐ | ☐ | ☐ |
| Méthode 2 : DNS BedrockConnect → serveur vedette → menu → adresse | ☐ | ☐ | ☐ |
| Pas de question « faire confiance » (si HTTPS) | ☐ | ☐ | ☐ |
| Mobile ou Windows : ajout direct de l'adresse | ☐ | | |
| Un joueur depuis la maison (même réseau que le serveur) | ☐ | | |

État des outils au 23 octobre :

- **MCXboxBroadcast (méthode 1)** : passé à NetherNet en septembre 2026, compatible 26.50.
  C'est la méthode à mettre en avant.
- **BedrockConnect (méthode 2)** : aucune trace de NetherNet dans le projet (dernière version :
  26.50, le 15 septembre). Elle risque de ne plus marcher le 27 tant que BedrockConnect n'aura pas
  publié de mise à jour. Mieux vaut retirer la méthode 2 du guide, ou la marquer « en attente »,
  jusqu'à ce que le test passe.

## Compte Xbox du serveur (méthode 1)

Crée un compte Microsoft **dédié** (jamais le tien : il peut être signalé). Au premier démarrage,
le résumé d'Ansible affiche un code. Tu peux aussi le revoir avec :

```bash
./outils.sh xbox
```

Ouvre https://www.microsoft.com/link, entre le code et connecte-toi avec le compte dédié. Le
serveur accepte ensuite automatiquement les demandes d'ami.

## Au quotidien

```bash
./outils.sh                          # aide
./outils.sh etat                     # conteneurs, CPU, RAM
./outils.sh whitelist JosephMC       # joueur Java
./outils.sh whitelist .Gamertag      # joueur Bedrock (avec le point de Floodgate)
./outils.sh console smp              # console (« exit » pour sortir, le serveur continue)
./outils.sh logs proxy
./outils.sh snapshot                 # instantané Proxmox avant un tournage
./outils.sh maj                      # mettre à jour Paper, Geyser, plugins
ssh mc                               # shell sur la VM (raccourci ajouté par deploy.sh)
```

Pour donner les droits admin sur tout le réseau (rangs partagés via MariaDB) :
`./outils.sh cmd proxy "lpv user JosephMC permission set * true"`, ou un groupe LuckPerms.

## Sur la VM

```
/opt/minecraft/
├── docker-compose.yml    généré, ne pas modifier à la main
├── .env                  mots de passe générés (rcon, MariaDB)
├── proxy/                Velocity, Geyser, Floodgate (plugins/, velocity.toml)
├── serveurs/<nom>/       un dossier par serveur Paper (monde, plugins, scripts Skript)
├── partage/whitelist.json
├── sauvegardes/          chaque nuit à 04:30, gardées 7 jours
└── secrets/, certs/, bin/
```

Les sauvegardes restent sur la VM tant que `sauvegarde_rsync` est vide. Pour une vraie copie hors
serveur, remplis-le (NAS, autre machine) ou active une sauvegarde Proxmox de la VM
(*Datacenter → Backup*) vers un autre disque.

## Limites connues

- `mc_version: "LATEST"` suit la dernière version de Paper. Si un plugin n'existe pas encore
  pour cette version, le serveur démarre sans lui (avertissement dans `./outils.sh logs <serveur>`).
  Fige la version une fois que tout est validé.
- ViaVersion est installé sur les serveurs Paper : Geyser parle toujours la dernière version
  Java, et ViaVersion évite de bloquer les joueurs Bedrock quand Paper a un peu de retard.
- Les gamertags qui contiennent des espaces ne passent pas par `./outils.sh whitelist` : utilise
  directement `./outils.sh cmd spawn "fwhitelist add <gamertag>"`.
