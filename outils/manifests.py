#!/usr/bin/env python3
"""
Génère les manifests que lit le launcher (nom, URL et sha1 de chaque fichier) :
  - fichiers résolus sur Modrinth (modrinth.lock.json) : téléchargés depuis cdn.modrinth.com ;
  - fichiers déposés à la main dans mods/, datapacks/, shaderpacks/, resourcepacks/ :
    servis depuis ce dépôt GitHub (un .jar de plus de 100 Mo se découpe en .part00, .part01…).
Met aussi à jour servers.dat (adresse du serveur) et le defaults_sha1 du catalog.json.
Lancé par update_manifest.sh. Bibliothèque standard Python uniquement.
"""
import hashlib
import json
import pathlib
import re
import struct
import sys
import urllib.parse

RACINE = pathlib.Path(__file__).resolve().parent.parent
DOSSIERS = {  # dossier → champ du catalog.json qui donne l'URL de son manifest
    'mods': 'manifest_url',
    'datapacks': 'datapacks_manifest_url',
    'shaderpacks': 'shaderpacks_manifest_url',
    'resourcepacks': 'resourcepacks_manifest_url',
}


def sha1(chemin):
    h = hashlib.sha1()
    with open(chemin, 'rb') as f:
        for bloc in iter(lambda: f.read(1 << 20), b''):
            h.update(bloc)
    return h.hexdigest()


def ecrire_si_change(chemin, contenu):
    donnees = contenu.encode('utf-8') if isinstance(contenu, str) else contenu
    if chemin.exists() and chemin.read_bytes() == donnees:
        return False
    chemin.write_bytes(donnees)
    return True


def servers_dat(nom, adresse):
    """servers.dat (NBT non compressé) avec une seule entrée : le serveur du pack."""
    def chaine(s):
        b = s.encode('utf-8')
        return struct.pack('>H', len(b)) + b

    entree = (b'\x08' + chaine('name') + chaine(nom)
              + b'\x08' + chaine('ip') + chaine(adresse)
              + b'\x01' + chaine('acceptTextures') + b'\x01'   # accepte le resource pack du serveur
              + b'\x00')
    liste = b'\x09' + chaine('servers') + b'\x0a' + struct.pack('>i', 1) + entree
    return b'\x0a' + chaine('') + liste + b'\x00'


def traiter_pack(pack):
    m = re.search(r'^(.*)/(modpacks/[^/]+)/manifest\.json$', pack['manifest_url'])
    if not m:
        sys.exit("manifest_url du catalog.json ne pointe pas vers modpacks/<pack>/manifest.json")
    url_base, rel = m.group(1) + '/' + m.group(2), m.group(2)
    dossier_pack = RACINE / rel
    print(f"📦 {pack['name']} ({rel})")

    chemin_lock = dossier_pack / 'modrinth.lock.json'
    lock = json.loads(chemin_lock.read_text(encoding='utf-8')) if chemin_lock.exists() else {}

    for dossier, champ in DOSSIERS.items():
        if not pack.get(champ):
            continue
        fichiers = [{'name': e['name'], 'url': e['url'], 'sha1': e['sha1']} for e in lock.get(dossier, [])]
        local = dossier_pack / dossier
        if local.is_dir():
            for f in sorted(local.iterdir()):
                if f.is_file() and not f.name.startswith('.'):
                    fichiers.append({'name': f.name,
                                     'url': f"{url_base}/{dossier}/{urllib.parse.quote(f.name)}",
                                     'sha1': sha1(f)})
        noms = [f['name'] for f in fichiers]
        doublons = sorted({n for n in noms if noms.count(n) > 1})
        if doublons:
            sys.exit(f"❌ {dossier} : {', '.join(doublons)} à la fois dans la liste Modrinth et déposé à la main")
        manifest = {'version': pack.get('version', '1.0.0'), 'files': fichiers}
        nom_manifest = pack[champ].rsplit('/', 1)[1]
        change = ecrire_si_change(dossier_pack / nom_manifest,
                                  json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
        print(f"   {nom_manifest} : {len(fichiers)} fichier(s){' (mis à jour)' if change else ''}")

    if pack.get('servers_dat_url') and pack.get('server_host'):
        if ecrire_si_change(dossier_pack / 'servers.dat', servers_dat(pack['name'], pack['server_host'])):
            print(f"   servers.dat → {pack['server_host']}")

    defaults = dossier_pack / 'defaults.zip'
    if defaults.exists() and pack.get('defaults_url'):
        empreinte = sha1(defaults)
        if pack.get('defaults_sha1') != empreinte:
            pack['defaults_sha1'] = empreinte
            print(f'   defaults.zip sha1 : {empreinte}')
            return True
    return False


def main():
    chemin_catalog = RACINE / 'catalog.json'
    catalog = json.loads(chemin_catalog.read_text(encoding='utf-8'))
    if any([traiter_pack(p) for p in catalog['modpacks']]):
        chemin_catalog.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('✅ Manifests à jour')


if __name__ == '__main__':
    main()
