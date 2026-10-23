#!/usr/bin/env python3
"""
Résout les listes Modrinth du pack (mods.txt, shaders.txt, resourcepacks.txt) pour la
version de Minecraft et le loader du catalog.json, dépendances obligatoires comprises,
et écrit modpacks/<pack>/modrinth.lock.json. update_manifest.sh en tire ensuite les
manifests que lit le launcher.

  python3 outils/modrinth.py                     ajoute / retire selon les listes, sans
                                                 toucher aux versions déjà choisies
  python3 outils/modrinth.py --maj               passe tout à la dernière version compatible
  python3 outils/modrinth.py --minecraft 26.2    change de version de Minecraft (tout est refait)
  python3 outils/modrinth.py --minecraft latest  prend la version la plus récente que tous
                                                 les mods obligatoires supportent

Les fichiers ne sont pas copiés dans le dépôt : le launcher les télécharge directement
depuis cdn.modrinth.com et vérifie leur sha1. Bibliothèque standard Python uniquement.
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

RACINE = pathlib.Path(__file__).resolve().parent.parent
API = 'https://api.modrinth.com/v2'
FABRIC_META = 'https://meta.fabricmc.net/v2'
UA = 'PoiBoy34/QC-SMP (outils/modrinth.py)'

# liste → (clé du lock et dossier, type de projet Modrinth, loaders, version MC obligatoire, dépendances)
LISTES = {
    'mods.txt':          ('mods',          'mod',          None,                 True,  True),
    'shaders.txt':       ('shaderpacks',   'shader',       ['iris', 'optifine'], False, False),
    'resourcepacks.txt': ('resourcepacks', 'resourcepack', ['minecraft'],        False, False),
}

resume = []   # lignes du récapitulatif (terminal + page du workflow GitHub)


def erreur(msg):
    print('❌ ' + msg, file=sys.stderr)
    resume.append('❌ ' + msg)
    ecrire_resume()
    sys.exit(1)


def note(msg):
    print(msg)
    resume.append(msg)


def ecrire_resume():
    chemin = os.environ.get('GITHUB_STEP_SUMMARY')
    if chemin and resume:
        with open(chemin, 'a', encoding='utf-8') as f:
            f.write('### Mods Modrinth\n\n' + '\n'.join('- ' + l for l in resume) + '\n')


def get(url, params=None):
    """GET JSON avec reprises. None si la ressource n'existe pas (400/404)."""
    if params:
        url += '?' + urllib.parse.urlencode(
            {k: json.dumps(v) if isinstance(v, list) else v for k, v in params.items()})
    for essai in range(6):
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            if e.code == 429 or e.code >= 500:
                time.sleep(int(e.headers.get('Retry-After') or 0) or 2 ** essai)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** essai)
    erreur('injoignable : ' + url)


def lire_liste(chemin):
    entrees = []
    for n, ligne in enumerate(chemin.read_text(encoding='utf-8').splitlines(), 1):
        ligne = ligne.split('#', 1)[0].strip()
        if not ligne:
            continue
        version = None
        if '==' in ligne:
            ligne, version = (x.strip() for x in ligne.split('==', 1))
        optionnel = ligne.endswith('?')
        nom = ligne.rstrip('?').strip().lower()
        if not re.fullmatch(r'[a-z0-9_.-]+', nom):
            erreur(f'{chemin.name}, ligne {n} : « {ligne} » n\'est pas un nom Modrinth valide')
        entrees.append({'nom': nom, 'optionnel': optionnel, 'version': version, 'ligne': n})
    return entrees


def fichier_principal(v):
    f = next((f for f in v['files'] if f.get('primary')), v['files'][0])
    return {'name': f['filename'], 'url': f['url'], 'sha1': f['hashes']['sha1'], 'size': f['size']}


