#!/usr/bin/env python3
"""
Contenu custom du serveur, pour Java ET Bedrock :
  - items : contenu/items/<id>.json + <id>.png
  - menus : contenu/menus.json (le bouton « LQDM » du menu Échap, et /menu)

Une seule description, et chaque édition reçoit ce qu'il lui faut :

  modpacks/<pack>/resourcepacks/LQDM-Contenu.zip   pack Java : le launcher l'installe et l'active
  contenu/generes/bedrock/LQDM-Contenu.mcpack       pack Bedrock : Geyser l'envoie à chaque connexion
  contenu/generes/geyser/lqdm.json                  mappings Geyser : l'item Java devient un vrai item Bedrock
  contenu/generes/datapack/LQDM-Menus.zip           datapack des menus (dialogs) pour les serveurs Paper
  contenu/generes/items.json                        commande /give de chaque item (./outils.sh donner)
  contenu/generes/lqdm-items.sk                     fonction Skript donnerItemLQDM(joueur, id, quantité)

  python3 outils/contenu.py                  génère tout (lit les formats de pack chez Mojang la 1re fois)
  python3 outils/contenu.py --formats 97,121 force les formats (resource pack, datapack), utile hors ligne

Côté Java, un item custom est un item vanilla avec le composant item_model, et les menus sont des
dialogs vanilla : aucun mod n'est nécessaire. Geyser traduit les deux pour Bedrock.
Bibliothèque standard Python uniquement.
"""
import argparse
import hashlib
import io
import json
import pathlib
import re
import struct
import sys
import urllib.request
import uuid
import zipfile

RACINE = pathlib.Path(__file__).resolve().parent.parent
CONTENU = RACINE / 'contenu'
SORTIE = CONTENU / 'generes'
NS = 'lqdm'
NOM = 'LQDM'
GENERATEUR = 2   # à augmenter si les fichiers produits changent de forme (nouvelle version du pack Bedrock)
UUID_BASE = uuid.UUID('6f1d1c4e-3b1a-4c8e-9a51-2f6c0d8e7b10')   # fixe : les consoles reconnaissent le pack
DATE_ZIP = (1980, 1, 1, 0, 0, 0)   # dates figées : même contenu = même fichier = rien à retélécharger

CLES = {'nom', 'base', 'type', 'description', 'brillant', 'pile_max', 'durabilite', 'nourriture'}
CLES_NOURRITURE = {'faim', 'saturation', 'toujours', 'duree', 'animation'}
ANIMATIONS = {'none', 'eat', 'drink', 'block', 'bow', 'spear', 'crossbow', 'spyglass'}
CLES_MENU = {'titre', 'texte', 'colonnes', 'boutons'}
CLES_BOUTON = {'texte', 'icone', 'info', 'largeur', 'commande', 'suggerer', 'menu', 'lien', 'copier'}
ACTIONS_BOUTON = ('commande', 'suggerer', 'menu', 'lien', 'copier')


def erreur(msg):
    sys.exit('❌ ' + msg)


# --- Items -----------------------------------------------------------------------------

def taille_png(chemin):
    entete = chemin.read_bytes()[:24]
    if entete[:8] != b'\x89PNG\r\n\x1a\n' or entete[12:16] != b'IHDR':
        erreur(f'{chemin.name} n\'est pas une image PNG')
    return struct.unpack('>II', entete[16:24])


def verifier_item(id_, d):
    def non(msg):
        erreur(f'contenu/items/{id_}.json : {msg}')

    inconnues = set(d) - CLES
    if inconnues:
        non(f"clé inconnue « {', '.join(sorted(inconnues))} » (clés possibles : {', '.join(sorted(CLES))})")
    if not isinstance(d.get('nom'), str) or not d['nom'].strip():
        non('« nom » est obligatoire')
    if not re.fullmatch(r'minecraft:[a-z0-9_]+', d.get('base', 'minecraft:paper')):
        non('« base » doit être un item vanilla, ex. "minecraft:paper"')
    if d.get('type', 'objet') not in ('objet', 'outil'):
        non('« type » vaut "objet" (tenu à plat) ou "outil" (tenu comme une épée)')
    if not all(isinstance(l, str) for l in d.get('description', [])):
        non('« description » est une liste de lignes de texte')
    if 'pile_max' in d and not (isinstance(d['pile_max'], int) and 1 <= d['pile_max'] <= 99):
        non('« pile_max » va de 1 à 99')
    if 'durabilite' in d and not (isinstance(d['durabilite'], int) and d['durabilite'] > 0):
        non('« durabilite » est un nombre entier positif')
    n = d.get('nourriture')
    if n is not None:
        if not isinstance(n, dict) or set(n) - CLES_NOURRITURE:
            non(f"« nourriture » accepte : {', '.join(sorted(CLES_NOURRITURE))}")
        if not (isinstance(n.get('faim', 0), int) and n.get('faim', 0) >= 0):
            non('« faim » est un nombre entier (2 = une cuisse de poulet)')
        if n.get('animation', 'eat') not in ANIMATIONS:
            non(f"« animation » vaut : {', '.join(sorted(ANIMATIONS))}")


