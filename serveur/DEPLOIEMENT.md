# Déployer le serveur : mini guide

Du Proxmox prêt au premier joueur connecté, environ une heure. Les détails et le dépannage
sont dans le [README](README.md).

## Avant de commencer

- [ ] Un PC sous **Linux, macOS ou Windows avec WSL** (sur Windows : installe Ubuntu
      depuis le Microsoft Store et fais tout dedans).
- [ ] **git** et **Ansible** sur ce PC : `sudo apt install git ansible`
      (macOS : `brew install ansible`).
- [ ] Le **mot de passe root** de ton Proxmox (192.168.2.133).
- [ ] Un **jeton Cloudflare** : My Profile → API Tokens → Create Token → modèle
      *Edit zone DNS*, limité à la zone `mekhorizon.org`.
- [ ] Un **compte Tailscale** (gratuit, https://tailscale.com) pour administrer le serveur de partout.
- [ ] Un **compte Microsoft dédié** au serveur (pas le tien), pour la méthode « Amis » des consoles.

## Et les consoles ?

Rien à installer sur les consoles (elles ne le permettent pas) : tout se passe sur le
serveur, et `deploy.sh` le met en place tout seul :

- **Geyser** traduit Bedrock en Java, et **Floodgate** laisse entrer les joueurs qui n'ont
  qu'un compte Microsoft (pas de Minecraft Java) ;
- **NetherNet**, le seul protocole des Bedrock à jour depuis la version 26.60 (27 octobre 2026),
  est activé, avec HTTPS. L'ancien protocole reste ouvert pour les appareils en retard ;
- **MCXboxBroadcast** fait apparaître le serveur dans l'onglet **Amis** des consoles. Depuis
  la 26.60, il relaie la demande de la console et la console se connecte ensuite directement
  au serveur : il n'a plus besoin de ports à lui.

Ce qui reste à faire à la main pour les consoles : créer le compte Microsoft du serveur
(étape 6), ajouter les joueurs console à la liste blanche avec le point (étape 7) et
tester sur chaque console (étape 8).

La méthode DNS (BedrockConnect) n'est volontairement pas installée. Elle est compatible
NetherNet depuis le 27 octobre, mais elle oblige chaque joueur à changer le DNS de sa console
vers un serveur tiers. La méthode Amis fait la même chose sans rien toucher sur la console.

## 1. Récupérer le projet

```bash
git clone https://github.com/PoiBoy34/QC-SMP.git
cd QC-SMP/serveur
```

## 2. Remplir la config

Ton réseau est déjà dans `config.yml` :

```yaml
proxmox_ip: "192.168.2.133"  # ton Proxmox
vm_ip: "192.168.2.134"       # la VM Minecraft (passerelle 192.168.2.1 et /24 détectés tout seuls)
```

Ajoute ton pseudo Java pour être op et sur la liste blanche :

```yaml
admins_java: ["TonPseudo"]
```

Vérifie aussi que `vm_id: 250` est libre dans Proxmox, et que `vm_memory_mb: 12288`
(12 Go) laisse assez de mémoire au reste de ton Proxmox.

Puis les secrets (ce fichier n'est jamais envoyé sur GitHub) :

```bash
cp secrets.yml.exemple secrets.yml
nano secrets.yml
```

- `cloudflare_api_token` : le jeton Cloudflare ;
- `tailscale_authkey` (facultatif) : sur https://login.tailscale.com/admin/settings/keys,
  *Generate auth key*, sans cocher *Reusable* ni *Ephemeral*. Sans clé, tu connecteras
  Tailscale à l'étape 5 avec un lien.

## 3. Lancer le déploiement

```bash
./deploy.sh
```

- Il demande le **mot de passe root de Proxmox une seule fois**, puis tout se fait par clé SSH.
- Compte **10 à 20 minutes** : création de la VM, Tailscale, sécurité, Docker, téléchargement
  de Paper, Velocity et Geyser.
- À la fin, un **résumé** s'affiche : l'adresse MAC de la VM, les ports à ouvrir, l'état
  NetherNet et le code Xbox.

## 4. Le modem (192.168.2.1)

**Réserve l'IP de la VM.** Dans le modem, section DHCP (réservation, ou « IP statique ») :
associe `192.168.2.134` à l'adresse MAC affichée dans le résumé. Le modem ne la donnera alors
jamais à un autre appareil. Fais la même chose pour ton Proxmox (192.168.2.133) si ce n'est
pas déjà fait.

**Redirige ces ports vers 192.168.2.134 :**

| Port | Protocole |
| --- | --- |
| 25565 | TCP |
| 19132 | **TCP et UDP** |
| 19133 | UDP |

Vérifie que l'IP WAN affichée par le modem est la même que celle que donne
`curl -4 ifconfig.me`. Si le modem affiche 100.64.x.x ou 10.x.x.x, ton FAI te met
derrière un CGNAT et les redirections ne marcheront pas.

## 5. Tailscale (accès à distance)

Tailscale est installé sur l'hôte Proxmox. Il ouvre le réseau de la maison à **tes** appareils,
pas aux joueurs.

1. Sans clé dans `secrets.yml` : `./outils.sh tailscale`, puis ouvre le lien affiché et
   connecte-toi à ton compte Tailscale.
2. Une seule fois, sur https://login.tailscale.com/admin/machines, menu **…** de l'hôte Proxmox :
   - **Edit route settings** → coche `192.168.2.0/24` ;
   - **Disable key expiry** (sinon il faudrait le reconnecter tous les six mois).
3. Installe Tailscale sur ton PC et ton téléphone (même compte). Sur un PC Linux, active les
   routes : `sudo tailscale up --accept-routes` (Windows, macOS, iPhone et Android le font seuls).

De partout, tu as alors l'interface Proxmox (https://192.168.2.133:8006), `ssh mc`,
`./outils.sh` et `./deploy.sh`, comme à la maison.

## 5 bis. Discord (facultatif)

Pour relier le tchat du jeu à un salon Discord : crée le bot et remplis `discord_token`
(secrets.yml) et `discord_salon` (config.yml) en suivant la section « Discord » du
[README](README.md), puis `./deploy.sh --tags serveur`.

## 6. Connecter le compte Xbox du serveur (consoles)

Crée d'abord un compte **dédié** sur https://www.xbox.com, jamais le tien : le serveur
accepte automatiquement tous ceux qui l'ajoutent en ami et reste « en ligne » en permanence.
Un compte **adulte** (un compte enfant a des restrictions qui bloquent les amis et le
multijoueur), avec un gamertag qui ressemble au serveur (par ex. « LQDM Serveur »).

```bash
./outils.sh xbox
```

Dans une fenêtre de navigation **privée** (pour ne pas utiliser ton compte perso déjà connecté),
ouvre https://www.microsoft.com/link, entre le code et connecte-toi avec le **compte dédié**.
Code expiré, ou mauvais compte connecté ? `./outils.sh xbox nouveau` déconnecte le compte
actuel et donne un nouveau code.
Mets ensuite son gamertag dans `gamertag: ""` de `docs/_config.yml` (le site l'affichera aux
joueurs console).

## 7. Préparer le monde et les joueurs

```bash
./outils.sh cmd smp "worldborder set 6000"
./outils.sh cmd smp "chunky radius 3000"
./outils.sh cmd smp "chunky start"          # pré-génère le SMP (contre le lag)

./outils.sh whitelist UnPseudoJava          # ajoute un joueur Java
./outils.sh whitelist .UnGamertag           # ajoute un joueur Bedrock (avec le point)
```

La liste blanche ne bloque personne tant que `liste_blanche: false` dans `config.yml` (le
serveur est ouvert à tous). Les joueurs ajoutés restent enregistrés pour le jour où tu la
mets à `true` (puis `./deploy.sh --tags serveur`).

## 8. Tester

- [ ] `./outils.sh etat` : tous les conteneurs sont `running` / `healthy`.
- [ ] `./outils.sh nethernet` : la signalisation est démarrée, en HTTPS, et annonce ton IP
      publique et 192.168.2.134.
- [ ] **PC** : launcher depuis https://qcsmp.mekhorizon.org → Jouer → tu arrives au spawn.
- [ ] **Téléphone** : Serveurs → Ajouter → `mc.qcsmp.mekhorizon.org`, port `19132`.
- [ ] **Console** (Bedrock 26.60, donc NetherNet) : ajoute le compte du serveur en ami →
      onglet Amis → Rejoindre, sur Xbox, PlayStation et Switch. Teste aussi avec un
      **compte enfant** si des jeunes jouent sur console (voir le site).
- [ ] **Un joueur de la maison** (même réseau que le serveur) se connecte aussi.
- [ ] **Tailscale** : depuis le téléphone en 4G/5G (Wi-Fi coupé), ouvre https://192.168.2.133:8006.

Quand les tests console passent, publie le guide joueurs (le site l'affiche déjà).

## Au quotidien

| Besoin | Commande |
| --- | --- |
| Voir l'état | `./outils.sh etat` |
| Console d'un serveur | `./outils.sh console smp` |
| Journal en direct | `./outils.sh logs proxy` |
| Instantané avant un tournage | `./outils.sh snapshot` |
| Mettre à jour Paper, Geyser, plugins | `./outils.sh maj` |
| Appliquer un changement de `config.yml` | `./deploy.sh --tags serveur` |
| État de Tailscale | `./outils.sh tailscale` |
| Shell sur la VM | `ssh mc` |
