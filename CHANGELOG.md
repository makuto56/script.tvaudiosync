# Changelog

## [1.1.0] - 2026-09-15

### Corrige
- Bug critique : la page d'accueil de l'interface web plantait systematiquement
  (UnicodeEncodeError sur un emoji mal echappe), rendant l'UI inutilisable
- Detection du port ffmpeg fiabilisee (connexion TCP directe au lieu de
  parser `netstat`, absent sur certaines boxes)
- Correspondance de nom de chaine/audio : le fallback approximatif est
  desormais refuse en cas d'ambiguite (ex. "France 2" vs "France 24")
- `xbmc.LOGNOTICE` remplace par un choix compatible Kodi 18 -> 21+
- Arret de l'ancien processus ffmpeg plus propre (attente reelle avant
  SIGKILL au lieu d'un delai fixe)

### Ajoute
- Jeton d'acces optionnel pour l'interface web (parametre "Interface web")
- Validation/bornage des valeurs d'offset et de volume recues via l'UI web

### Securite
- Correction d'une faille XSS stockee dans l'affichage des presets
- Suppression/chargement de preset par identifiant stable au lieu d'un
  index de tableau (evite les erreurs en cas de modifications concurrentes)

## [1.0.0] - 2026-09-15

### Ajouté
- Fusion vidéo + audio via ffmpeg
- Menu contextuel Kodi
- Interface web de contrôle (port 8090)
- Décalage audio réglable
- Volume du commentaire
- Presets
- Reconnexion automatique
- Support CoreELEC / LibreELEC
