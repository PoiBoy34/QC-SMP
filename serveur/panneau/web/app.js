// Panneau LQDM : interface. Parle à panneau.py (même adresse, /api/...).
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const etat = { serveurs: [], paper: [], onglet: 'tableau', flux: null, joueurs: [] };

  // --- Outils ---------------------------------------------------------------------------
  function el(tag, attrs = {}, ...enfants) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (k === 'texte') e.textContent = v;
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const x of enfants.flat()) if (x !== null && x !== undefined && x !== false) e.append(x instanceof Node ? x : String(x));
    return e;
  }

  async function api(chemin, options = {}) {
    const init = { method: options.methode || 'GET', headers: {}, credentials: 'same-origin' };
    if (init.method !== 'GET') init.headers['X-LQDM'] = '1';
    if (options.json !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(options.json);
    } else if (options.corps !== undefined) {
      init.body = options.corps;
    }
    const r = await fetch('/api/' + chemin, init);
    if (r.status === 401 && chemin !== 'connexion') { afficherConnexion(); throw new Error('connexion requise'); }
    const type = r.headers.get('Content-Type') || '';
    const d = type.includes('json') ? await r.json() : await r.text();
    if (!r.ok) throw new Error((d && d.erreur) || ('erreur ' + r.status));
    return d;
  }

  function note(texte, genre = 'ok') {
    const n = el('div', { class: 'note ' + genre, texte });
    $('#notes').append(n);
    setTimeout(() => n.remove(), genre === 'erreur' ? 7000 : 3500);
  }
  const echec = (e) => note(e.message, 'erreur');

  const octets = (n) => {
    if (!n && n !== 0) return '?';
    const u = ['o', 'Ko', 'Mo', 'Go', 'To'];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return n.toFixed(i ? 1 : 0).replace('.', ',') + ' ' + u[i];
  };
  const duree = (s) => {
    s = Math.floor(s || 0);
    const j = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    if (j) return j + ' j ' + h + ' h';
    if (h) return h + ' h ' + m + ' min';
    return m + ' min';
  };
  const depuis = (t) => {
    if (!t) return 'jamais';
    const s = Date.now() / 1000 - t;
    if (s < 90) return 'à l’instant';
    return 'il y a ' + duree(s);
  };
  const date = (t) => new Date(t * 1000).toLocaleString('fr-CA', { dateStyle: 'medium', timeStyle: 'short' });
  const nomServeur = (n) => ({ proxy: 'Proxy (Velocity)', spawn: 'Spawn', smp: 'Survie (SMP)' }[n] || n);
  const tete = (j) => el('img', {
    class: 'tete', alt: '', width: 28, height: 28, loading: 'lazy',
    src: j.edition === 'Java' && j.uuid ? 'https://mc-heads.net/avatar/' + j.uuid + '/28' : 'icone.svg',
  });

  // --- Connexion ------------------------------------------------------------------------
  function afficherConnexion() {
    fermerFlux();
    $('#app').hidden = true;
    $('#ecran-connexion').hidden = false;
    $('#form-connexion [name=compte]').focus();
  }

  $('#form-connexion').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    const err = $('#erreur-connexion');
    err.hidden = true;
    try {
      const d = await api('connexion', { methode: 'POST', json: { compte: f.compte.value.trim(), mot_de_passe: f.mot_de_passe.value } });
      f.mot_de_passe.value = '';
      demarrer(d.compte);
    } catch (x) {
      err.textContent = x.message;
      err.hidden = false;
    }
  });

  $('#deconnexion').addEventListener('click', async () => {
    try { await api('deconnexion', { methode: 'POST' }); } catch (_) { /* déjà déconnecté */ }
    afficherConnexion();
  });

  function demarrer(compte) {
    $('#compte-connecte').textContent = 'Connecté : ' + compte;
    $('#ecran-connexion').hidden = true;
    $('#app').hidden = false;
    ouvrir(location.hash.slice(1) || 'tableau');
  }

  // --- Onglets --------------------------------------------------------------------------
  const chargeurs = {
    tableau: chargerTableau, joueurs: chargerJoueurs, admins: chargerAdmins,
    console: ouvrirConsole, journaux: chargerJournaux, fichiers: chargerFichiers, historique: chargerHistorique,
  };
  function ouvrir(nom) {
    if (!chargeurs[nom]) nom = 'tableau';
    etat.onglet = nom;
    $$('.menu [data-onglet]').forEach((b) => b.classList.toggle('actif', b.dataset.onglet === nom));
    $$('.onglet').forEach((s) => { s.hidden = s.id !== nom; });
    history.replaceState(null, '', '#' + nom);
    if (nom !== 'console') fermerFlux();
    chargeurs[nom]();
  }
  $$('.menu [data-onglet]').forEach((b) => b.addEventListener('click', () => ouvrir(b.dataset.onglet)));

  function remplirChoix(select, avecProxy) {
    const avant = select.value;
    const noms = etat.serveurs.filter((s) => s.genre === 'paper' || (avecProxy && s.genre === 'proxy')).map((s) => s.nom);
    select.replaceChildren(...noms.map((n) => el('option', { value: n, texte: nomServeur(n) })));
    if (noms.includes(avant)) select.value = avant;
  }
  async function serveurs() {
    if (!etat.serveurs.length) {
      const d = await api('etat');
      etat.serveurs = d.serveurs;
    }
    return etat.serveurs;
  }

  // --- Tableau de bord ------------------------------------------------------------------
  function barre(pc) {
    const b = el('div', { class: 'barre' }, el('span'));
    b.firstChild.style.width = Math.min(100, Math.max(0, pc)) + '%';
    if (pc > 85) b.classList.add('haut');
    return b;
  }
  function tuile(titre, valeur, detail, pc) {
    return el('div', { class: 'carte tuile' }, el('span', { class: 'discret', texte: titre }),
      el('strong', { texte: valeur }), detail ? el('span', { class: 'discret', texte: detail }) : null,
      pc !== undefined ? barre(pc) : null);
  }

  async function actionServeur(nom, action) {
    const mots = { demarrer: 'Démarrer', arreter: 'Arrêter', redemarrer: 'Redémarrer', sauver: 'Sauvegarder le monde de' };
    if (action !== 'sauver' && !confirm(mots[action] + ' ' + nomServeur(nom) + ' ?')) return;
    note(mots[action] + ' ' + nomServeur(nom) + '…');
    try {
      await api('serveur/' + nom + '/' + action, { methode: 'POST' });
      note(nomServeur(nom) + ' : fait');
      etat.serveurs = [];
      if (etat.onglet === 'tableau') chargerTableau();
    } catch (e) { echec(e); }
  }
  function boutonsServeur(s, dansConsole) {
    const marche = s.etat === 'running';
    return el('div', { class: 'actions-serveur' },
      marche
        ? [el('button', { class: 'bouton', texte: 'Redémarrer', onclick: () => actionServeur(s.nom, 'redemarrer') }),
          el('button', { class: 'bouton danger', texte: 'Arrêter', onclick: () => actionServeur(s.nom, 'arreter') })]
        : el('button', { class: 'bouton principal', texte: 'Démarrer', onclick: () => actionServeur(s.nom, 'demarrer') }),
      marche && s.genre === 'paper' ? el('button', { class: 'bouton', texte: 'Sauver le monde', onclick: () => actionServeur(s.nom, 'sauver') }) : null,
      s.genre !== 'autre' && !dansConsole ? el('button', { class: 'bouton', texte: 'Console', onclick: () => { $('#serveur-console').dataset.voulu = s.nom; ouvrir('console'); } }) : null);
  }

  async function chargerTableau() {
    try {
      const d = await api('etat');
      etat.serveurs = d.serveurs;
      const sys = d.systeme || {};
      const total = d.serveurs.reduce((n, s) => n + (s.joueurs ? s.joueurs.length : 0), 0);
      const tuiles = [tuile('Joueurs connectés', String(total), 'sur tout le réseau')];
      if (sys.memoire) tuiles.push(tuile('Mémoire de la VM', octets(sys.memoire.utilise) + ' / ' + octets(sys.memoire.total), null, 100 * sys.memoire.utilise / sys.memoire.total));
      if (sys.charge) tuiles.push(tuile('Charge CPU', sys.charge[0].toFixed(2).replace('.', ','), (sys.coeurs || '?') + ' cœurs', 100 * sys.charge[0] / (sys.coeurs || 1)));
      if (sys.disque) tuiles.push(tuile('Disque', octets(sys.disque.utilise) + ' / ' + octets(sys.disque.total), null, 100 * sys.disque.utilise / sys.disque.total));
      if (sys.allume_depuis) tuiles.push(tuile('VM allumée depuis', duree(sys.allume_depuis)));
      $('#tuiles-systeme').replaceChildren(...tuiles);

      $('#serveurs').replaceChildren(...d.serveurs.map((s) => {
        const marche = s.etat === 'running';
        return el('article', { class: 'carte serveur' + (marche ? '' : ' eteint') },
          el('header', {}, el('span', { class: 'pastille ' + (marche ? 'verte' : 'rouge') }),
            el('h3', { texte: nomServeur(s.nom) }), el('span', { class: 'discret', texte: s.statut })),
          el('dl', {},
            el('dt', { texte: 'CPU' }), el('dd', { texte: s.cpu || '–' }),
            el('dt', { texte: 'Mémoire' }), el('dd', { texte: s.memoire || '–' }),
            s.joueurs ? [el('dt', { texte: 'Joueurs' }), el('dd', { texte: s.joueurs.length + ' / ' + s.max })] : null),
          s.joueurs && s.joueurs.length ? el('p', { class: 'joueurs-serveur', texte: s.joueurs.join(', ') }) : null,
          boutonsServeur(s));
      }));
      $('#maj-tableau').textContent = 'Mis à jour à ' + new Date().toLocaleTimeString('fr-CA');
    } catch (e) { echec(e); }
  }

  $('#form-annonce').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('annonce', { methode: 'POST', json: { texte: e.target.texte.value } });
      e.target.reset();
      note('Annonce envoyée');
    } catch (x) { echec(x); }
  });

  // --- Joueurs --------------------------------------------------------------------------
  async function actionJoueur(joueur, action, extra = {}) {
    try {
      const d = await api('joueur', { methode: 'POST', json: { joueur, action, ...extra } });
      const sorties = Object.entries(d.sorties || {}).map(([s, t]) => nomServeur(s) + ' : ' + (t || 'ok'));
      note(sorties[0] ? sorties.join(' · ').slice(0, 220) : 'Fait');
      return d;
    } catch (e) { echec(e); return null; }
  }

  function roles(j) {
    return el('span', { class: 'roles' },
      j.op ? el('span', { class: 'badge or', texte: 'Admin' }) : null,
      j.banni ? el('span', { class: 'badge rouge', texte: 'Banni' }) : null,
      j.liste_blanche ? el('span', { class: 'badge', texte: 'Liste blanche' }) : null,
      el('span', { class: 'badge discret', texte: j.edition }));
  }

  async function chargerJoueurs() {
    try {
      const d = await api('joueurs');
      etat.joueurs = d.joueurs;
      etat.paper = d.serveurs;
      afficherJoueurs();
    } catch (e) { echec(e); }
  }
  function afficherJoueurs() {
    const q = $('#filtre-joueurs').value.trim().toLowerCase();
    const liste = etat.joueurs.filter((j) => !q || j.nom.toLowerCase().includes(q));
    $('#liste-joueurs').replaceChildren(...(liste.length ? liste.map((j) => el('tr', {},
      el('td', {}, el('span', { class: 'joueur' }, tete(j), el('strong', { texte: j.nom }))),
      el('td', {}, j.en_ligne ? el('span', { class: 'badge vert', texte: 'En ligne · ' + nomServeur(j.en_ligne) }) : el('span', { class: 'discret', texte: 'Hors ligne' })),
      el('td', { texte: j.stats && j.stats.temps_jeu ? duree(j.stats.temps_jeu) : '–' }),
      el('td', { texte: j.en_ligne ? 'maintenant' : depuis(j.vu) }),
      el('td', {}, roles(j)),
      el('td', {}, el('button', { class: 'bouton', texte: 'Gérer', onclick: () => fiche(j) })),
    )) : [el('tr', {}, el('td', { colspan: 6, class: 'discret', texte: q ? 'Aucun joueur trouvé.' : 'Aucun joueur pour l’instant.' }))]));
  }
  $('#filtre-joueurs').addEventListener('input', afficherJoueurs);

  function fiche(j) {
    const s = j.stats || {};
    const recharger = async () => { await chargerJoueurs(); const n = etat.joueurs.find((x) => x.nom === j.nom); if (n) fiche(n); };
    const agir = (action, extra, confirmer) => async () => {
      if (confirmer && !confirm(confirmer)) return;
      if (await actionJoueur(j.nom, action, extra)) recharger();
    };
    const demander = (action, question, cle = 'valeur') => async () => {
      const v = prompt(question);
      if (v === null) return;
      if (await actionJoueur(j.nom, action, { [cle]: v })) recharger();
    };
    const choixServeur = el('select', {}, (etat.paper || []).map((n) => el('option', { value: n, texte: nomServeur(n) })));
    const choixMode = el('select', {}, [['survival', 'Survie'], ['creative', 'Créatif'], ['adventure', 'Aventure'], ['spectator', 'Spectateur']]
      .map(([v, t]) => el('option', { value: v, texte: t })));
    const infos = el('pre', { class: 'sortie', hidden: true });

    $('#contenu-fiche').replaceChildren(
      el('header', { class: 'entete-fiche' }, tete(j), el('div', {}, el('h2', { texte: j.nom }), roles(j))),
      el('dl', { class: 'infos' },
        el('dt', { texte: 'État' }), el('dd', { texte: j.en_ligne ? 'En ligne sur ' + nomServeur(j.en_ligne) : 'Hors ligne, vu ' + depuis(j.vu) + (j.vu_sur ? ' (' + nomServeur(j.vu_sur) + ')' : '') }),
        el('dt', { texte: 'UUID' }), el('dd', { class: 'code', texte: j.uuid || '?' }),
        el('dt', { texte: 'Temps de jeu' }), el('dd', { texte: s.temps_jeu ? duree(s.temps_jeu) : '–' }),
        el('dt', { texte: 'Morts' }), el('dd', { texte: String(s.morts ?? '–') }),
        el('dt', { texte: 'Monstres tués' }), el('dd', { texte: String(s.monstres_tues ?? '–') }),
        el('dt', { texte: 'Joueurs tués' }), el('dd', { texte: String(s.joueurs_tues ?? '–') }),
        el('dt', { texte: 'Distance parcourue' }), el('dd', { texte: s.distance ? s.distance.toLocaleString('fr-CA') + ' blocs' : '–' })),
      el('h3', { texte: 'Actions' }),
      el('div', { class: 'actions-joueur' },
        j.en_ligne ? [
          el('div', { class: 'ligne' }, choixServeur, el('button', { class: 'bouton', texte: 'Envoyer sur ce serveur', onclick: () => agir('envoyer', { valeur: choixServeur.value })() })),
          el('div', { class: 'ligne' }, choixMode, el('button', { class: 'bouton', texte: 'Changer le mode de jeu', onclick: () => agir('mode', { valeur: choixMode.value })() })),
          el('button', { class: 'bouton', texte: 'Message privé', onclick: demander('message', 'Message à ' + j.nom + ' :') }),
          el('button', { class: 'bouton', texte: 'Expulser', onclick: demander('expulser', 'Raison de l’expulsion (facultatif) :', 'raison') }),
        ] : null,
        j.op
          ? el('button', { class: 'bouton', texte: 'Retirer admin (deop)', onclick: agir('deop', {}, 'Retirer les droits d’admin à ' + j.nom + ' ?') })
          : el('button', { class: 'bouton', texte: 'Rendre admin (op)', onclick: agir('op', {}, 'Donner TOUS les droits (op) à ' + j.nom + ' ?') }),
        el('button', { class: 'bouton', texte: 'Donner un grade', onclick: demander('grade', 'Grade LuckPerms (ex. : default, vip, moderateur) :') }),
        j.liste_blanche
          ? el('button', { class: 'bouton', texte: 'Retirer de la liste blanche', onclick: agir('liste_blanche_retirer') })
          : el('button', { class: 'bouton', texte: 'Ajouter à la liste blanche', onclick: agir('liste_blanche_ajouter') }),
        j.banni
          ? el('button', { class: 'bouton', texte: 'Débannir', onclick: agir('debannir') })
          : el('button', { class: 'bouton danger', texte: 'Bannir', onclick: demander('bannir', 'Raison du bannissement de ' + j.nom + ' :', 'raison') }),
        el('button', { class: 'bouton', texte: 'Voir ses grades', onclick: async () => {
          const d = await actionJoueur(j.nom, 'infos');
          if (d) { infos.textContent = Object.values(d.sorties).join('\n'); infos.hidden = false; }
        } })),
      infos);
    const dlg = $('#fiche');
    if (!dlg.open) dlg.showModal();
  }

  // --- Admins ---------------------------------------------------------------------------
  async function chargerAdmins() {
    try {
      const d = await api('admins');
      $('#liste-admins').replaceChildren(...(d.admins.length ? d.admins.map((j) => el('div', { class: 'carte element' },
        el('span', { class: 'joueur' }, tete(j), el('strong', { texte: j.nom }), roles(j)),
        el('span', { class: 'discret', texte: j.en_ligne ? 'En ligne · ' + nomServeur(j.en_ligne) : 'vu ' + depuis(j.vu) }),
        el('button', { class: 'bouton', texte: 'Retirer admin', onclick: async () => {
          if (!confirm('Retirer les droits d’admin à ' + j.nom + ' ?')) return;
          if (await actionJoueur(j.nom, 'deop')) chargerAdmins();
        } }))) : [el('p', { class: 'discret', texte: 'Aucun admin (op) pour l’instant.' })]));
      $('#grades').textContent = d.grades || '';
    } catch (e) { echec(e); }
  }
  $('#form-admin').addEventListener('submit', async (e) => {
    e.preventDefault();
    const joueur = e.target.joueur.value.trim();
    if (!confirm('Donner TOUS les droits (op) à ' + joueur + ' sur tous les serveurs ?')) return;
    if (await actionJoueur(joueur, 'op')) { e.target.reset(); chargerAdmins(); }
  });

  // --- Console --------------------------------------------------------------------------
  function fermerFlux() {
    if (etat.flux) { etat.flux.close(); etat.flux = null; }
  }
  function ajouterConsole(texte, classe) {
    const sortie = $('#sortie-console');
    const enBas = sortie.scrollHeight - sortie.scrollTop - sortie.clientHeight < 40;
    const ligne = el('div', { class: classe || classeLigne(texte), texte });
    sortie.append(ligne);
    while (sortie.childElementCount > 3000) sortie.firstChild.remove();
    if (enBas) sortie.scrollTop = sortie.scrollHeight;
  }
  const classeLigne = (t) => (/\b(ERROR|SEVERE|Exception)\b/.test(t) ? 'l-erreur' : /\bWARN/.test(t) ? 'l-avert' : '');

  async function ouvrirConsole() {
    await serveurs().catch(echec);
    const choix = $('#serveur-console');
    remplirChoix(choix, true);
    if (choix.dataset.voulu) { choix.value = choix.dataset.voulu; delete choix.dataset.voulu; }
    brancherConsole();
  }
  function brancherConsole() {
    fermerFlux();
    const nom = $('#serveur-console').value;
    if (!nom) return;
    $('#sortie-console').replaceChildren();
    const s = etat.serveurs.find((x) => x.nom === nom);
    $('#actions-console').replaceChildren(...(s ? [boutonsServeur(s, true)] : []));
    etat.flux = new EventSource('/api/console/' + encodeURIComponent(nom) + '/flux?lignes=400');
    etat.flux.onmessage = (e) => ajouterConsole(JSON.parse(e.data));
    etat.flux.onerror = () => { /* EventSource se reconnecte tout seul */ };
  }
  $('#serveur-console').addEventListener('change', brancherConsole);
  const historiqueCommandes = [];
  let curseur = 0;
  $('#form-console').addEventListener('submit', async (e) => {
    e.preventDefault();
    const champ = e.target.commande;
    const commande = champ.value.trim();
    if (!commande) return;
    historiqueCommandes.push(commande);
    curseur = historiqueCommandes.length;
    champ.value = '';
    ajouterConsole('> ' + commande, 'l-commande');
    try {
      const d = await api('console/' + encodeURIComponent($('#serveur-console').value), { methode: 'POST', json: { commande } });
      if (d.sortie) ajouterConsole(d.sortie, 'l-reponse');
    } catch (x) { ajouterConsole(x.message, 'l-erreur'); }
  });
  $('#form-console [name=commande]').addEventListener('keydown', (e) => {
    if (e.key === 'ArrowUp' && curseur > 0) { e.preventDefault(); e.target.value = historiqueCommandes[--curseur]; }
    if (e.key === 'ArrowDown') { e.preventDefault(); curseur = Math.min(historiqueCommandes.length, curseur + 1); e.target.value = historiqueCommandes[curseur] || ''; }
  });

  // --- Journaux -------------------------------------------------------------------------
  let journalBrut = '';
  async function chargerJournaux() {
    await serveurs().catch(echec);
    remplirChoix($('#serveur-journaux'), true);
    const nom = $('#serveur-journaux').value;
    if (!nom) return;
    try {
      const d = await api('journaux/' + encodeURIComponent(nom));
      $('#liste-journaux').replaceChildren(...(d.journaux.length ? d.journaux.map((f) => el('button', {
        class: 'element-fichier', onclick: (e) => {
          $$('#liste-journaux .actif').forEach((b) => b.classList.remove('actif'));
          e.currentTarget.classList.add('actif');
          lireJournal(nom, f.nom);
        },
      }, el('strong', { texte: f.nom }), el('span', { class: 'discret', texte: date(f.date) + ' · ' + octets(f.taille) }))) : [el('p', { class: 'discret', texte: 'Aucun journal.' })]));
    } catch (e) { echec(e); }
  }
  async function lireJournal(serveur, nom) {
    $('#texte-journal').textContent = 'Chargement…';
    try {
      journalBrut = await api('journaux/' + encodeURIComponent(serveur) + '/' + encodeURIComponent(nom));
      const lien = $('#telecharger-journal');
      lien.href = '/api/journaux/' + encodeURIComponent(serveur) + '/' + encodeURIComponent(nom) + '?telecharger=1';
      lien.hidden = false;
      filtrerJournal();
      const t = $('#texte-journal');
      t.scrollTop = t.scrollHeight;
    } catch (e) { echec(e); }
  }
  function filtrerJournal() {
    const q = $('#filtre-journal').value.trim().toLowerCase();
    const lignes = q ? journalBrut.split('\n').filter((l) => l.toLowerCase().includes(q)) : journalBrut.split('\n');
    $('#texte-journal').textContent = lignes.join('\n') || 'Aucune ligne.';
  }
  $('#filtre-journal').addEventListener('input', filtrerJournal);
  $('#serveur-journaux').addEventListener('change', () => { journalBrut = ''; $('#texte-journal').textContent = 'Choisis un journal à gauche.'; $('#telecharger-journal').hidden = true; chargerJournaux(); });

  // --- Plugins et datapacks -------------------------------------------------------------
  async function chargerFichiers() {
    await serveurs().catch(echec);
    remplirChoix($('#serveur-fichiers'), true);
    const nom = $('#serveur-fichiers').value;
    const genre = $('#genre-fichiers').value;
    $('#genre-fichiers option[value=datapacks]').disabled = nom === 'proxy';
    if (nom === 'proxy' && genre === 'datapacks') { $('#genre-fichiers').value = 'plugins'; return chargerFichiers(); }
    $('#aide-depot').textContent = genre === 'plugins'
      ? ' Fichiers .jar, pour ' + nomServeur(nom) + (nom === 'proxy' ? ' (plugins Velocity)' : ' (plugins Paper)') + '.'
      : ' Fichiers .zip, pour le monde de ' + nomServeur(nom) + '.';
    $('#envoi-fichiers').accept = genre === 'plugins' ? '.jar' : '.zip';
    if (!nom) return;
    try {
      const d = await api('fichiers/' + encodeURIComponent(nom) + '/' + genre);
      $('#liste-fichiers').replaceChildren(...(d.fichiers.length ? d.fichiers.map((f) => {
        const base = 'fichiers/' + encodeURIComponent(nom) + '/' + genre + '/' + encodeURIComponent(f.nom);
        const agir = async (action, methode = 'POST', question) => {
          if (question && !confirm(question)) return;
          try {
            await api(action ? base + '/' + action : base, { methode });
            $('#avis-redemarrage').hidden = false;
            chargerFichiers();
          } catch (e) { echec(e); }
        };
        return el('div', { class: 'carte element' + (f.actif ? '' : ' eteint') },
          el('span', {}, el('strong', { texte: f.nom.replace(/\.desactive$/, '') }), f.actif ? null : el('span', { class: 'badge', texte: 'désactivé' })),
          el('span', { class: 'discret', texte: octets(f.taille) + ' · ' + date(f.date) }),
          el('span', { class: 'actions-serveur' },
            f.actif
              ? el('button', { class: 'bouton', texte: 'Désactiver', onclick: () => agir('desactiver') })
              : el('button', { class: 'bouton', texte: 'Activer', onclick: () => agir('activer') }),
            el('button', { class: 'bouton danger', texte: 'Supprimer', onclick: () => agir('', 'DELETE', 'Supprimer ' + f.nom + ' ?') })));
      }) : [el('p', { class: 'discret', texte: 'Aucun fichier.' })]));
    } catch (e) { echec(e); }
  }
  ['#serveur-fichiers', '#genre-fichiers'].forEach((s) => $(s).addEventListener('change', () => { $('#avis-redemarrage').hidden = true; chargerFichiers(); }));

  async function envoyerFichiers(fichiers) {
    const nom = $('#serveur-fichiers').value;
    const genre = $('#genre-fichiers').value;
    for (const f of fichiers) {
      note('Envoi de ' + f.name + ' (' + octets(f.size) + ')…');
      try {
        await api('fichiers/' + encodeURIComponent(nom) + '/' + genre + '/' + encodeURIComponent(f.name), { methode: 'PUT', corps: f });
        note(f.name + ' ajouté');
        $('#avis-redemarrage').hidden = false;
      } catch (e) { echec(e); }
    }
    chargerFichiers();
  }
  const depot = $('#depot');
  $('#envoi-fichiers').addEventListener('change', (e) => { envoyerFichiers([...e.target.files]); e.target.value = ''; });
  ['dragenter', 'dragover'].forEach((t) => depot.addEventListener(t, (e) => { e.preventDefault(); depot.classList.add('survol'); }));
  ['dragleave', 'drop'].forEach((t) => depot.addEventListener(t, () => depot.classList.remove('survol')));
  depot.addEventListener('drop', (e) => { e.preventDefault(); envoyerFichiers([...e.dataTransfer.files]); });
  $('#redemarrer-fichiers').addEventListener('click', async () => {
    await actionServeur($('#serveur-fichiers').value, 'redemarrer');
    $('#avis-redemarrage').hidden = true;
  });

  // --- Historique -----------------------------------------------------------------------
  async function chargerHistorique() {
    try {
      const d = await api('historique');
      $('#liste-historique').replaceChildren(...(d.historique.length ? d.historique.map((h) => el('tr', {},
        el('td', { texte: date(h.date) }), el('td', {}, el('strong', { texte: h.compte })),
        el('td', { texte: h.action }), el('td', { class: 'code', texte: h.details }))) : [el('tr', {}, el('td', { colspan: 4, class: 'discret', texte: 'Rien pour l’instant.' }))]));
    } catch (e) { echec(e); }
  }

  // Le tableau de bord se rafraîchit tout seul.
  setInterval(() => {
    if (!document.hidden && !$('#app').hidden && etat.onglet === 'tableau') chargerTableau();
  }, 10000);

  // --- Démarrage ------------------------------------------------------------------------
  api('session').then((d) => demarrer(d.compte)).catch(() => afficherConnexion());
})();
