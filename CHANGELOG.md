# Changelog

## [1.2.0] - 2026-09-16

### Corrige
- Collision avec le port 8090 de Kodi : l'interface web essaie maintenant 8090 puis 8091-8099.
- Une collision de port web ne fait plus echouer toute la session audio/ffmpeg.
- Detection du port ffmpeg sans connexion TCP : compatible avec `-listen 1` de ffmpeg.
- Nettoyage ffmpeg plus prudent : le PID est verifie comme appartenant bien a ffmpeg avant envoi de SIGTERM/SIGKILL.
- Reconnexion ffmpeg plus robuste apres un arret inattendu.
- Recherche de chaine/audio normalisee avec accents et suffixes HD/FHD/UHD.
- Lecture des playlists bornee pour eviter une consommation memoire excessive avec un M3U enorme.

### Securite
- Interface web authentifiee par un jeton genere automatiquement si aucun jeton n'est configure.
- Validation stricte des actions API et des valeurs offset/volume.
- Limite de taille du corps POST.
- Limite du nombre de lignes de logs demandees via HTTP.
- Ecritures des presets via fichier temporaire puis remplacement atomique.
- Acces concurrent aux presets protege par verrou.
- Echappement HTML conserve pour les noms de presets et les valeurs affichees.

### Ajoute
- Port web effectif affiche dans l'etat de l'interface.
- Port ffmpeg effectif affiche dans l'interface.
- Fallback automatique du port ffmpeg si le port prefere est deja utilise.
- Jeton web persistant genere localement dans le profil de l'addon.
- Endpoint d'etat sans cache et API plus explicite en cas d'erreur.

## [1.1.0] - 2026-09-15

### Corrige
- Bug critique : la page d'accueil de l'interface web plantait systematiquement (UnicodeEncodeError sur un emoji mal echappe).
- Detection du port ffmpeg fiabilisee.
- Correspondance de nom de chaine/audio : le fallback approximatif est refuse en cas d'ambiguite.
- Compatibilite des niveaux de log Kodi 18 -> 21+.
- Arret de l'ancien processus ffmpeg plus propre.

### Ajoute
- Jeton d'acces optionnel pour l'interface web.
- Validation/bornage des valeurs d'offset et de volume.
- Presets avec identifiant stable.

## [1.0.0] - 2026-09-15

### Ajouté
- Fusion vidéo + audio via ffmpeg
- Menu contextuel Kodi
- Interface web de contrôle
- Décalage audio réglable
- Volume du commentaire
- Presets
- Reconnexion automatique
- Support CoreELEC / LibreELEC
