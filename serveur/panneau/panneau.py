#!/usr/bin/env python3
"""
Panneau de contrôle LQDM : gérer le réseau Minecraft depuis un navigateur.

Tableau de bord (serveurs, mémoire, CPU, joueurs), joueurs (infos, statistiques, actions),
admins, console en direct, journaux, plugins et datapacks (ajout par glisser-déposer).

Tourne sur la VM (service systemd « lqdm-panneau », installé par deploy.sh), en HTTPS avec
le certificat Let's Encrypt du domaine du jeu, joignable d'Internet : un compte et un mot de
passe par admin, essais limités, historique des actions. Parle aux serveurs avec docker et
rcon-cli, comme outils.sh. Bibliothèque standard Python uniquement.
"""
import gzip
import hashlib
import hmac
import http.server
import json
import os
import pathlib
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.parse

BASE = pathlib.Path(os.environ.get('LQDM_BASE', '/opt/minecraft'))
WEB = pathlib.Path(__file__).resolve().parent / 'web'
PORT = int(os.environ.get('PANNEAU_PORT', '8080'))
# Un fichier par compte (nom du fichier = nom du compte, contenu = mot de passe), créés par deploy.sh
COMPTES = pathlib.Path(os.environ.get('PANNEAU_COMPTES', '/etc/lqdm-panneau/comptes'))
HISTORIQUE = pathlib.Path(os.environ.get('STATE_DIRECTORY', '/var/lib/lqdm-panneau')) / 'historique.jsonl'
CERTIFICAT = os.environ.get('PANNEAU_CERTIFICAT', '')     # vide = HTTP (réseau local seulement)
CLE_PRIVEE = os.environ.get('PANNEAU_CLE', '')
DUREE_SESSION = 7 * 24 * 3600
TAILLE_MAX_ENVOI = 300 * 1024 * 1024
CLE_SESSION = secrets.token_bytes(32)        # nouvelle à chaque démarrage : il faut se reconnecter

PAS_MINECRAFT = {'mariadb', 'ddns'}
RE_JOUEUR = re.compile(r'^\.?[A-Za-z0-9_]{1,20}$')
RE_FICHIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._+()-]{0,150}$')
RE_ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]|§[0-9a-fk-orx]', re.I)
GAMEMODES = {'survival', 'creative', 'adventure', 'spectator'}
# Dossiers gérables depuis l'onglet Plugins : (chemin dans le dossier du serveur, extensions)
DOSSIERS = {
    'plugins': ('plugins', ('.jar',)),
    'datapacks': ('world/datapacks', ('.zip',)),
}


def sans_couleurs(texte):
    return RE_ANSI.sub('', texte)


