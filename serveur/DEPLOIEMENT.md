# Déployer le serveur : mini guide

Du Proxmox vide au premier joueur connecté, environ une heure. Les détails et le
dépannage sont dans le [README](README.md).

## Avant de commencer

- [ ] Un PC sous **Linux, macOS ou Windows avec WSL** (sur Windows : installe Ubuntu
      depuis le Microsoft Store et fais tout dedans).
- [ ] **git** et **Ansible** sur ce PC : `sudo apt install git ansible`
      (macOS : `brew install ansible`).
- [ ] L'**IP de ton Proxmox** et son **mot de passe root**.
- [ ] Une **IP libre** sur ton réseau pour la VM, hors de la plage DHCP du routeur
      (ex. `192.168.1.50`).
- [ ] Un **jeton Cloudflare** : My Profile → API Tokens → Create Token → modèle
      *Edit zone DNS*, limité à la zone `mekhorizon.org`.
- [ ] Un **compte Microsoft dédié** au serveur (pas le tien), pour la méthode « Ami » des consoles.

## 1. Récupérer le projet

```bash
git clone https://github.com/PoiBoy34/QC-SMP.git
cd QC-SMP/serveur
```

## 2. Remplir la config

Dans `config.yml`, change au minimum :

```yaml
proxmox_ip: "192.168.1.10"   # ton Proxmox
vm_ip: "192.168.1.50"        # l'IP libre pour la VM
admins_java: ["TonPseudo"]   # ton pseudo Java : op + liste blanche
```

Vérifie aussi que `vm_id: 250` est libre dans Proxmox, et que `vm_memory_mb: 12288`
(12 Go) laisse assez de mémoire au reste de ton Proxmox.

Puis le jeton (ce fichier n'est jamais envoyé sur GitHub) :

```bash
cp secrets.yml.exemple secrets.yml
nano secrets.yml        # colle le jeton dans cloudflare_api_token
```

## 3. Lancer le déploiement

```bash
./deploy.sh
```

- Il demande le **mot de passe root de Proxmox une seule fois**, puis tout se fait par clé SSH.
- Compte **10 à 20 minutes** : création de la VM, sécurité, Docker, téléchargement
  de Paper, Velocity et Geyser.
- À la fin, un **résumé** s'affiche : les ports à ouvrir, l'état NetherNet et le code Xbox.

## 4. Ouvrir les ports sur le routeur

Redirige vers l'IP de la VM :

| Port | Protocole |
| --- | --- |
| 25565 | TCP |
| 19132 | **TCP et UDP** |
| 19133 | UDP |
| 19140 à 19149 | UDP |

Vérifie que l'IP WAN affichée par le routeur est la même que celle que donne
`curl -4 ifconfig.me`. Si le routeur affiche 100.64.x.x ou 10.x.x.x, ton FAI te met
derrière un CGNAT et les redirections ne marcheront pas.

## 5. Connecter le compte Xbox du serveur

```bash
./outils.sh xbox
```

Ouvre https://www.microsoft.com/link, entre le code et connecte-toi avec le **compte dédié**.
Mets ensuite son gamertag dans `gamertag: ''` en haut du script de `docs/index.html`
(le site l'affichera aux joueurs console).

## 6. Préparer le monde et les joueurs

```bash
./outils.sh cmd smp "worldborder set 6000"
./outils.sh cmd smp "chunky radius 3000"
./outils.sh cmd smp "chunky start"          # pré-génère le SMP (contre le lag)

./outils.sh whitelist UnPseudoJava          # ajoute un joueur Java
./outils.sh whitelist .UnGamertag           # ajoute un joueur Bedrock (avec le point)
```

## 7. Tester

- [ ] `./outils.sh etat` : tous les conteneurs sont `running` / `healthy`.
- [ ] `./outils.sh nethernet` : la signalisation est démarrée.
- [ ] **PC** : launcher depuis https://qcsmp.mekhorizon.org → Jouer → tu arrives au spawn.
- [ ] **Téléphone** : Serveurs → Ajouter → `mc.qcsmp.mekhorizon.org`, port `19132`.
- [ ] **Console** : ajoute le compte du serveur en ami → onglet Amis → Rejoindre.
- [ ] **Après le 27 octobre** (Bedrock 26.60 / NetherNet) : refais les tests console sur
      Xbox, PlayStation et Switch avant de publier le guide joueurs.

## Au quotidien

| Besoin | Commande |
| --- | --- |
| Voir l'état | `./outils.sh etat` |
| Console d'un serveur | `./outils.sh console smp` |
| Journal en direct | `./outils.sh logs proxy` |
| Instantané avant un tournage | `./outils.sh snapshot` |
| Mettre à jour Paper, Geyser, plugins | `./outils.sh maj` |
| Appliquer un changement de `config.yml` | `./deploy.sh --tags serveur` |
| Shell sur la VM | `ssh mc` |