def charger_items():
    items = []
    for f in sorted((CONTENU / 'items').glob('*.json')):
        id_ = f.stem
        if not re.fullmatch(r'[a-z0-9_]+', id_):
            erreur(f'{f.name} : nom de fichier en minuscules, chiffres et _ seulement (ex. baton_magique.json)')
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            erreur(f'{f.name} : JSON invalide ({e})')
        verifier_item(id_, d)
        png = f.with_suffix('.png')
        if not png.exists():
            erreur(f'il manque la texture contenu/items/{id_}.png')
        largeur, hauteur = taille_png(png)
        if largeur != hauteur:
            erreur(f'{id_}.png fait {largeur}×{hauteur} : la texture doit être carrée (16×16 conseillé)')
        items.append({'id': id_, 'def': d, 'png': png.read_bytes()})
    return items


def composants_java(id_, d):
    c = {'item_model': f'{NS}:{id_}', 'item_name': d['nom']}
    if d.get('description'):
        c['lore'] = [{'text': l, 'italic': False, 'color': 'gray'} for l in d['description']]
    if d.get('brillant'):
        c['enchantment_glint_override'] = True
    if d.get('durabilite'):
        c['max_stack_size'] = 1                   # Java refuse un item usable empilable
        c['max_damage'] = d['durabilite']
    elif 'pile_max' in d:
        c['max_stack_size'] = d['pile_max']
    n = d.get('nourriture')
    if n is not None:
        c['food'] = {'nutrition': n.get('faim', 0), 'saturation': float(n.get('saturation', 0)),
                     'can_always_eat': bool(n.get('toujours', False))}
        c['consumable'] = {'consume_seconds': float(n.get('duree', 1.6)), 'animation': n.get('animation', 'eat')}
    return c