def lancer(args, delai=20):
    """Lance une commande sans shell ; renvoie (code, sortie)."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=delai)
        return p.returncode, sans_couleurs((p.stdout or '') + (p.stderr or '')).strip()
    except subprocess.TimeoutExpired:
        return 124, 'délai dépassé'
    except OSError as e:
        return 127, str(e)


# --- Le réseau : conteneurs, rcon, fichiers -----------------------------------------------

def conteneurs():
    code, sortie = lancer(['docker', 'ps', '-a', '--filter', 'name=^mc-',
                           '--format', '{{.Names}}\t{{.State}}\t{{.Status}}'])
    res = []
    if code != 0:
        return res
    for ligne in sortie.splitlines():
        parts = ligne.split('\t')
        if len(parts) != 3 or not parts[0].startswith('mc-'):
            continue
        nom = parts[0][3:]
        genre = 'proxy' if nom == 'proxy' else ('autre' if nom in PAS_MINECRAFT else 'paper')
        res.append({'nom': nom, 'genre': genre, 'etat': parts[1], 'statut': parts[2]})
    ordre = {'proxy': 0, 'spawn': 1, 'smp': 2}
    return sorted(res, key=lambda c: (c['genre'] == 'autre', ordre.get(c['nom'], 3), c['nom']))


def serveurs_paper(en_marche=False):
    return [c['nom'] for c in conteneurs() if c['genre'] == 'paper' and (c['etat'] == 'running' or not en_marche)]


def serveur_valide(nom, minecraft=True):
    for c in conteneurs():
        if c['nom'] == nom and (not minecraft or c['genre'] != 'autre'):
            return c
    raise Erreur(404, f'serveur inconnu : {nom}')


def dossier(nom):
    return BASE / 'proxy' if nom == 'proxy' else BASE / 'serveurs' / nom


def rcon(nom, commande):
    code, sortie = lancer(['docker', 'exec', f'mc-{nom}', 'rcon-cli', commande])
    return code == 0, sortie


def lire_json(chemin, defaut):
    try:
        return json.loads(pathlib.Path(chemin).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return defaut


RE_LIST = re.compile(r'There are (\d+) (?:of a max of|out of maximum) (\d+) players online:?(.*)', re.S)


def joueurs_en_ligne():
    """{serveur: {'max': n, 'joueurs': [noms]}} pour les serveurs Paper en marche."""
    res = {}
    for nom in serveurs_paper(en_marche=True):
        ok, sortie = rcon(nom, 'list')
        m = RE_LIST.search(sortie) if ok else None
        if m:
            noms = [n.strip() for n in m.group(3).replace('\n', ',').split(',') if n.strip()]
            res[nom] = {'max': int(m.group(2)), 'joueurs': noms}
    return res


# Les statistiques Docker prennent ~2 s : un fil les tient à jour en continu.
_stats = {'temps': 0, 'valeurs': {}}


def boucle_stats():
    while True:
        code, sortie = lancer(['docker', 'stats', '--no-stream', '--format', '{{json .}}'], delai=30)
        if code == 0:
            valeurs = {}
            for ligne in sortie.splitlines():
                try:
                    d = json.loads(ligne)
                except ValueError:
                    continue
                if d.get('Name', '').startswith('mc-'):
                    valeurs[d['Name'][3:]] = {'cpu': d.get('CPUPerc', ''), 'memoire': d.get('MemUsage', ''),
                                              'memoire_pc': d.get('MemPerc', '')}
            _stats.update(temps=time.time(), valeurs=valeurs)
        time.sleep(5)


def systeme():
    info = {}
    try:
        mem = dict(l.split(':', 1) for l in pathlib.Path('/proc/meminfo').read_text().splitlines())
        total = int(mem['MemTotal'].split()[0]) * 1024
        dispo = int(mem['MemAvailable'].split()[0]) * 1024
        info['memoire'] = {'total': total, 'utilise': total - dispo}
        info['charge'] = os.getloadavg()
        info['coeurs'] = os.cpu_count()
        info['allume_depuis'] = float(pathlib.Path('/proc/uptime').read_text().split()[0])
    except (OSError, KeyError, ValueError):
        pass
    try:
        d = shutil.disk_usage(BASE)
        info['disque'] = {'total': d.total, 'utilise': d.used}
    except OSError:
        pass
    return info


# --- Joueurs ------------------------------------------------------------------------------

def edition(uuid):
    return 'Bedrock' if uuid.startswith('00000000-0000-0000-0009') else 'Java'


def stats_joueur(uuid):
    """Statistiques additionnées sur tous les serveurs Paper, et dernière présence."""
    total = {'temps_jeu': 0, 'morts': 0, 'monstres_tues': 0, 'joueurs_tues': 0, 'distance': 0}
    vu, vu_sur = 0, None
    for nom in serveurs_paper():
        monde = dossier(nom) / 'world'
        s = lire_json(monde / 'stats' / f'{uuid}.json', {}).get('stats', {}).get('minecraft:custom', {})
        total['temps_jeu'] += s.get('minecraft:play_time', s.get('minecraft:play_one_minute', 0)) // 20
        total['morts'] += s.get('minecraft:deaths', 0)
        total['monstres_tues'] += s.get('minecraft:mob_kills', 0)
        total['joueurs_tues'] += s.get('minecraft:player_kills', 0)
        total['distance'] += sum(v for k, v in s.items() if k.endswith('_one_cm')) // 100
        try:
            t = (monde / 'playerdata' / f'{uuid}.dat').stat().st_mtime
            if t > vu:
                vu, vu_sur = t, nom
        except OSError:
            pass
    return total, vu, vu_sur


def liste_joueurs():
    paper = serveurs_paper()
    connus = {}
    ops, bannis = set(), set()
    for nom in paper:
        d = dossier(nom)
        for e in lire_json(d / 'usercache.json', []):
            if isinstance(e, dict) and e.get('uuid') and e.get('name'):
                connus.setdefault(e['uuid'], e['name'])
        ops |= {e.get('uuid') for e in lire_json(d / 'ops.json', []) if isinstance(e, dict)}
        bannis |= {e.get('uuid') for e in lire_json(d / 'banned-players.json', []) if isinstance(e, dict)}
        for e in lire_json(d / 'ops.json', []) + lire_json(d / 'banned-players.json', []):
            if isinstance(e, dict) and e.get('uuid') and e.get('name'):
                connus.setdefault(e['uuid'], e['name'])
    liste_blanche = {e.get('uuid') for e in lire_json(BASE / 'partage' / 'whitelist.json', []) if isinstance(e, dict)}
    for e in lire_json(BASE / 'partage' / 'whitelist.json', []):
        if isinstance(e, dict) and e.get('uuid') and e.get('name'):
            connus.setdefault(e['uuid'], e['name'])

    en_ligne = {}
    for serveur, d in joueurs_en_ligne().items():
        for n in d['joueurs']:
            en_ligne[n.lower()] = serveur

    res = []
    for uuid, nom in connus.items():
        stats, vu, vu_sur = stats_joueur(uuid)
        ou = en_ligne.get(nom.lower())
        res.append({'nom': nom, 'uuid': uuid, 'edition': edition(uuid), 'en_ligne': ou,
                    'op': uuid in ops, 'banni': uuid in bannis, 'liste_blanche': uuid in liste_blanche,
                    'vu': vu, 'vu_sur': vu_sur, 'stats': stats})
    # Joueurs connectés pas encore dans les caches (tout nouveaux)
    noms = {j['nom'].lower() for j in res}
    for n, serveur in en_ligne.items():
        if n not in noms:
            res.append({'nom': n, 'uuid': '', 'edition': 'Bedrock' if n.startswith('.') else 'Java',
                        'en_ligne': serveur, 'op': False, 'banni': False, 'liste_blanche': False,
                        'vu': time.time(), 'vu_sur': serveur, 'stats': {}})
    res.sort(key=lambda j: (j['en_ligne'] is None, -j['vu'], j['nom'].lower()))
    return res


def ou_est(joueur):
    for serveur, d in joueurs_en_ligne().items():
        if joueur.lower() in (n.lower() for n in d['joueurs']):
            return serveur
    return None


def texte_court(valeur, defaut=''):
    t = ' '.join(str(valeur or defaut).split())[:200]
    return t


def partout(commande):
    """Lance la commande sur tous les serveurs Paper en marche ; renvoie les sorties."""
    return {nom: rcon(nom, commande)[1] for nom in serveurs_paper(en_marche=True)}


def action_joueur(d):
    joueur = str(d.get('joueur', ''))
    if not RE_JOUEUR.match(joueur):
        raise Erreur(400, 'pseudo invalide')
    action = d.get('action')
    nu = joueur[1:] if joueur.startswith('.') else joueur
    if action == 'expulser':
        serveur = ou_est(joueur)
        if not serveur:
            raise Erreur(409, f"{joueur} n'est pas connecté")
        return {serveur: rcon(serveur, f"kick {joueur} {texte_court(d.get('raison'), 'Expulsé par un admin')}")[1]}
    if action == 'bannir':
        return partout(f"ban {joueur} {texte_court(d.get('raison'), 'Banni par un admin')}")
    if action == 'debannir':
        return partout(f'pardon {joueur}')
    if action == 'op':
        return partout(f'op {joueur}')
    if action == 'deop':
        return partout(f'deop {joueur}')
    if action in ('liste_blanche_ajouter', 'liste_blanche_retirer'):
        spawn = 'spawn' if 'spawn' in serveurs_paper(en_marche=True) else (serveurs_paper(en_marche=True) or [None])[0]
        if not spawn:
            raise Erreur(409, 'aucun serveur Paper en marche')
        ajout = action.endswith('ajouter')
        if joueur.startswith('.'):
            sortie = rcon(spawn, f"fwhitelist {'add' if ajout else 'remove'} {nu}")[1]
        else:
            sortie = rcon(spawn, f"whitelist {'add' if ajout else 'remove'} {joueur}")[1]
        for nom in serveurs_paper(en_marche=True):
            if nom != spawn:
                rcon(nom, 'whitelist reload')
        return {spawn: sortie}
    if action == 'mode':
        mode = d.get('valeur')
        if mode not in GAMEMODES:
            raise Erreur(400, 'mode de jeu invalide')
        serveur = ou_est(joueur)
        if not serveur:
            raise Erreur(409, f"{joueur} n'est pas connecté")
        return {serveur: rcon(serveur, f'gamemode {mode} {joueur}')[1]}
    if action == 'envoyer':
        cible = str(d.get('valeur', ''))
        if cible not in serveurs_paper():
            raise Erreur(400, 'serveur inconnu')
        return {'proxy': rcon('proxy', f'send {joueur} {cible}')[1]}
    if action == 'message':
        serveur = ou_est(joueur)
        if not serveur:
            raise Erreur(409, f"{joueur} n'est pas connecté")
        return {serveur: rcon(serveur, f"tell {joueur} {texte_court(d.get('valeur'))}")[1]}
    if action == 'grade':
        groupe = str(d.get('valeur', ''))
        if not re.match(r'^[a-z0-9_-]{1,32}$', groupe):
            raise Erreur(400, 'grade invalide (minuscules, chiffres, - et _)')
        serveur = (serveurs_paper(en_marche=True) or [None])[0]
        if not serveur:
            raise Erreur(409, 'aucun serveur Paper en marche')
        return {serveur: rcon(serveur, f'lp user {joueur} parent set {groupe}')[1]}
    if action == 'infos':
        serveur = (serveurs_paper(en_marche=True) or [None])[0]
        if not serveur:
            raise Erreur(409, 'aucun serveur Paper en marche')
        return {'grades (LuckPerms)': rcon(serveur, f'lp user {joueur} info')[1]}
    raise Erreur(400, 'action inconnue')


# --- Fichiers : journaux, plugins, datapacks ---------------------------------------------

def nom_fichier(nom):
    if not RE_FICHIER.match(nom) or '..' in nom:
        raise Erreur(400, 'nom de fichier invalide')
    return nom


def journaux(serveur):
    d = dossier(serveur) / 'logs'
    res = []
    if d.is_dir():
        for f in d.iterdir():
            if f.is_file() and (f.suffix in ('.log', '.gz', '.txt')):
                st = f.stat()
                res.append({'nom': f.name, 'taille': st.st_size, 'date': st.st_mtime})
    return sorted(res, key=lambda f: -f['date'])


def lire_journal(serveur, nom):
    f = dossier(serveur) / 'logs' / nom_fichier(nom)
    if not f.is_file():
        raise Erreur(404, 'journal introuvable')
    donnees = gzip.decompress(f.read_bytes()) if f.suffix == '.gz' else f.read_bytes()
    donnees = donnees[-3 * 1024 * 1024:]          # les 3 derniers Mo suffisent
    return sans_couleurs(donnees.decode('utf-8', 'replace'))


def lister_dossier(serveur, genre):
    if genre not in DOSSIERS:
        raise Erreur(404, 'dossier inconnu')
    if genre == 'datapacks' and serveur == 'proxy':
        return []
    chemin, extensions = DOSSIERS[genre]
    d = dossier(serveur) / chemin
    res = []
    if d.is_dir():
        for f in d.iterdir():
            if not f.is_file():
                continue
            actif = f.name.endswith(extensions)
            desactive = f.name.endswith(tuple(e + '.desactive' for e in extensions))
            if actif or desactive:
                st = f.stat()
                res.append({'nom': f.name, 'actif': actif, 'taille': st.st_size, 'date': st.st_mtime})
    return sorted(res, key=lambda f: f['nom'].lower())


def chemin_dans(serveur, genre, nom):
    if genre not in DOSSIERS or (genre == 'datapacks' and serveur == 'proxy'):
        raise Erreur(404, 'dossier inconnu')
    d = (dossier(serveur) / DOSSIERS[genre][0]).resolve()
    f = (d / nom_fichier(nom)).resolve()
    if f.parent != d:
        raise Erreur(400, 'nom de fichier invalide')
    return d, f


# --- Sessions -----------------------------------------------------------------------------

RE_COMPTE = re.compile(r'^[A-Za-z0-9_-]{1,32}$')


def jeton(compte):
    donnees = f'{compte}.{int(time.time()) + DUREE_SESSION}'
    sig = hmac.new(CLE_SESSION, donnees.encode(), hashlib.sha256).hexdigest()
    return f'{donnees}.{sig}'


def compte_du_jeton(valeur):
    """Le compte connecté, ou None. Un compte retiré de la VM perd l'accès tout de suite."""
    try:
        compte, expire, sig = valeur.split('.', 2)
        attendu = hmac.new(CLE_SESSION, f'{compte}.{expire}'.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, attendu) and int(expire) > time.time() and (COMPTES / compte).is_file():
            return compte
    except (ValueError, AttributeError, OSError):
        pass
    return None


