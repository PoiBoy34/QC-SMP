# Le site LQDM

https://qcsmp.mekhorizon.org, publié par GitHub Pages depuis ce dossier. GitHub le construit
avec Jekyll à chaque push sur `main` : il suffit de modifier un fichier (même directement sur
github.com) et le site se met à jour en une minute environ.

| Page | Fichier |
|---|---|
| Accueil | `index.html` |
| Jouer (téléchargement du launcher, consoles, téléphones) | `jouer/index.html` |
| Nouvelles | `nouvelles/index.html` + un fichier par nouvelle dans `_posts/` |
| Wiki | `wiki/index.html` + un fichier par article dans `_wiki/` |
| Support, Recrutement, Voter | `support/`, `recrutement/`, `voter/` |
| Menu du haut, pied de page | `_includes/entete.html`, `_includes/pied.html` |
| Couleurs et mise en page | `assets/css/site.css` |

## Les réglages

En bas de `_config.yml` : adresse du serveur, port Bedrock, lien Discord, pseudo à contacter,
gamertag du compte Xbox du serveur, recrutement ouvert ou fermé, sites de vote. Toutes les pages
les reprennent.

- **gamertag** : dès que le compte Xbox du serveur existe, mets son nom ici ; la page Jouer et le
  wiki l'affichent aux joueurs console.
- **votes** : l'onglet *Voter* apparaît dans le menu dès qu'un site y est listé.

## Publier une nouvelle

Crée un fichier dans `_posts/` nommé `AAAA-MM-JJ-titre-court.md` (le nom donne l'adresse de la page) :

```markdown
---
title: "Soirée mini-jeux samedi !"
date: 2026-11-07 10:00:00 -0500
categorie: Événement
image: /assets/img/nouvelles/soiree.jpg
description: "Rendez-vous samedi à 19 h pour une soirée mini-jeux."
---
Le texte de la nouvelle, en **Markdown**.

## Un intertitre

- une liste
- [un lien](/jouer/)
```

- `categorie` : `Annonce`, `Mise à jour` ou `Événement` (la liste est dans `_data/nouvelles.yml`).
- `image` : facultative, idéalement 1200×630. Sans image, la carte prend l'aperçu du site.
- Une date dans le futur n'apparaît pas tout de suite : GitHub ne publie que les nouvelles déjà passées.
- Mets `title` et `description` entre guillemets : un « : » sans guillemets casse la page.

## Ajouter un article au wiki

Crée un fichier dans `_wiki/`, par exemple `_wiki/elytres.md` (adresse : `/wiki/elytres/`) :

```markdown
---
title: "Trouver des élytres"
categorie: Le serveur
ordre: 5
description: "Où et comment trouver des élytres sur la survie."
---
Le texte de l'article, en Markdown.
```

- `categorie` : une des catégories de `_data/wiki.yml` (tu peux en ajouter une, avec sa couleur et son icône).
- `ordre` : la position de l'article dans sa catégorie.
- `populaire: 9` (facultatif) : l'article apparaît dans « Articles les plus lus », dans cet ordre.

La recherche du wiki trouve les nouveaux articles toute seule.

## Les images

`assets/img/` contient les images générées pour le site (l'île du haut de l'accueil, les icônes
du wiki, les couvertures des nouvelles) : remplace-les par de vraies captures du serveur quand
tu en auras, avec le même nom de fichier. Le drapeau et les fleurs de lys viennent du fleurdelisé
officiel (domaine public), le logo Discord est le logo officiel.

## Tester avant de pousser (facultatif)

```bash
gem install jekyll -v 3.10.0 && gem install jekyll-sitemap kramdown-parser-gfm webrick
jekyll serve --source docs     # puis http://localhost:4000
```
