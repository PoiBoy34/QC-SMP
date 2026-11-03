# mc-homelab : réseau Minecraft Java + Bedrock sur Proxmox

> **Pressé ?** Suis le [mini guide de déploiement](DEPLOIEMENT.md), étape par étape.

Un script, `./deploy.sh`, qui fait tout depuis ton PC :

1. crée une clé SSH dédiée et l'installe sur Proxmox (le mot de passe root est demandé une seule fois) ;
2. crée une VM Debian 13 (image cloud officielle, vérifiée par SHA512) avec IP fixe et ta clé ;
3. sécurise la VM : SSH par clé seulement, pas de root, pare-feu UFW, fail2ban, mises à jour de sécurité automatiques ;
4. installe Docker et lance le réseau du plan :

| Conteneur | Rôle | Joignable |
| --- | --- | --- |
| `mc-proxy` | Velocity + Geyser (NetherNet) + Floodgate + LuckPerms + MCXboxBroadcast | Internet : 25565/tcp, 19132/tcp+udp, 19133/udp |
| `mc-spawn` | Paper, hub en aventure, sans mobs ni faim (FancyNpcs, FAWE) | 127.0.0.1 seulement |
| `mc-smp` | Paper survie (CoreProtect) | 127.0.0.1 seulement |
| `mc-minijeu1`… | Paper isolé par mini-jeu (Skript, SkBee) | 127.0.0.1 seulement |
| `mc-mariadb` | Base LuckPerms : les rangs sont partagés par tous les serveurs | 127.0.0.1 seulement |
| `mc-ddns` | Garde ton domaine pointé sur l'IP de la maison (si domaine + jeton) | — |
| `lqdm-panneau` (service, pas un conteneur) | Panneau de contrôle web | Internet en HTTPS : 8443/tcp |

Plus : liste blanche commune à tous les serveurs, sauvegarde chaque nuit, certificat HTTPS
renouvelé automatiquement, et redémarrage automatique du proxy si l'IP de la maison change.

## Pourquoi Docker Compose et pas Crafty Controller

