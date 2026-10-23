---
title: "Windows bloque le launcher"
categorie: Dépannage
ordre: 1
populaire: 7
description: "« Windows a protégé votre ordinateur », téléchargement bloqué, antivirus : que faire."
---
C'est **normal** et ce n'est pas un virus. Windows et les navigateurs affichent ces avertissements
pour **tout** programme qui n'a pas encore été installé par des milliers de personnes. Le launcher
est un projet d'ici : il n'a pas encore cette réputation.

## « Windows a protégé votre ordinateur » (écran bleu)

1. Clique sur **Informations complémentaires**.
2. Puis sur **Exécuter quand même**.

## Chrome ou Edge bloque le téléchargement

- Clique sur les trois points (ou la flèche) à côté du fichier dans les téléchargements.
- Choisis **Conserver**, puis **Conserver quand même**.

## L'antivirus met le fichier en quarantaine

C'est un faux positif (Avast, Norton, McAfee…) : restaure le fichier depuis la quarantaine et
ajoute une exception pour le dossier d'installation du launcher.

## Pour les curieux : vérifier le fichier

Le code du launcher est public sur [GitHub](https://github.com/{{ site.lqdm.depot }}), et le
fichier est fabriqué automatiquement à partir de ce code. Tu peux comparer son empreinte avec
celle indiquée sur la [page des versions](https://github.com/{{ site.lqdm.depot }}/releases), dans
PowerShell :

```powershell
Get-FileHash .\LQDM-Launcher-Setup-x.x.x.exe -Algorithm SHA256
```
