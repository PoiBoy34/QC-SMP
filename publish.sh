#!/usr/bin/env bash
# ===========================================================================
# publish.sh — à lancer après avoir modifié mods.txt / shaders.txt / resourcepacks.txt,
# ajouté / retiré des fichiers dans modpacks/<pack>/mods (datapacks, shaderpacks,
# resourcepacks), ou modifié contenu/ (items, menus).
#
#     ./publish.sh                           message de commit par défaut
#     ./publish.sh "ajout de Xaero"          message personnalisé
#     ./publish.sh --maj "mise à jour"       toutes les versions à jour
#     ./publish.sh --minecraft 26.2 "26.2"   changement de version de Minecraft
#
# Il résout les listes Modrinth, régénère les manifests (sha1 + URL) puis pousse.
# Les joueurs récupèrent la mise à jour au lancement suivant, sans réinstaller le launcher.
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"

OPTIONS=()
while [[ ${1:-} == --* ]]; do
    case $1 in
        --minecraft) OPTIONS+=("$1" "${2:?version manquante après --minecraft}"); shift 2 ;;
        *)           OPTIONS+=("$1"); shift ;;
    esac
done

# GitHub refuse tout fichier de plus de 100 Mo dans un dépôt.
BIG=$(find modpacks -type f -size +99M 2>/dev/null || true)
if [ -n "$BIG" ]; then
    echo "❌ Fichiers trop gros pour GitHub (>99 Mo) :"
    echo "$BIG" | sed 's/^/   /'
    echo
    echo "Découpe-les — le launcher réassemble les .partXX tout seul :"
    echo '   split -b 90M -d -a 2 "modpacks/PACK/mods/gros.jar" "modpacks/PACK/mods/gros.jar.part"'
    echo '   rm "modpacks/PACK/mods/gros.jar"'
    echo "…puis relance ./publish.sh"
    exit 1
fi

python3 outils/modrinth.py ${OPTIONS[@]+"${OPTIONS[@]}"}
python3 outils/contenu.py
./update_manifest.sh

if [ -z "$(git status --porcelain)" ]; then
    echo "Rien de nouveau à publier."
    exit 0
fi

git add -A
echo
git status --short
git commit -q -m "${1:-modpack : mise à jour du contenu}"
git push
echo
echo "✅ Publié. Les joueurs l'auront au prochain lancement du launcher."