def choisir_version(projet, pin, loaders, mc, mc_obligatoire):
    """Version figée si demandée, sinon la plus récente « release » (puis beta, puis alpha)."""
    if pin:
        return get(f"{API}/project/{projet['id']}/version/{urllib.parse.quote(pin)}")
    params = {'loaders': loaders, 'include_changelog': 'false'}
    versions = get(f"{API}/project/{projet['id']}/version", {**params, 'game_versions': [mc]}) or []
    if not versions and not mc_obligatoire:
        # shaders et resource packs annoncent rarement chaque version de Minecraft
        versions = get(f"{API}/project/{projet['id']}/version", params) or []
    for type_ in ('release', 'beta', 'alpha'):
        for v in versions:          # Modrinth renvoie du plus récent au plus ancien
            if v['version_type'] == type_:
                return v
    return None


def dependances_obligatoires(v):
    ids = set()
    for d in v.get('dependencies', []):
        if d.get('dependency_type') != 'required':
            continue
        if d.get('project_id'):
            ids.add(d['project_id'])
        elif d.get('version_id'):
            dv = get(f"{API}/version/{d['version_id']}")
            if dv:
                ids.add(dv['project_id'])
    return sorted(ids)


def resoudre(liste, cle, type_projet, loaders, mc, mc_obligatoire, avec_deps, anciens):
    anciens = {e['projet']: e for e in anciens}
    a_traiter = []
    for r in lire_liste(liste):
        projet = get(f"{API}/project/{r['nom']}")
        if not projet:
            erreur(f"{liste.name}, ligne {r['ligne']} : « {r['nom']} » n'existe pas sur Modrinth")
        if projet['project_type'] != type_projet:
            note(f"⚠️ {r['nom']} est un projet « {projet['project_type']} », pas « {type_projet} »")
        a_traiter.append((projet, False, r['version'], r['optionnel'], None))

    retenus = {}
    while a_traiter:
        projet, auto, pin, optionnel, parent = a_traiter.pop(0)
        if projet['id'] in retenus:
            if not auto:
                retenus[projet['id']]['auto'] = False
            continue
        ancien = anciens.get(projet['id'])
        if ancien and (pin is None or pin in (ancien['version'], ancien['version_id'])):
            entree = dict(ancien, auto=auto)                # version déjà choisie : on n'y touche pas
        else:
            v = choisir_version(projet, pin, loaders, mc, mc_obligatoire)
            if not v:
                quoi = f"{projet['slug']}" + (f" (requis par {parent})" if parent else '')
                if optionnel:
                    note(f"⚠️ {quoi} : rien pour Minecraft {mc}, ignoré (optionnel)")
                    continue
                erreur(f"{quoi} : aucune version pour Minecraft {mc} ({', '.join(loaders)}). "
                       f"Retire-le, marque-le optionnel avec « ? », ou change de version de Minecraft.")
            entree = {'slug': projet['slug'], 'titre': projet['title'], 'projet': projet['id'],
                      'version': v['version_number'], 'version_id': v['id'], **fichier_principal(v),
                      'requiert': dependances_obligatoires(v) if avec_deps else [], 'auto': auto}
            avant = f" (avant : {ancien['version']})" if ancien else ''
            note(f"{'➕' if not ancien else '⬆️'} {entree['titre']} {entree['version']}{avant}"
                 + (' — dépendance' if auto else ''))
        retenus[projet['id']] = entree
        for dep in entree['requiert']:
            if dep not in retenus:
                dep_projet = get(f'{API}/project/{dep}')
                if dep_projet:
                    a_traiter.append((dep_projet, True, None, False, projet['slug']))

    for pid, e in anciens.items():
        if pid not in retenus:
            note(f"➖ {e['titre']} retiré")
    return sorted(retenus.values(), key=lambda e: e['slug'])


def fabric_loader(mc):
    data = get(f'{FABRIC_META}/versions/loader/{urllib.parse.quote(mc)}') or []
    stables = [d['loader']['version'] for d in data if d['loader'].get('stable')]
    return stables[0] if stables else (data[0]['loader']['version'] if data else None)


