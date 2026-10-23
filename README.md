# LQDM-Launcher

Le launcher de **LQDM**, le serveur Minecraft des Québécois (Java + consoles, Fabric).
Tu l'installes une fois, tu te connectes, tu cliques sur **Jouer** : Minecraft,
Fabric, Java et les mods se téléchargent et se mettent à jour tout seuls, puis le
jeu se connecte **directement au serveur**.

## Installation

👉 **https://qcsmp.mekhorizon.org** : la page de téléchargement, avec toutes les étapes.

Ou directement sur GitHub : https://github.com/PoiBoy34/QC-SMP/releases/latest

### Windows
1. Télécharge **`LQDM-Launcher-Setup-x.x.x.exe`**
2. Lance-le et suis l'installation
3. Ouvre **LQDM** depuis le menu Démarrer ou le raccourci bureau

### Linux
1. Télécharge **`LQDM-Launcher-x.x.x.AppImage`**
2. Rends-le exécutable (clic droit → Propriétés → Autoriser l'exécution, ou
   `chmod +x LQDM-Launcher-*.AppImage`)
3. Double-clique dessus

### Sur console (Xbox, PlayStation, Switch), téléphone ou Bedrock Windows
Pas besoin de launcher : tout est expliqué sur https://qcsmp.mekhorizon.org (ajout du compte
du serveur en ami, ou adresse `mc.qcsmp.mekhorizon.org`, port `19132`).

## ⚠️ « Windows a protégé votre ordinateur » / avertissement du navigateur

C'est **normal et attendu**, ce n'est pas un virus. Windows et Chrome affichent
cet avertissement pour **tout** programme téléchargé qui n'a pas encore été
installé par des milliers de personnes. Le launcher est un projet perso : il
n'a pas encore cette réputation, donc l'alerte apparaît.

**Chrome / Edge** — téléchargement bloqué ou marqué comme « rarement
téléchargé » :
- clique sur la flèche à côté du fichier dans la barre de téléchargements ;
- choisis **Conserver** / **Conserver quand même**.

**Windows SmartScreen** — écran bleu « Windows a protégé votre ordinateur » :
- clique sur **Informations complémentaires** ;
- puis sur **Exécuter quand même**.

**Antivirus (Avast, Norton, McAfee…)** — s'il met le fichier en quarantaine,
c'est un faux positif : restaure-le et ajoute une exception pour le dossier
d'installation.

Tu peux vérifier que ton fichier est bien celui publié ici en comparant son
empreinte SHA-256 avec celle indiquée dans la release :

```powershell
Get-FileHash .\LQDM-Launcher-Setup-x.x.x.exe -Algorithm SHA256
```

Le code source est entièrement dans ce dépôt, et les exécutables sont
construits automatiquement par GitHub Actions à partir de ce code.

## Comment ça marche

1. **Connecte-toi** avec ton compte Microsoft (bouton en haut à droite).
2. **Clique sur Jouer.**

Le launcher fait le reste :
- il télécharge les mods (performance et confort seulement : rien qui change le jeu) ;
- il installe la bonne version de Fabric et de Java ;
- il vérifie chaque fichier (sha1), lance le jeu et te connecte au serveur.

Le premier lancement est plus long (téléchargement de Minecraft). Ensuite, seuls
les fichiers manquants ou modifiés sont retéléchargés.

Les shaders sont installés mais éteints : active-les dans
**Options → Options vidéo → Shaders** si ta machine suit.

## Mises à jour

Le launcher se met à jour tout seul : quand une nouvelle version sort, une
bannière apparaît en haut de la fenêtre → **Télécharger**, puis
**Installer & redémarrer**. Tu peux aussi vérifier dans
**⚙️ Paramètres → Launcher → Vérifier les mises à jour**.

## Besoin d'aide ?

Écris dans le salon **#support** du [Discord LQDM](https://discord.gg/EQyXcrG2hA),
ou contacte **poiboy34** sur Discord.

Joins le rapport du launcher : **⚙️ Paramètres → Aide et diagnostic → Copier le
rapport de diagnostic**, puis colle-le dans ton message (Ctrl+V). Il contient tout
ce qu'il faut pour comprendre le problème.

