---
title: "Le serveur est-il ouvert à tous ?"
categorie: Pour commencer
ordre: 4
description: "Ouvert à tous ou sur liste blanche : comment entrer sur LQDM."
excerpt_separator: "<!--extrait-->"
---
{% if site.lqdm.liste_blanche -%}
Non : pour l'instant, LQDM est sur **liste blanche**. Seuls les joueurs ajoutés par l'équipe
peuvent entrer. Si le jeu te dit « You are not whitelisted on this server » (« tu n'es pas sur
la liste blanche »), c'est que tu n'y es pas encore.

## Demander à être ajouté

Écris dans le salon **#support** du [Discord]({{ site.lqdm.discord }}), ou envoie un message à
**{{ site.lqdm.contact }}**, en donnant :

- ton **pseudo Java** si tu joues sur PC avec le launcher ;
- ton **gamertag** si tu joues sur console, téléphone ou tablette.

Vérifie bien l'orthographe : une seule lettre de travers et le serveur ne te reconnaîtra pas.
Une fois ajouté, tu peux entrer sur tout le réseau : spawn, survie et mini-jeux.
{%- else -%}
**Oui !** Pour l'instant, LQDM est ouvert à tous : pas d'inscription, pas de liste d'attente.
Suis les étapes de la page [Jouer](/jouer/) et c'est parti.

## Et plus tard ?

Selon le nombre de joueurs, l'équipe pourra activer une **liste blanche** : seuls les joueurs
ajoutés pourraient alors entrer. Si ça arrive, ce sera annoncé dans les
[nouvelles](/nouvelles/) et sur le [Discord]({{ site.lqdm.discord }}), avec la marche à suivre.

En attendant, les [règles](/wiki/regles/) s'appliquent à tout le monde.
{%- endif %}