def minecraft_le_plus_recent(liste, loader):
    """Plus récente version « release » de Minecraft que tous les mods obligatoires supportent."""
    tags = get(f'{API}/tag/game_version') or []
    releases = [t['version'] for t in sorted(tags, key=lambda t: t['date'], reverse=True)
                if t['version_type'] == 'release']
    supports = []
    for r in lire_liste(liste):
        if r['optionnel']:
            continue
        projet = get(f"{API}/project/{r['nom']}") or erreur(f"« {r['nom']} » n'existe pas sur Modrinth")
        versions = get(f"{API}/project/{projet['id']}/version", {'loaders': [loader]}) or []
        supports.append((r['nom'], {g for v in versions for g in v['game_versions']}))
    for mc in releases:
        if all(mc in jeux for _, jeux in supports) and fabric_loader(mc):
            return mc
    erreur('aucune version de Minecraft n\'est supportée par tous les mods obligatoires')


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--maj', action='store_true', help='tout passer à la dernière version compatible')
    p.add_argument('--minecraft', help='nouvelle version de Minecraft, ou « latest »')
    args = p.parse_args()

    chemin_catalog = RACINE / 'catalog.json'
    catalog = json.loads(chemin_catalog.read_text(encoding='utf-8'))
    pack = catalog['modpacks'][0]
    m = re.search(r'/(modpacks/[^/]+)/manifest\.json', pack['manifest_url'])
    if not m:
        erreur('manifest_url du catalog.json ne pointe pas vers modpacks/<pack>/manifest.json')
    dossier = RACINE / m.group(1)
    loader = pack.get('loader', 'fabric').lower()
    if loader != 'fabric':
        erreur(f"loader « {loader} » : seul Fabric est géré par cet outil")

    mc = args.minecraft or pack['minecraft']
    if mc == 'latest':
        mc = minecraft_le_plus_recent(dossier / 'mods.txt', loader)
        note(f'🎯 Version de Minecraft la plus récente supportée par tous les mods : {mc}')
    loader_version = pack.get('loader_version', 'latest')
    if args.maj or mc != pack['minecraft'] or loader_version == 'latest':
        loader_version = fabric_loader(mc) or erreur(f'Fabric ne supporte pas Minecraft {mc}')

    chemin_lock = dossier / 'modrinth.lock.json'
    lock = json.loads(chemin_lock.read_text(encoding='utf-8')) if chemin_lock.exists() else {}
    tout_refaire = args.maj or lock.get('minecraft') != mc or lock.get('loader') != loader
    if tout_refaire and lock:
        note('🔄 Toutes les versions sont recalculées')

    nouveau = {'_info': 'Généré par outils/modrinth.py à partir des listes .txt : ne pas modifier à la main.',
               'minecraft': mc, 'loader': loader}
    for nom_liste, (cle, type_projet, loaders, mc_obligatoire, avec_deps) in LISTES.items():
        liste = dossier / nom_liste
        if not liste.exists():
            nouveau[cle] = []
            continue
        nouveau[cle] = resoudre(liste, cle, type_projet, loaders or [loader], mc, mc_obligatoire,
                                avec_deps, [] if tout_refaire else lock.get(cle, []))

    if nouveau != lock:
        chemin_lock.write_text(json.dumps(nouveau, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if (pack['minecraft'], pack.get('loader_version')) != (mc, loader_version):
        note(f"🧩 catalog.json : Minecraft {pack['minecraft']} → {mc}, "
             f"Fabric {pack.get('loader_version')} → {loader_version}")
        pack['minecraft'], pack['loader_version'] = mc, loader_version
        chemin_catalog.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    total = sum(len(nouveau[c]) for c, *_ in LISTES.values())
    note(f'✅ Minecraft {mc}, Fabric {loader_version} : {total} fichier(s) Modrinth')
    ecrire_resume()


if __name__ == '__main__':
    main()
