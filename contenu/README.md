# Contenu custom : items, menus et commandes

Le contenu fait maison du serveur, décrit **une seule fois** ici. `outils/contenu.py`
en tire tout ce qu'il faut pour Java **et** pour Bedrock (consoles, téléphones). Aucun mod :

- un **item custom** est un item vanilla avec sa propre texture (resource pack) ;
- les **menus** sont des *dialogs* vanilla : un bouton **LQDM** dans le menu Échap, comme sur DonutSMP ;
- Geyser traduit les deux pour Bedrock : vrais items Bedrock, menus en formulaires.

| Chemin | Rôle |
|---|---|
| `items/<id>.json` + `items/<id>.png` | Un item custom : sa description et sa texture |
| `menus.json` | Les menus : le bouton du menu Échap, `/menu` et leurs sous-menus |
| `skript/` | Les commandes du réseau (`/menu`, `/spawn`, `/smp`…) |
| `generes/` | Fabriqué par `outils/contenu.py` : **ne pas modifier à la main** |

## Publier un changement

Modifie les fichiers (même directement sur github.com), puis *Commit changes*.
Le workflow **Mods et contenu** génère les packs et les pousse :

- **joueurs Java** : le launcher installe le nouveau pack au lancement suivant ;
- **serveur** (menus, items Bedrock, commandes) : au prochain `./deploy.sh --tags serveur`
  (dans `serveur/`). Les serveurs dont les menus ont changé redémarrent, les scripts se rechargent à chaud.

Depuis ton PC : `./publish.sh "nouveau menu"` fait la même chose.
Pour vérifier sans rien pousser : `python3 outils/contenu.py`. En cas d'erreur, le message
dit quel fichier corriger et pourquoi.

## Ajouter un item

1. Crée `items/<id>.json` (nom de fichier en minuscules, chiffres et `_`), par exemple `items/sirop_erable.json` :

   ```json
   {
     "nom": "Sirop d'érable",
     "description": ["Tout droit de la cabane à sucre."],
     "nourriture": { "faim": 4, "saturation": 6, "animation": "drink" },
     "pile_max": 16
   }
   ```

2. Dépose sa texture à côté : `items/sirop_erable.png`, carrée, **16×16** pixels de préférence.
3. Publie (voir plus haut).
4. Donne-le en jeu, depuis `serveur/` : `./outils.sh donner Pseudo sirop_erable 3`.
   Dans un script Skript : `donnerItemLQDM(player, "sirop_erable", 3)`.

| Clé | Obligatoire | Exemple | Effet |
|---|---|---|---|
| `nom` | oui | `"Poutine"` | Nom affiché |
| `base` | non (`minecraft:paper`) | `"minecraft:stick"` | Item vanilla de départ |
| `type` | non (`objet`) | `"outil"` | `outil` : tenu en main comme une épée |
| `description` | non | `["Ligne 1", "Ligne 2"]` | Lignes grises sous le nom |
| `brillant` | non | `true` | Effet « enchanté » |
| `pile_max` | non | `16` | Taille d'une pile, de 1 à 99 (sinon celle de l'item de base) |
| `durabilite` | non | `250` | Barre d'usure (l'item ne s'empile plus) |
| `nourriture` | non | `{ "faim": 8, "saturation": 12.8 }` | L'item se mange |

Dans `nourriture` :

| Clé | Par défaut | Effet |
|---|---|---|
| `faim` | 0 | Points de faim rendus : 2 = une cuisse, 20 = la barre pleine |
| `saturation` | 0 | Combien de temps la faim tient |
| `toujours` | `false` | `true` : se mange même sans avoir faim |
| `duree` | 1.6 | Secondes pour le manger |
| `animation` | `eat` | `eat`, `drink`, `block`, `bow`, `spear`, `crossbow`, `spyglass` ou `none` |

Ce qu'un item custom **ne peut pas** faire :

- être un **bloc** qu'on pose, ou un **mob** : ça demanderait un mod côté Java ;
- avoir un **pouvoir** tout seul : un clic droit spécial se programme en Skript sur le serveur
  (`on right click` + vérifier le nom de l'item).

Les joueurs Java qui n'utilisent pas le launcher reçoivent la texture du serveur à la
connexion (il la leur propose). Les joueurs Bedrock la reçoivent par Geyser.

## Les menus (bouton du menu Échap)

`menus.json` contient des menus nommés. Celui qui s'appelle `menu` est le principal :

- **Java** : bouton **LQDM** dans le menu Échap, ou `/menu` ;
- **Bedrock** : `/menu`, ou la boussole du spawn (`/geyser quickactions` marche aussi).

```json
"homes": {
  "titre": "Homes",
  "texte": "Tes points de retour sur le SMP.",
  "colonnes": 2,
  "boutons": [
    { "texte": "Mes homes", "icone": "oak_door", "commande": "homes" },
    { "texte": "Créer un home ici", "icone": "name_tag", "commande": "sethome" }
  ]
}
```

Un menu : `titre` (obligatoire), `texte` (une ligne ou une liste de lignes), `colonnes`
(2 par défaut), `boutons`. Un menu sans boutons affiche juste son texte (comme `regles`).
Chaque sous-menu a un bouton **Retour** vers le menu principal.

Un bouton : `texte` (obligatoire), `icone` (un item vanilla : `ender_pearl`, `oak_door`…,
affiché sur Java seulement), `info` (bulle au survol), `largeur`, et **une seule** action :

| Action | Exemple | Effet |
|---|---|---|
| `commande` | `"rtp"` | Lance la commande, comme si le joueur la tapait (sans `/`) |
| `suggerer` | `"tpa "` | Écrit la commande dans le chat : le joueur complète (un pseudo) et valide |
| `menu` | `"homes"` | Ouvre un autre menu de `menus.json` |
| `lien` | `"https://discord.gg/EQyXcrG2hA"` | Ouvre un lien (`https://` seulement) |
| `copier` | `"mc.qcsmp.mekhorizon.org"` | Copie le texte dans le presse-papiers |

Un bouton `commande` n'a pas plus de droits que le joueur : une commande d'admin ne
marchera que pour les admins.

## Les commandes du réseau (`skript/`)

| Commande | Où | Effet |
|---|---|---|
| `/menu` (`/m`) | partout | Ouvre le menu |
| `/spawn` (`/hub`, `/lobby`) | partout | Retour au spawn |
| `/smp` (`/survie`) | partout | Va sur le serveur de survie |
| `/games` (`/jeux`) | partout | Menu des mini-jeux |
| `/rules` (`/regles`) | partout | Les règles |
| `/rtp`, `/home`, `/homes`, `/sethome`, `/delhome`, `/tpa`, `/tpahere`, `/tpaccept`, `/tpdeny`, `/back` | SMP | Fournies par HuskHomes. Tapées ailleurs, elles emmènent le joueur sur le SMP |

| Fichier | Installé sur |
|---|---|
| `tous.sk` | tous les serveurs |
| `spawn.sk` | le spawn (`/spawn` local, boussole du menu dans la barre) |
| `pas-spawn.sk` | tous sauf le spawn (`/spawn` renvoie au spawn) |
| `pas-smp.sk` | tous sauf le SMP (les commandes de survie emmènent sur le SMP) |

Un nouveau fichier `.sk` ici doit aussi être ajouté dans `serveur/tasks/minecraft.yml`
(tâche « scripts à installer selon le serveur »), pour choisir sur quels serveurs il va.