_verrou_historique = threading.Lock()


def noter(compte, quoi, details=''):
    """Historique des actions : qui a fait quoi, et quand (onglet Historique)."""
    ligne = json.dumps({'date': time.time(), 'compte': compte, 'action': quoi, 'details': str(details)[:500]},
                       ensure_ascii=False)
    with _verrou_historique:
        try:
            HISTORIQUE.parent.mkdir(parents=True, exist_ok=True)
            with open(HISTORIQUE, 'a', encoding='utf-8') as f:
                f.write(ligne + '\n')
        except OSError:
            pass


def lire_historique(n=300):
    try:
        lignes = HISTORIQUE.read_text(encoding='utf-8').splitlines()[-n:]
    except OSError:
        return []
    res = []
    for l in reversed(lignes):
        try:
            res.append(json.loads(l))
        except ValueError:
            pass
    return res


_echecs = {}
_verrou_echecs = threading.Lock()


def mot_de_passe_correct(ip, compte, essai):
    with _verrou_echecs:
        maintenant = time.time()
        recents = [t for t in _echecs.get(ip, []) if maintenant - t < 600]
        _echecs[ip] = recents
        tous = sum(len(v) for v in _echecs.values())
        if len(recents) >= 8 or tous >= 50:
            raise Erreur(429, 'trop d’essais : réessaie dans 10 minutes')
    attendu = ''
    if RE_COMPTE.match(compte):
        try:
            attendu = (COMPTES / compte).read_text(encoding='utf-8').strip()
        except OSError:
            pass
    if attendu and hmac.compare_digest(essai.encode(), attendu.encode()):
        return True
    with _verrou_echecs:
        _echecs.setdefault(ip, []).append(time.time())
        for cle in [k for k, v in _echecs.items() if not v]:
            del _echecs[cle]
    # Lu par fail2ban (5 échecs = adresse bloquée 1 h) : le nom n'est écrit que s'il est valide.
    print(f"connexion refusée : compte {compte if RE_COMPTE.match(compte) else '?'} depuis {ip}", flush=True)
    time.sleep(1)
    return False