Le Discord du serveur a été créé par **CampFire012**
(son Discord : https://discord.gg/pcQqDzTq2B).

---

# Pour le mainteneur

| Chemin | Rôle |
|---|---|
| `catalog.json` | Description du pack (version de Minecraft, Fabric, adresse du serveur), lue par le launcher |
| `modpacks/LQDM/mods.txt` | **Liste des mods** : un nom Modrinth par ligne |
| `modpacks/LQDM/shaders.txt`, `resourcepacks.txt` | Pareil pour les shaders et les resource packs |
| `modpacks/LQDM/mods/` (et `datapacks/`, `shaderpacks/`, `resourcepacks/`) | Fichiers déposés à la main (ex. le resource pack du serveur) |
| `modpacks/LQDM/modrinth.lock.json` | Versions exactes choisies sur Modrinth (généré) |
| `modpacks/LQDM/*manifest.json`, `servers.dat` | Ce que télécharge le launcher (généré) |
| `contenu/` | Items custom, menus du menu Échap et commandes du réseau, pour Java et Bedrock : voir [contenu/README.md](contenu/README.md) |
| `outils/` | `modrinth.py` (résout les listes), `contenu.py` (génère le contenu custom) et `manifests.py` (génère les manifests) |
| `update_manifest.sh` | Régénère les manifests |
| `publish.sh` | Listes + contenu + manifests + commit + push, en une commande |
| `minecraft-launcher/` | Code du launcher (Electron), basé sur TimeRift-Launcher 2.1.3 |
| `docs/` | Site de téléchargement (https://qcsmp.mekhorizon.org), publié par GitHub Pages |
| `serveur/` | Déploiement du serveur sur Proxmox (Ansible, Docker, Velocity + Geyser) : voir le [mini guide de déploiement](serveur/DEPLOIEMENT.md) |

## Ajouter un mod

Le plus simple, même depuis un téléphone : ouvre `modpacks/LQDM/mods.txt` sur
github.com, ajoute une ligne avec le nom Modrinth du mod (la fin de l'adresse
`modrinth.com/mod/<nom>`), puis *Commit changes*. Le workflow **Mods** trouve la
bonne version, ajoute ses dépendances et publie. Les joueurs l'ont au lancement suivant.

Depuis ton PC :

```bash
echo "xaeros-minimap" >> modpacks/LQDM/mods.txt
./publish.sh "ajout de la minimap"
```

- `nom?` : optionnel, ignoré s'il n'existe pas encore pour la version de Minecraft du pack.
- `nom==1.2.3` : version figée.
- Retirer la ligne retire le mod (et ses dépendances devenues inutiles).

Les fichiers Modrinth ne sont pas copiés dans le dépôt : le launcher les télécharge
directement depuis `cdn.modrinth.com` et vérifie leur sha1. Le dépôt reste léger,
et on ne redistribue pas des fichiers dont la licence l'interdirait.

Un mod qui n'est pas sur Modrinth : dépose le `.jar` dans `modpacks/LQDM/mods/`
puis `./publish.sh`. Un fichier de plus de 100 Mo est refusé par GitHub : découpe-le,
le launcher réassemble les morceaux tout seul :

```bash
split -b 90M -d -a 2 "modpacks/LQDM/mods/gros.jar" "modpacks/LQDM/mods/gros.jar.part"
rm "modpacks/LQDM/mods/gros.jar"
```

Règle du serveur : seulement des mods qui ne changent pas le gameplay, pour rester
à égalité avec les joueurs Bedrock.

## Mettre à jour les mods, changer de version de Minecraft

Ajouter un mod ne met **pas** les autres à jour : les versions ne bougent que quand tu le demandes.

- **Tout mettre à jour** : onglet *Actions* → *Mods* → *Run workflow*, coche
  « Passer tous les mods à leur dernière version » (ou `./publish.sh --maj "maj des mods"`).
- **Changer de version de Minecraft** : même endroit, champ « Nouvelle version de
  Minecraft » (ex. `26.2`), ou `latest` pour la plus récente que tous les mods
  obligatoires supportent (`./publish.sh --minecraft 26.2 "passage en 26.2"`).

⚠️ La version de Minecraft du pack doit correspondre à celle du serveur
(`mc_version` dans la config du serveur). Change les deux en même temps.

## Changer l'adresse du serveur

`server_host` dans `catalog.json`, puis `./publish.sh`. Pas besoin de nouvelle
version du launcher : il relit le catalogue à chaque démarrage. Avec `"quick_play": false`,
le jeu s'ouvre sur le menu au lieu de se connecter directement.

## Publier une version du launcher

Change le numéro de `version` dans `minecraft-launcher/package.json` et pousse sur `main`
(ça marche aussi en modifiant le fichier directement sur github.com). GitHub Actions
construit le `.exe` et l'`.AppImage`, puis publie la release **tout seul** une fois les
5 fichiers présents (`.exe`, `.exe.blockmap`, `latest.yml`, `.AppImage`, `latest-linux.yml`).
Les launchers installés proposent alors la mise à jour, et le site donne la nouvelle version.

```bash
cd minecraft-launcher && npm version 1.0.1 --no-git-tag-version && cd ..
git commit -am "launcher 1.0.1" && git push
gh run watch    # facultatif : suivre le build
```

Pousser un tag `v1.0.1` marche aussi, comme sur TimeRift. Une version déjà publiée
n'est jamais reconstruite.

Si le job *publier* échoue, la release reste en brouillon : vérifie les 5 fichiers
dans l'onglet Releases, puis `gh release edit v1.0.1 --draft=false`. Ne la publie
jamais avant la fin du build Windows : le `.exe` n'aurait plus nulle part où atterrir.

## Visuels

L'icône (`minecraft-launcher/build/icon.png`, 512×512) et le fond
(`minecraft-launcher/src/bg.png`, `assets/`) sont provisoires : remplace-les
par les vrais, même nom de fichier.