Crafty fait tourner tous les serveurs dans un seul conteneur et garde leur config dans sa propre
base de données. Ton plan veut le contraire : un conteneur par serveur, et un seul
`docker-compose.yml` identique sur le homelab et le dédié OVH. Ici, tout est décrit dans
`config.yml` et généré par Ansible. Passer au dédié revient donc à relancer le même déploiement
sur une autre IP. Crafty n'aide pas non plus pour Geyser et NetherNet, qui sont la partie fragile.
Les images [itzg](https://docker-minecraft-server.readthedocs.io/) téléchargent Paper, Velocity
et les plugins toutes seules. Pour gérer graphiquement, le réseau a son propre panneau web
(voir « Panneau de contrôle »), fait pour ces conteneurs.

## Démarrage

**Il te faut :** un PC sous Linux, macOS ou Windows avec WSL, et Ansible
(`sudo apt install ansible`, `brew install ansible` ou `pipx install --include-deps ansible`).
Il te faut aussi le mot de passe root de Proxmox et une IP libre pour la VM, à réserver dans le
modem (chez toi : Proxmox en 192.168.2.133, VM en 192.168.2.134, déjà dans `config.yml`).

```bash
# 1. Mets tes deux IP dans config.yml (proxmox_ip, vm_ip). Le reste est optionnel.
nano config.yml

# 2. Lance le déploiement (10 à 20 min la première fois)
./deploy.sh

# 3. À la fin, Ansible affiche un résumé : MAC de la VM, ports à ouvrir, état NetherNet, code Xbox.
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
| 19133 | UDP | Bedrock : connexions NetherNet (WebRTC), consoles de l'onglet Amis comprises |
| 8443 | TCP | Panneau de contrôle web (HTTPS), si `panneau: true` |

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

## NetherNet (Bedrock 26.60 et plus)

Depuis le **27 octobre 2026** (Bedrock 26.60), les joueurs Bedrock à jour ne se connectent
plus qu'en NetherNet : signalisation en TCP, puis connexion WebRTC en UDP. Ce que le déploiement
règle (vérifié dans le code source de Geyser et de MCXboxBroadcast, au 31 octobre) :

- `geyser_transport: "both"` : NetherNet **et** l'ancien protocole RakNet, pour les appareils
  pas encore à jour (Geyser 2.12.1 accepte Bedrock 26.40 à 26.60). Geyser est passé en
  `nethernet` par défaut le 26 octobre. Quand plus personne n'est en retard, mets
  `geyser_transport: "nethernet"` et redéploie.
- Signalisation intégrée sur 19132/TCP, WebRTC sur 19133/UDP, en HTTPS avec le certificat du domaine.
- Geyser annonce l'IP publique (joueurs d'Internet) **et** l'IP locale (joueurs à la maison, en
  direct). Si l'IP de la maison change, `veille-proxy.sh` met l'annonce à jour en moins de 10 min.
- **MCXboxBroadcast** (onglet Amis des consoles) n'ouvre plus de ports à lui : il relaie la
  demande de la console à la signalisation de Geyser, et la console se connecte ensuite à Geyser
  comme tout le monde (19133/UDP). Ce relais vérifie le certificat HTTPS sur le nom du serveur :
  le déploiement le fait donc viser le domaine, que le conteneur du proxy résout en local
  (`extra_hosts`), sans passer par le modem.
- Geyser et MCXboxBroadcast sont retéléchargés à chaque redémarrage du proxy : `./outils.sh maj`
  prend les derniers builds.

Vérification : `./outils.sh nethernet` doit montrer la signalisation démarrée et les adresses annoncées.

**Tests à faire au premier déploiement, avant de publier le guide**, sur Xbox, PlayStation et Switch :

| Test | Xbox | PS | Switch |
| --- | --- | --- | --- |
| Ajouter le compte du serveur en ami → onglet Amis → Rejoindre | ☐ | ☐ | ☐ |
| Pas de question « faire confiance » (HTTPS) | ☐ | ☐ | ☐ |
| Avec un compte enfant (autorisations parentales) | ☐ | ☐ | ☐ |
| Mobile ou Windows : ajout direct de l'adresse | ☐ | | |
| Un joueur depuis la maison (même réseau que le serveur) | ☐ | | |

État des outils au 31 octobre :

- **Geyser 2.12.1** : 26.60 supporté depuis le 21 octobre, NetherNet par défaut depuis le 26.
- **MCXboxBroadcast** : 26.60 depuis le 27 octobre (build 162 du 29 octobre), nouveau système
  de relais. C'est la méthode console du guide.
- **BedrockConnect** : compatible 26.60 et NetherNet depuis le 27 octobre, mais il faut changer
  le DNS de chaque console vers un serveur tiers. Pas installé : à garder en plan B si un modèle
  de console refusait la méthode Amis.

## Accès à distance : Tailscale

Avec `tailscale: true` (par défaut), le déploiement installe Tailscale **sur l'hôte Proxmox**,
qui devient routeur de sous-réseau : tes appareils Tailscale joignent tout le réseau de la maison
(interface Proxmox, `ssh mc`, `./outils.sh`, `./deploy.sh`) de partout. Les joueurs n'y passent
jamais.

- Sur l'hôte plutôt que dans un conteneur : rien à bricoler (pas de `/dev/net/tun` à passer à un
  LXC), et l'accès reste possible quand une VM ou un conteneur est en panne, c'est-à-dire
  justement quand on en a besoin.
- Paquet officiel (dépôt pkgs.tailscale.com, comme l'installateur de Tailscale). Seul ce dépôt
  est mis à jour : sans abonnement Proxmox, un `apt update` complet échoue sur le dépôt *enterprise*.
- `--accept-dns=false` : Proxmox garde la main sur son DNS. Routage IPv4 seulement, pour ne pas
  couper l'IPv6 automatique de l'hôte.
- Connexion : clé `tailscale_authkey` dans `secrets.yml`, ou `./outils.sh tailscale` (lien à ouvrir).
- Une seule fois, dans la console Tailscale : approuver la route `192.168.2.0/24` et désactiver
  l'expiration de la clé de l'hôte (voir le [mini guide](DEPLOIEMENT.md), étape 5).
- Depuis un tailnet, la VM voit les connexions arriver de l'IP de l'hôte (Tailscale les traduit) :
  le pare-feu de la VM, qui accepte SSH depuis le réseau local et l'hôte, n'a rien à changer.

## Discord : tchat relié au jeu

Le plugin [VelocityDiscord](https://github.com/fooooooooooooooo/VelocityDiscord), sur le proxy,
relie le tchat de **tous** les serveurs (Java et consoles) à un salon Discord, dans les deux
sens. Seuls les messages des joueurs passent (pas d'arrivées, départs, morts ni progrès), et la
commande `/list` de Discord dit qui est en ligne. Il s'installe dès que `discord_token` (secrets.yml) et `discord_salon`
(config.yml) sont remplis.

1. https://discord.com/developers/applications → **New Application** (par ex. « LQDM »).
2. Onglet **Bot** : **Reset Token**, copie le jeton dans `discord_token` de `secrets.yml`.
   Plus bas, active **Server Members Intent** et **Message Content Intent**.
3. Onglet **OAuth2 → URL Generator** : coche `bot` et `applications.commands`, puis les
   permissions *View Channels*, *Send Messages*, *Embed Links* et *Read Message History*.
   Ouvre le lien généré et ajoute le bot au serveur Discord LQDM. Il faut le droit
   « Gérer le serveur » sur ce Discord : sinon, demande à CampFire012.
4. Crée un salon (par ex. `#tchat-minecraft`). Dans Discord : Paramètres → Avancés → **Mode
   développeur**, puis clic droit sur le salon → **Copier l'identifiant** → `discord_salon`
   dans `config.yml`.
5. Facultatif, mais plus joli : salon → **Modifier le salon → Intégrations → Webhooks →
   Nouveau webhook → Copier l'URL du webhook**, dans `discord_webhook` de `secrets.yml`. Chaque
   message s'affiche alors sous le nom et la tête du skin du joueur.
6. `./deploy.sh --tags serveur`.

Le tchat en jeu reste séparé par serveur (spawn, SMP, mini-jeux) : seul le salon Discord voit
tout. Pour gérer la liste blanche depuis Discord, il faudra un petit bot de plus : à faire le
jour où la liste blanche sera activée.

## Compte Xbox du serveur (onglet Amis des consoles)

Crée un compte Microsoft **dédié** (jamais le tien : il peut être signalé). Au premier démarrage,
le résumé d'Ansible affiche un code. Tu peux aussi le revoir avec :

```bash
./outils.sh xbox
```

Ouvre https://www.microsoft.com/link, entre le code et connecte-toi avec le compte dédié. Le
serveur accepte ensuite automatiquement les demandes d'ami.

## Panneau de contrôle

`https://mc.qcsmp.mekhorizon.org:8443` (le domaine du jeu, port `panneau_port`). Dans un
navigateur, de partout, sans Tailscale :

- **Tableau de bord** : chaque serveur (en marche ou non, CPU, mémoire, joueurs), mémoire,
  CPU et disque de la VM ; démarrer, arrêter, redémarrer ; annonce à tous les joueurs.
- **Joueurs** : tous ceux venus au moins une fois (Java et Bedrock), en ligne ou non, temps de
  jeu, morts, distance… Fiche par joueur : envoyer sur un serveur, mode de jeu, message,
  expulser, bannir, op, grade LuckPerms, liste blanche.
- **Admins** : les op, en ajouter ou en retirer ; les grades LuckPerms.
- **Console** : le journal en direct de chaque serveur (proxy compris) et une ligne de commande.
- **Journaux** : les anciens journaux, avec filtre et téléchargement.
- **Plugins et datapacks** : glisser-déposer un `.jar` (ou un datapack `.zip`), désactiver,
  supprimer, puis redémarrer le serveur en un clic.
- **Historique** : qui a fait quoi, avec son compte.

Comptes : `panneau_comptes` dans `config.yml`, un par personne. Les mots de passe sont créés
sur la VM au déploiement : `./outils.sh panneau` les affiche, `./outils.sh panneau nouveau
<compte>` en change un (s'il a fuité). Retirer un nom de la liste coupe son accès au déploiement
suivant.

Sécurité : HTTPS avec le certificat Let's Encrypt du jeu, cookie de session sécurisé, 5 mauvais
mots de passe = adresse bloquée une heure (fail2ban), service systemd durci. Un compte du
panneau peut tout faire sur les serveurs (comme `docker`) : ne le donne qu'à des admins de
confiance. Sans domaine ni certificat, le panneau reste fermé à Internet (réseau local seulement,
en HTTP).

## Au quotidien

```bash
./outils.sh                          # aide
./outils.sh etat                     # conteneurs, CPU, RAM
./outils.sh verifier                 # le serveur vu d'Internet : DNS, Java, Bedrock (comme le site)
./outils.sh whitelist JosephMC       # joueur Java
./outils.sh whitelist .Gamertag      # joueur Bedrock (avec le point de Floodgate)
./outils.sh console smp              # console (« exit » pour sortir, le serveur continue)
./outils.sh logs proxy
./outils.sh snapshot                 # instantané Proxmox avant un tournage
./outils.sh tailscale                # connecter Tailscale sur l'hôte, ou voir son état
./outils.sh maj                      # mettre à jour Paper, Geyser, plugins
./outils.sh panneau                  # adresse, comptes et mots de passe du panneau web
./outils.sh erreurs spawn            # erreurs Skript et datapacks d'un serveur
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
