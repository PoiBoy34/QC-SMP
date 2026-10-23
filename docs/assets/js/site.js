// Site LQDM : menu mobile, état du serveur, boutons Copier, page Jouer, filtre des
// nouvelles et recherche du wiki. Les réglages (adresse, dépôt…) viennent de _config.yml.
(() => {
  const R = window.LQDM || {};
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  // --- En-tête : menu mobile, fond au défilement ----------------------------------------
  const entete = $('[data-entete]');
  const boutonMenu = $('[data-menu]');
  if (boutonMenu) {
    boutonMenu.addEventListener('click', () => {
      const ouvert = entete.classList.toggle('ouvert');
      boutonMenu.setAttribute('aria-expanded', String(ouvert));
    });
  }
  const defiler = () => entete && entete.classList.toggle('defile', window.scrollY > 8);
  window.addEventListener('scroll', defiler, { passive: true });
  defiler();

  // --- État du serveur -----------------------------------------------------------------
  const etats = $$('[data-etat]');
  if (etats.length && R.adresse) {
    fetch('https://api.mcsrvstat.us/3/' + R.adresse)
      .then((r) => r.json())
      .then((s) => {
        const n = s.players ? s.players.online : 0;
        const texte = s.online
          ? 'Serveur en ligne · ' + n + (n > 1 ? ' joueurs connectés' : ' joueur connecté')
          : 'Serveur fermé pour le moment';
        etats.forEach((e) => {
          e.classList.toggle('en-ligne', Boolean(s.online));
          $('[data-etat-texte]', e).textContent = texte;
          e.hidden = false;
        });
      })
      .catch(() => {});
  }

  // --- Boutons Copier ------------------------------------------------------------------
  function copier(texte) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(texte);
    const zone = document.createElement('textarea');
    zone.value = texte;
    document.body.appendChild(zone);
    zone.select();
    document.execCommand('copy');
    zone.remove();
    return Promise.resolve();
  }
  $$('[data-copier]').forEach((b) => {
    const libelle = b.textContent;
    b.addEventListener('click', () => {
      copier(b.dataset.copier).then(() => {
        b.textContent = 'Copié !';
        setTimeout(() => { b.textContent = libelle; }, 1500);
      }).catch(() => {});
    });
  });

  // --- Page Jouer : onglets selon l'appareil, lien direct vers la dernière version -----
  const onglets = $$('.onglet');
  function ouvrir(id) {
    onglets.forEach((o) => {
      const actif = o.getAttribute('aria-controls') === id;
      o.setAttribute('aria-selected', String(actif));
      document.getElementById(o.getAttribute('aria-controls')).hidden = !actif;
    });
  }
  if (onglets.length) {
    onglets.forEach((o) => o.addEventListener('click', () => {
      const id = o.getAttribute('aria-controls');
      ouvrir(id);
      history.replaceState(null, '', '#' + id);
    }));
    const ua = navigator.userAgent;
    const mobile = /Android|iPhone|iPad|iPod/i.test(ua) || (navigator.maxTouchPoints > 1 && /Macintosh/.test(ua));
    const linux = /Linux/i.test(ua) && !/Android/i.test(ua);
    const mac = /Macintosh|Mac OS X/i.test(ua) && !mobile;
    const depuisAdresse = () => {
      const id = location.hash.slice(1);
      if (document.getElementById(id) && onglets.some((o) => o.getAttribute('aria-controls') === id)) { ouvrir(id); return true; }
      return false;
    };
    if (!depuisAdresse() && mobile) ouvrir('mobile');
    window.addEventListener('hashchange', depuisAdresse);

    const message = (t) => { const m = $('#message-appareil'); m.textContent = t; m.hidden = false; };
    if (mobile) {
      ['bouton-principal', 'sous-bouton', 'autres'].forEach((id) => { $('#' + id).hidden = true; });
      message("Tu es sur téléphone ou tablette : pas besoin du launcher, suis les étapes juste en dessous. " +
              "Le launcher, c'est pour jouer sur un ordinateur.");
    } else if (mac) {
      message("Le launcher n'existe pas encore sur Mac : joue avec Minecraft Java et l'adresse " + R.adresse + '.');
    } else if (linux) {
      $('#bouton-texte').textContent = 'Télécharger pour Linux';
      $('#sous-bouton').textContent = 'Gratuit · fichier AppImage';
      $('#autres').innerHTML = 'Sur Windows ? <a id="lien-windows" href="https://github.com/' + R.depot + '/releases/latest">Prends la version Windows</a>';
    }

    fetch('https://api.github.com/repos/' + R.depot + '/releases/latest')
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((release) => {
        const fichier = (fin) => release.assets.find((a) => a.name.endsWith(fin));
        const exe = fichier('.exe');
        const appimage = fichier('.AppImage');
        const mo = (a) => Math.round(a.size / 1048576) + ' Mo';
        const version = release.tag_name.replace(/^v/, '');
        if (linux && appimage) {
          $('#bouton-principal').href = appimage.browser_download_url;
          $('#sous-bouton').textContent = 'Gratuit · AppImage · version ' + version + ' · ' + mo(appimage);
          if (exe && $('#lien-windows')) $('#lien-windows').href = exe.browser_download_url;
        } else if (exe) {
          $('#bouton-principal').href = exe.browser_download_url;
          $('#sous-bouton').textContent = 'Gratuit · Windows 10 et 11 · version ' + version + ' · ' + mo(exe);
          if (appimage) $('#lien-linux').href = appimage.browser_download_url;
        }
      })
      .catch(() => { /* les liens restent sur la page des versions de GitHub */ });
  }

  // --- Nouvelles : filtre par catégorie ------------------------------------------------
  const filtre = $('[data-filtre]');
  if (filtre) {
    filtre.addEventListener('change', () => {
      let n = 0;
      $$('.grille-articles .carte-article').forEach((a) => {
        const garde = !filtre.value || a.dataset.categorie === filtre.value;
        a.hidden = !garde;
        if (garde) n += 1;
      });
      $('[data-vide]').hidden = n > 0;
    });
  }

  // --- Wiki : recherche instantanée ----------------------------------------------------
  const simple = (t) => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const echapper = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  $$('[data-recherche]').forEach((form) => {
    const champ = $('input', form);
    const liste = $('.resultats', form);
    let index = null;
    let choix = -1;
    const charger = () => index || (index = fetch(form.dataset.recherche)
      .then((r) => r.json())
      .then((docs) => docs.map((d) => ({ ...d, t: simple(d.titre), c: simple(d.categorie + ' ' + d.texte) }))));

    function afficher(resultats, q) {
      choix = -1;
      if (!q) { liste.hidden = true; return; }
      liste.innerHTML = resultats.length
        ? resultats.map((d) => '<li><a href="' + d.url + '">' + echapper(d.titre) + '<small>' + echapper(d.categorie) + '</small></a></li>').join('')
        : '<li class="aucun">Aucun article trouvé. <a href="' + form.dataset.support + '">Demande au support</a>.</li>';
      liste.hidden = false;
    }
    function chercher() {
      const q = simple(champ.value).trim();
      const mots = q.split(/\s+/).filter(Boolean);
      if (!mots.length) { afficher([], ''); return; }
      charger().then((docs) => {
        const resultats = docs
          .map((d) => {
            if (!mots.every((m) => d.t.includes(m) || d.c.includes(m))) return null;
            return { d, score: mots.reduce((s, m) => s + (d.t.includes(m) ? 3 : 1), 0) };
          })
          .filter(Boolean)
          .sort((a, b) => b.score - a.score)
          .slice(0, 8)
          .map((x) => x.d);
        afficher(resultats, q);
      }).catch(() => {});
    }
    function surligner(i) {
      const liens = $$('a', liste).filter((a) => !a.closest('.aucun'));
      if (!liens.length) return;
      choix = (i + liens.length) % liens.length;
      liens.forEach((a, j) => a.classList.toggle('actif', j === choix));
      liens[choix].scrollIntoView({ block: 'nearest' });
    }
    champ.addEventListener('input', chercher);
    champ.addEventListener('focus', () => { charger(); if (champ.value) chercher(); });
    champ.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); surligner(choix + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); surligner(choix - 1); }
      else if (e.key === 'Escape') { liste.hidden = true; }
    });
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const liens = $$('a', liste).filter((a) => !a.closest('.aucun'));
      const cible = liens[Math.max(choix, 0)];
      if (cible) location.href = cible.href;
    });
    document.addEventListener('click', (e) => { if (!form.contains(e.target)) liste.hidden = true; });

    const q = new URLSearchParams(location.search).get('q');
    if (q && form === $('[data-recherche]')) { champ.value = q; chercher(); champ.focus(); }
  });
})();