# --- HTTP ---------------------------------------------------------------------------------

class Erreur(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
         '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png'}


class Gestionnaire(http.server.BaseHTTPRequestHandler):
    server_version = 'LQDM-Panneau'
    protocol_version = 'HTTP/1.1'
    timeout = 120                 # un client muet ne bloque pas un fil pour toujours

    def log_message(self, format, *args):     # journal systemd : requêtes API seulement
        if self.path.startswith('/api/') and '/flux' not in self.path:
            super().log_message(format, *args)

    # -- réponses
    def envoyer(self, code, corps, type_='application/json; charset=utf-8', entetes=None):
        if not isinstance(corps, bytes):
            corps = json.dumps(corps, ensure_ascii=False).encode() if 'json' in type_ else str(corps).encode()
        self.send_response(code)
        self.send_header('Content-Type', type_)
        self.send_header('Content-Length', str(len(corps)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        if CERTIFICAT:
            self.send_header('Strict-Transport-Security', 'max-age=31536000')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; img-src 'self' data: https://mc-heads.net; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(corps)

    def connecte(self):
        for morceau in self.headers.get('Cookie', '').split(';'):
            k, _, v = morceau.strip().partition('=')
            if k == 'lqdm':
                compte = compte_du_jeton(v)
                if compte:
                    return compte
        return None

    def corps_json(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > 64 * 1024:
            raise Erreur(413, 'requête trop grosse')
        try:
            return json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            raise Erreur(400, 'JSON invalide')

    # -- aiguillage
    def do_GET(self):
        self.traiter('GET')

    def do_HEAD(self):
        self.traiter('GET')

    def do_POST(self):
        self.traiter('POST')

    def do_PUT(self):
        self.traiter('PUT')

    def do_DELETE(self):
        self.traiter('DELETE')

    def traiter(self, methode):
        url = urllib.parse.urlsplit(self.path)
        morceaux = [urllib.parse.unquote(m) for m in url.path.split('/') if m]
        requete = urllib.parse.parse_qs(url.query)
        try:
            if not morceaux or morceaux[0] != 'api':
                return self.statique(url.path)
            route = morceaux[1:]
            if route == ['connexion'] and methode == 'POST':
                return self.connexion()
            self.compte = self.connecte()
            if not self.compte:
                raise Erreur(401, 'connexion requise')
            # Contre les requêtes envoyées par un autre site : seul le panneau met cet en-tête.
            if methode != 'GET' and self.headers.get('X-LQDM') != '1':
                raise Erreur(403, 'requête refusée')
            return self.api(methode, route, requete)
        except Erreur as e:
            self.envoyer(e.code, {'erreur': e.message})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:      # noqa: BLE001 — une erreur ne doit pas tuer le panneau
            self.log_error('erreur : %r', e)
            self.envoyer(500, {'erreur': f'erreur interne : {e}'})

    def statique(self, chemin):
        nom = chemin.strip('/') or 'index.html'
        f = (WEB / nom).resolve()
        if f.parent != WEB.resolve() or not f.is_file():
            f = WEB / 'index.html'
        self.envoyer(200, f.read_bytes(), TYPES.get(f.suffix, 'application/octet-stream'))

    def connexion(self):
        d = self.corps_json()
        compte = str(d.get('compte', '')).strip()
        if not mot_de_passe_correct(self.client_address[0], compte, str(d.get('mot_de_passe', ''))):
            raise Erreur(401, 'compte ou mot de passe incorrect')
        noter(compte, 'connexion', self.client_address[0])
        self.envoyer(200, {'ok': True, 'compte': compte}, entetes={
            'Set-Cookie': f'lqdm={jeton(compte)}; HttpOnly; SameSite=Strict; Path=/; Max-Age={DUREE_SESSION}'
                          + ('; Secure' if CERTIFICAT else '')})

    def api(self, methode, route, requete):
        r = route + [''] * 4
        if methode == 'GET' and route == ['session']:
            return self.envoyer(200, {'ok': True, 'compte': self.compte})
        if methode == 'GET' and route == ['historique']:
            return self.envoyer(200, {'historique': lire_historique()})
        if methode == 'POST' and route == ['deconnexion']:
            return self.envoyer(200, {'ok': True}, entetes={
                'Set-Cookie': 'lqdm=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})

        if methode == 'GET' and route == ['etat']:
            en_ligne = joueurs_en_ligne()
            serveurs = []
            for c in conteneurs():
                c.update(_stats['valeurs'].get(c['nom'], {}))
                if c['nom'] in en_ligne:
                    c['joueurs'] = en_ligne[c['nom']]['joueurs']
                    c['max'] = en_ligne[c['nom']]['max']
                serveurs.append(c)
            return self.envoyer(200, {'serveurs': serveurs, 'systeme': systeme(),
                                      'stats_a_jour': _stats['temps']})

        if methode == 'POST' and r[0] == 'serveur' and route[2:] and len(route) == 3:
            c = serveur_valide(r[1], minecraft=False)
            action = r[2]
            if action in ('demarrer', 'arreter', 'redemarrer'):
                verbe = {'demarrer': 'start', 'arreter': 'stop', 'redemarrer': 'restart'}[action]
                noter(self.compte, action, c['nom'])
                code, sortie = lancer(['docker', verbe, f"mc-{c['nom']}"], delai=180)
                return self.envoyer(200 if code == 0 else 500, {'sortie': sortie})
            if action == 'sauver' and c['genre'] == 'paper':
                return self.envoyer(200, {'sortie': rcon(c['nom'], 'save-all')[1]})
            raise Erreur(400, 'action inconnue')

        if methode == 'POST' and route == ['annonce']:
            texte = texte_court(self.corps_json().get('texte'))
            if not texte:
                raise Erreur(400, 'message vide')
            noter(self.compte, 'annonce', texte)
            return self.envoyer(200, {'sorties': partout(f'say {texte}')})

        if methode == 'GET' and route == ['joueurs']:
            return self.envoyer(200, {'joueurs': liste_joueurs(), 'serveurs': serveurs_paper()})
        if methode == 'POST' and route == ['joueur']:
            d = self.corps_json()
            if d.get('action') != 'infos':
                noter(self.compte, d.get('action'), f"{d.get('joueur')} {d.get('valeur') or d.get('raison') or ''}".strip())
            return self.envoyer(200, {'sorties': action_joueur(d)})

        if methode == 'GET' and route == ['admins']:
            serveur = (serveurs_paper(en_marche=True) or [None])[0]
            grades = rcon(serveur, 'lp listgroups')[1] if serveur else 'aucun serveur Paper en marche'
            admins = [j for j in liste_joueurs() if j['op']]
            return self.envoyer(200, {'admins': admins, 'grades': grades})

        if r[0] == 'console' and r[1]:
            c = serveur_valide(r[1])
            if methode == 'GET' and r[2] == 'flux':
                return self.flux_console(c['nom'], requete)
            if methode == 'POST':
                commande = str(self.corps_json().get('commande', '')).strip().lstrip('/')
                if not commande or '\n' in commande or len(commande) > 1000:
                    raise Erreur(400, 'commande invalide')
                noter(self.compte, 'console', f"{c['nom']} : {commande}")
                ok, sortie = rcon(c['nom'], commande)
                return self.envoyer(200, {'ok': ok, 'sortie': sortie})

        if methode == 'GET' and r[0] == 'journaux' and r[1]:
            c = serveur_valide(r[1])
            if len(route) == 2:
                return self.envoyer(200, {'journaux': journaux(c['nom'])})
            texte = lire_journal(c['nom'], route[2])
            entetes = {}
            if 'telecharger' in requete:
                entetes['Content-Disposition'] = f'attachment; filename="{c["nom"]}-{route[2].removesuffix(".gz")}"'
            return self.envoyer(200, texte, 'text/plain; charset=utf-8', entetes)

        if r[0] == 'fichiers' and r[1] and r[2]:
            c = serveur_valide(r[1])
            genre = r[2]
            if methode == 'GET' and len(route) == 3:
                return self.envoyer(200, {'fichiers': lister_dossier(c['nom'], genre)})
            if len(route) == 4:
                d, f = chemin_dans(c['nom'], genre, route[3])
                if methode == 'PUT':
                    noter(self.compte, 'ajout fichier', f"{c['nom']} : {genre}/{f.name}")
                    return self.recevoir(d, f, DOSSIERS[genre][1])
                if methode == 'DELETE':
                    if not f.is_file():
                        raise Erreur(404, 'fichier introuvable')
                    noter(self.compte, 'suppression fichier', f"{c['nom']} : {genre}/{f.name}")
                    f.unlink()
                    return self.envoyer(200, {'ok': True})
            if len(route) == 5 and methode == 'POST' and route[4] in ('activer', 'desactiver'):
                d, f = chemin_dans(c['nom'], genre, route[3])
                if not f.is_file():
                    raise Erreur(404, 'fichier introuvable')
                noter(self.compte, route[4], f"{c['nom']} : {genre}/{f.name}")
                if route[4] == 'desactiver' and not f.name.endswith('.desactive'):
                    f.rename(f.with_name(f.name + '.desactive'))
                elif route[4] == 'activer' and f.name.endswith('.desactive'):
                    f.rename(f.with_name(f.name.removesuffix('.desactive')))
                return self.envoyer(200, {'ok': True})

        raise Erreur(404, 'introuvable')

    def recevoir(self, d, f, extensions):
        if not f.name.endswith(extensions):
            raise Erreur(400, 'type de fichier refusé : ' + ', '.join(extensions))
        n = int(self.headers.get('Content-Length') or 0)
        if n <= 0 or n > TAILLE_MAX_ENVOI:
            raise Erreur(413, 'fichier vide ou trop gros (300 Mo maximum)')
        d.mkdir(parents=True, exist_ok=True)
        temp = d / f'.envoi-{secrets.token_hex(4)}'
        try:
            with open(temp, 'wb') as sortie:
                reste = n
                while reste:
                    bloc = self.rfile.read(min(reste, 1024 * 1024))
                    if not bloc:
                        raise Erreur(400, 'envoi interrompu')
                    sortie.write(bloc)
                    reste -= len(bloc)
            with open(temp, 'rb') as entree:
                if entree.read(4) != b'PK\x03\x04':
                    raise Erreur(400, "ce n'est pas un vrai fichier .jar / .zip")
            os.replace(temp, f)
        finally:
            temp.unlink(missing_ok=True)
        self.envoyer(200, {'ok': True, 'nom': f.name})

    def flux_console(self, serveur, requete):
        """Journal en direct (Server-Sent Events) : docker logs -f."""
        lignes = requete.get('lignes', ['300'])[0]
        lignes = lignes if lignes.isdigit() and int(lignes) <= 5000 else '300'
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Accel-Buffering', 'no')
        self.send_header('Connection', 'close')
        self.end_headers()
        p = subprocess.Popen(['docker', 'logs', '-f', '--tail', lignes, f'mc-{serveur}'],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        dernier = time.time()
        try:
            for brut in iter(p.stdout.readline, b''):
                ligne = sans_couleurs(brut.decode('utf-8', 'replace').rstrip('\r\n'))
                self.wfile.write(f'data: {json.dumps(ligne, ensure_ascii=False)}\n\n'.encode())
                if time.time() - dernier > 0.05:
                    self.wfile.flush()
                    dernier = time.time()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            p.kill()
            p.wait()
        self.close_connection = True


class Serveur(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    contexte = None

    def finish_request(self, request, client_address):
        # Dans le fil du client (pas dans la boucle d'accueil) : un client lent ne bloque
        # personne. Quelqu'un qui tape l'adresse sans « https:// » est renvoyé vers https.
        if not self.contexte:
            return super().finish_request(request, client_address)
        request.settimeout(15)
        try:
            debut = request.recv(1, socket.MSG_PEEK)
            if not debut:
                return
            if debut != b'\x16':                     # pas une poignée de main TLS : HTTP en clair
                entete = request.recv(4096).decode('latin-1', 'replace')
                m = re.search(r'(?im)^host:[ \t]*([A-Za-z0-9.-]+)', entete)
                cible = f'https://{m.group(1) if m else "localhost"}:{PORT}/'
                request.sendall((f'HTTP/1.1 301 Moved Permanently\r\nLocation: {cible}\r\n'
                                 'Content-Length: 0\r\nConnection: close\r\n\r\n').encode())
                return
            tls = self.contexte.wrap_socket(request, server_side=True)
        except (OSError, ssl.SSLError):
            return
        try:
            self.RequestHandlerClass(tls, client_address, self)
        finally:
            try:
                tls.close()
            except OSError:
                pass

    def handle_error(self, request, client_address):
        pass                      # clients qui coupent, scanners en HTTP : rien à journaliser


def boucle_certificat(contexte):
    """Recharge le certificat quand certbot le renouvelle (tous les ~60 jours)."""
    vu = os.stat(CERTIFICAT).st_mtime
    while True:
        time.sleep(3600)
        try:
            t = os.stat(CERTIFICAT).st_mtime
            if t != vu:
                contexte.load_cert_chain(CERTIFICAT, CLE_PRIVEE)
                vu = t
                print('certificat rechargé', flush=True)
        except (OSError, ssl.SSLError) as e:
            print(f'certificat : {e}', flush=True)


def main():
    threading.Thread(target=boucle_stats, daemon=True).start()
    comptes = sorted(f.name for f in COMPTES.iterdir() if f.is_file()) if COMPTES.is_dir() else []
    print(f"Panneau LQDM sur le port {PORT} (données : {BASE}, comptes : {', '.join(comptes) or 'aucun'})", flush=True)
    serveur = Serveur(('0.0.0.0', PORT), Gestionnaire)
    if CERTIFICAT:
        contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexte.minimum_version = ssl.TLSVersion.TLSv1_2
        contexte.load_cert_chain(CERTIFICAT, CLE_PRIVEE)
        serveur.contexte = contexte
        threading.Thread(target=boucle_certificat, args=(contexte,), daemon=True).start()
    print('HTTPS actif' if CERTIFICAT else 'HTTP (sans certificat)', flush=True)
    serveur.serve_forever()


if __name__ == '__main__':
    main()
