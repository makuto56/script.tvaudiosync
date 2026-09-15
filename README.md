<p align="center">
  <img src="icon.png" alt="TV Audio Sync" width="180">
</p>

# TV Audio Sync — Addon Kodi

Fusionne en direct, via **ffmpeg**, la vidéo d'une chaîne TV IPTV avec un flux
audio externe (commentaire sportif, radio, etc.) choisi dans une seconde
playlist M3U.

Kodi ne peut pas lire deux flux en parallèle. Cet addon contourne la limite en
demandant à `ffmpeg` de coller la vidéo et l'audio en un **seul flux local**,
que Kodi lit ensuite normalement. Résultat : image et son parfaitement
synchronisés, sans coupure.

## Fonctionnalités

- Fusion vidéo + audio en un seul flux
- Décalage audio réglable en direct (±100 / ±500 ms)
- Volume du commentaire ajustable (0–200 %)
- Changement de chaîne / d'audio en direct
- Presets : sauvegardez vos combinaisons préférées
- Interface web complète (port 8090)
- Statistiques système (CPU, RAM, température)
- Logs ffmpeg consultables depuis le navigateur
- Reconnexion automatique si ffmpeg plante

## Prérequis

- Kodi 18 (Leia) ou supérieur
- Box sous CoreELEC, LibreELEC ou Linux
- ffmpeg installé (via Entware sur CoreELEC)
- IPTV Simple Client configuré avec un M3U vidéo
- Un second M3U pour les flux audio

## Installation

### 1. Installer ffmpeg

En SSH sur la box :

    installentware
    # La box redémarre
    opkg update
    opkg install ffmpeg
    which ffmpeg    # doit renvoyer /opt/bin/ffmpeg

### 2. Installer l'addon

Téléchargez le zip depuis les Releases, puis dans Kodi :
Extensions → icône dossier ouvert → sélectionnez le zip.

### 3. Configurer

Kodi → Extensions → Mes extensions → Programmes → TV Audio Sync → Configurer.

- Fichier M3U des chaînes TV : le même que dans IPTV Simple Client
- Fichier M3U des commentaires audio : votre playlist audio
- Chemin de ffmpeg : /opt/bin/ffmpeg
- Port local : 5589
- User-Agent : vide sauf si nécessaire
- Jeton d'accès interface web : optionnel, mais recommandé si votre box
  est sur un réseau partagé (le port 8090 n'a pas d'authentification par
  défaut). Une fois défini, ouvrez `http://IP_DE_LA_BOX:8090/?token=VOTRE_JETON`.

## Utilisation

1. Lancez une chaîne TV depuis IPTV Simple Client
2. Menu contextuel (bouton menu ou C sur la télécommande)
3. Choisissez "Commentaire audio (chaine en cours)"
4. Sélectionnez le commentaire dans la liste
5. Attendez 2-3 secondes → le flux fusionné démarre
6. Une notification affiche l'adresse web : http://IP_DE_LA_BOX:8090

### Interface web

Ouvrez http://IP_DE_LA_BOX:8090 dans un navigateur :

- **Live** : réglage offset, volume, stop
- **Chaînes** : changement de chaîne à la volée
- **Audios** : changement de commentaire à la volée
- **Presets** : sauvegarde/chargement de combinaisons
- **Logs** : dernières lignes ffmpeg

## Limitations connues

- Un seul client à la fois (option -listen 1 de ffmpeg)
- Dérive possible sur de très longues sessions
- Nécessite ffmpeg

## Dépannage

### "ffmpeg a quitté immédiatement"

Vérifiez le chemin :

    which ffmpeg

### "ffmpeg n'ouvre pas le port"

Tue les anciens ffmpeg :

    pkill -9 -f ffmpeg
    netstat -tln | grep 5589

### Écran noir, Kodi timeout

Vérifiez que l'URL audio renvoie bien un flux audio :

    curl -sIL 'http://votre-url-audio' | grep -i content-type

Si vous voyez text/html, l'URL est mauvaise.

### Logs

    tail -f /storage/.kodi/temp/kodi.log
    tail -f /storage/.kodi/userdata/addon_data/script.tvaudiosync/ffmpeg.log

## Licence

MIT — voir LICENSE.