def snbt(v):
    """Valeur Python → SNBT, la syntaxe des composants dans les commandes."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return format(v, 'g') + 'f'
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(v, list):
        return '[' + ','.join(snbt(x) for x in v) + ']'
    return '{' + ','.join(f'{k}:{snbt(x)}' for k, x in v.items()) + '}'


def commande_give(id_, d):
    composants = ','.join(f'{k}={snbt(v)}' for k, v in composants_java(id_, d).items())
    return f"give <joueur> {d.get('base', 'minecraft:paper')}[{composants}] <quantite>"


def definition_geyser(id_, d):
    java = composants_java(id_, d)
    composants = {f'minecraft:{k}': java[k] for k in
                  ('max_stack_size', 'max_damage', 'enchantment_glint_override', 'food', 'consumable') if k in java}
    return {
        'type': 'definition',
        'bedrock_identifier': f'{NS}:{id_}',
        'model': f'{NS}:{id_}',
        'display_name': d['nom'],
        'bedrock_options': {
            'icon': f'{NS}_{id_}',
            'allow_offhand': True,
            'display_handheld': d.get('type') == 'outil',
            'creative_category': 'items',
        },
        'components': composants,
    }


# --- Menus (dialogs vanilla) ----------------------------------------------------------------

def charger_menus():
    f = CONTENU / 'menus.json'
    if not f.exists():
        return {}
    try:
        menus = json.loads(f.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        erreur(f'menus.json : JSON invalide ({e})')
    if 'menu' not in menus:
        erreur('menus.json : il faut un menu nommé « menu » (celui du menu Échap et de /menu)')
    for nom, m in menus.items():
        def non(msg):
            erreur(f'menus.json, menu « {nom} » : {msg}')
        if not re.fullmatch(r'[a-z0-9_]+', nom):
            non('nom en minuscules, chiffres et _ seulement')
        if set(m) - CLES_MENU:
            non(f"clé inconnue « {', '.join(sorted(set(m) - CLES_MENU))} » (clés possibles : {', '.join(sorted(CLES_MENU))})")
        if not m.get('titre'):
            non('« titre » est obligatoire')
        for i, b in enumerate(m.get('boutons', []), 1):
            if set(b) - CLES_BOUTON:
                non(f"bouton {i} : clé inconnue « {', '.join(sorted(set(b) - CLES_BOUTON))} »")
            if not b.get('texte'):
                non(f'bouton {i} : « texte » est obligatoire')
            actions = [a for a in ACTIONS_BOUTON if a in b]
            if len(actions) != 1:
                non(f"bouton « {b['texte']} » : il faut exactement une action parmi {', '.join(ACTIONS_BOUTON)}")
            if 'menu' in b and b['menu'] not in menus:
                non(f"bouton « {b['texte']} » : le menu « {b['menu']} » n'existe pas")
            if 'lien' in b and not b['lien'].startswith('https://'):
                non(f"bouton « {b['texte']} » : le lien doit commencer par https://")
            if 'icone' in b and not re.fullmatch(r'[a-z0-9_]+', b['icone']):
                non(f"bouton « {b['texte']} » : « icone » est un nom d'item vanilla, ex. \"ender_pearl\"")
    return menus


def bouton_dialog(b):
    texte = b['texte']
    if b.get('icone'):
        # Petite icône d'item devant le texte (Java) ; Bedrock n'affiche que le texte.
        texte = [{'type': 'object', 'atlas': 'minecraft:items', 'sprite': f'item/{b["icone"]}', 'fallback': ''},
                 ' ' + b['texte']]
    if 'commande' in b:
        action = {'type': 'run_command', 'command': b['commande'].lstrip('/')}
    elif 'suggerer' in b:
        # Pré-remplit le chat (ex. « /tpa ») : le joueur n'a plus qu'à taper le pseudo.
        action = {'type': 'suggest_command', 'command': '/' + b['suggerer'].lstrip('/')}
    elif 'menu' in b:
        action = {'type': 'show_dialog', 'dialog': f'{NS}:{b["menu"]}'}
    elif 'lien' in b:
        action = {'type': 'open_url', 'url': b['lien']}
    else:
        action = {'type': 'copy_to_clipboard', 'value': b['copier']}
    j = {'label': texte, 'action': action}
    if b.get('info'):
        j['tooltip'] = b['info']
    if b.get('largeur'):
        j['width'] = b['largeur']
    return j


def dialog(nom, m):
    lignes = m.get('texte', [])
    lignes = [lignes] if isinstance(lignes, str) else lignes
    retour = {'label': 'Fermer', 'width': 200} if nom == 'menu' else \
        {'label': 'Retour', 'width': 200, 'action': {'type': 'show_dialog', 'dialog': f'{NS}:menu'}}
    d = {'title': m['titre'], 'external_title': m['titre'], 'can_close_with_escape': True}
    if lignes:
        d['body'] = [{'type': 'minecraft:plain_message', 'contents': l, 'width': 300} for l in lignes]
    if m.get('boutons'):
        return {'type': 'minecraft:multi_action', **d, 'columns': m.get('colonnes', 2),
                'actions': [bouton_dialog(b) for b in m['boutons']], 'exit_action': retour}
    return {'type': 'minecraft:notice', **d, 'action': retour}


# --- Fichiers produits ---------------------------------------------------------------------

def zip_fige(fichiers):
    """Zip déterministe : entrées triées, dates figées."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, 'w', zipfile.ZIP_DEFLATED) as z:
        for nom in sorted(fichiers):
            info = zipfile.ZipInfo(nom, DATE_ZIP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            donnees = fichiers[nom]
            z.writestr(info, donnees if isinstance(donnees, bytes) else donnees.encode('utf-8'))
    return tampon.getvalue()


def js(objet):
    return json.dumps(objet, indent=2, ensure_ascii=False) + '\n'


def mcmeta(description, format_):
    majeur, mineur = format_
    return js({'pack': {'description': description, 'pack_format': majeur,
                        'min_format': [majeur, mineur], 'max_format': [majeur, mineur]}})


def pack_java(items, format_, icone):
    fichiers = {'pack.mcmeta': mcmeta(f'{NOM} : items du serveur', format_)}
    if icone:
        fichiers['pack.png'] = icone
    for it in items:
        id_ = it['id']
        parent = 'minecraft:item/handheld' if it['def'].get('type') == 'outil' else 'minecraft:item/generated'
        fichiers[f'assets/{NS}/items/{id_}.json'] = js({'model': {'type': 'minecraft:model', 'model': f'{NS}:item/{id_}'}})
        fichiers[f'assets/{NS}/models/item/{id_}.json'] = js({'parent': parent, 'textures': {'layer0': f'{NS}:item/{id_}'}})
        fichiers[f'assets/{NS}/textures/item/{id_}.png'] = it['png']
    return zip_fige(fichiers)


def pack_bedrock(items, version, icone):
    version3 = [1, 0, version]
    fichiers = {
        'manifest.json': js({
            'format_version': 2,
            'header': {'name': NOM, 'description': 'Items du serveur (généré)',
                       'uuid': str(uuid.uuid5(UUID_BASE, 'en-tete')), 'version': version3,
                       'min_engine_version': [1, 21, 0]},
            'modules': [{'type': 'resources', 'uuid': str(uuid.uuid5(UUID_BASE, 'module')), 'version': version3}],
        }),
        'textures/item_texture.json': js({
            'resource_pack_name': NS, 'texture_name': 'atlas.items',
            'texture_data': {f'{NS}_{it["id"]}': {'textures': f'textures/items/{NS}/{it["id"]}'} for it in items},
        }),
    }
    if icone:
        fichiers['pack_icon.png'] = icone
    for it in items:
        fichiers[f'textures/items/{NS}/{it["id"]}.png'] = it['png']
    return zip_fige(fichiers)


def datapack_menus(menus, format_):
    fichiers = {'pack.mcmeta': mcmeta(f'{NOM} : menus du serveur', format_)}
    for nom, m in menus.items():
        fichiers[f'data/{NS}/dialog/{nom}.json'] = js(dialog(nom, m))
    # Le menu « menu » devient le bouton du menu Échap (Java) et l'action rapide (touche dédiée).
    for tag in ('pause_screen_additions', 'quick_actions'):
        fichiers[f'data/minecraft/tags/dialog/{tag}.json'] = js({'values': [f'{NS}:menu']})
    return zip_fige(fichiers)


def script_skript(items):
    lignes = [
        '# Généré par outils/contenu.py à partir de contenu/items : ne pas modifier à la main.',
        '# Dans un script : donnerItemLQDM(player, "poutine", 1)',
        'function donnerItemLQDM(joueur: player, objet: text, quantite: integer = 1):',
    ]
    for it in items:
        # Dans une chaîne Skript, « " » s'écrit « "" » et « % » s'écrit « %% ».
        cmd = commande_give(it['id'], it['def']).replace('"', '""').replace('%', '%%')
        cmd = cmd.replace('<joueur>', '%{_joueur}%').replace('<quantite>', '%{_quantite}%')
        lignes += [f'\tif {{_objet}} is "{it["id"]}":', f'\t\texecute console command "{cmd}"', '\t\tstop']
    lignes.append('\tsend "[LQDM] Item inconnu : %{_objet}%" to console')
    return '\n'.join(lignes) + '\n'


# --- Formats de pack, lus dans le jeu lui-même -----------------------------------------------

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'PoiBoy34/QC-SMP (outils/contenu.py)'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def formats_pack(mc):
    """Formats resource pack et datapack de cette version, lus dans le version.json du client."""
    manifest = json.loads(get('https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'))
    entree = next((v for v in manifest['versions'] if v['id'] == mc), None)
    if not entree:
        erreur(f'version de Minecraft « {mc} » inconnue de Mojang')
    client = json.loads(get(entree['url']))['downloads']['client']['url']
    with zipfile.ZipFile(io.BytesIO(get(client))) as jar:
        pv = json.loads(jar.read('version.json'))['pack_version']
    return {'ressources': [pv.get('resource_major', pv.get('resource')), pv.get('resource_minor', 0)],
            'donnees': [pv.get('data_major', pv.get('data')), pv.get('data_minor', 0)]}


# --- Programme principal ---------------------------------------------------------------------

def ecrire(chemin, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    donnees = donnees.encode('utf-8') if isinstance(donnees, str) else donnees
    if not chemin.exists() or chemin.read_bytes() != donnees:
        chemin.write_bytes(donnees)
        print(f'   écrit : {chemin.relative_to(RACINE)}')


def retirer(chemin):
    if chemin.exists():
        chemin.unlink()
        print(f'   retiré : {chemin.relative_to(RACINE)}')


def main():
    p = argparse.ArgumentParser(description='Génère les items et les menus custom pour Java et Bedrock.')
    p.add_argument('--formats', help='formats resource pack et datapack, ex. 97,121 (sinon lus chez Mojang)')
    args = p.parse_args()

    catalog = json.loads((RACINE / 'catalog.json').read_text(encoding='utf-8'))
    pack = catalog['modpacks'][0]
    mc = pack['minecraft']
    m = re.search(r'/(modpacks/[^/]+)/manifest\.json', pack['manifest_url'])
    zip_java = RACINE / m.group(1) / 'resourcepacks' / 'LQDM-Contenu.zip'
    sorties_items = [zip_java, SORTIE / 'bedrock' / 'LQDM-Contenu.mcpack', SORTIE / 'geyser' / f'{NS}.json',
                     SORTIE / 'items.json', SORTIE / 'lqdm-items.sk']
    sortie_menus = SORTIE / 'datapack' / 'LQDM-Menus.zip'

    items = charger_items()
    menus = charger_menus()
    if not items and not menus:
        for f in sorties_items + [sortie_menus]:
            retirer(f)
        print('Ni item ni menu dans contenu/ : rien à générer.')
        return

    chemin_etat = SORTIE / 'etat.json'
    etat = json.loads(chemin_etat.read_text(encoding='utf-8')) if chemin_etat.exists() else {}
    if args.formats:
        r, d = (int(x) for x in args.formats.split(','))
        formats = {'ressources': [r, 0], 'donnees': [d, 0]}
    elif etat.get('minecraft') == mc and etat.get('formats'):
        formats = etat['formats']
    else:
        if mc == 'latest':
            erreur('la version de Minecraft du catalog.json n\'est pas encore fixée : lance d\'abord outils/modrinth.py')
        print(f'Formats de pack pour Minecraft {mc} (téléchargement du client chez Mojang)…')
        formats = formats_pack(mc)

    icone_chemin = RACINE / 'assets' / 'pack-icons' / 'lqdm.png'
    icone = icone_chemin.read_bytes() if icone_chemin.exists() else None
    version = etat.get('version_bedrock', 0)
    empreinte = etat.get('empreinte')

    if items:
        # Le pack Bedrock change de version à chaque modification, sinon les consoles gardent l'ancien en cache.
        h = hashlib.sha1(str(GENERATEUR).encode())
        for it in items:
            h.update(it['id'].encode() + json.dumps(it['def'], sort_keys=True).encode() + it['png'])
        if h.hexdigest() != empreinte:
            empreinte, version = h.hexdigest(), version + 1
        mappings = {'format_version': 2, 'items': {}}
        for it in items:
            mappings['items'].setdefault(it['def'].get('base', 'minecraft:paper'), []).append(
                definition_geyser(it['id'], it['def']))
        print(f"🧩 {len(items)} item(s), pack Java format {formats['ressources'][0]}, pack Bedrock v1.0.{version}")
        ecrire(zip_java, pack_java(items, formats['ressources'], icone))
        ecrire(SORTIE / 'bedrock' / 'LQDM-Contenu.mcpack', pack_bedrock(items, version, icone))
        ecrire(SORTIE / 'geyser' / f'{NS}.json', js(mappings))
        ecrire(SORTIE / 'items.json', js({it['id']: {'nom': it['def']['nom'], 'commande': commande_give(it['id'], it['def'])}
                                          for it in items}))
        ecrire(SORTIE / 'lqdm-items.sk', script_skript(items))
    else:
        for f in sorties_items:
            retirer(f)

    if menus:
        print(f"🧭 {len(menus)} menu(s), datapack format {formats['donnees'][0]}")
        ecrire(sortie_menus, datapack_menus(menus, formats['donnees']))
    else:
        retirer(sortie_menus)

    ecrire(chemin_etat, js({'minecraft': mc, 'formats': formats, 'empreinte': empreinte,
                            'version_bedrock': version}))
    print('✅ Contenu généré')


if __name__ == '__main__':
    main()
