<p align="center">
  <img src="icon.png" alt="TV Audio Sync" width="180">
</p>

# TV Audio Sync — Addon Kodi

Fusionne en direct, via **ffmpeg**, la vidéo d'une chaîne TV IPTV avec un flux audio externe (commentaire sportif, radio, etc.) choisi dans une seconde playlist M3U.

Kodi ne lit normalement pas deux flux indépendants pour cette utilisation. L'addon demande donc à **ffmpeg** de produire un flux MPEG-TS local contenant la vidéo et l'audio externe, puis Kodi lit ce flux unique.

## Fonctionnalités

- Fusion vidéo + audio en un seul flux
- Décalage audio réglable en direct (±100 / ±500 ms)
- Volume du commentaire ajustable (0–200 %)
- Changement de chaîne / d'audio en direct
- Presets avec identifiant stable
- Interface web de contrôle
- Authentification par jeton généré automatiquement si aucun jeton n'est configuré
- Fallback automatique du port web si 8090 est déjà utilisé par Kodi ou un autre service
- Fallback automatique du port ffmpeg si le port configuré est occupé
- Affichage du PID et du port ffmpeg dans l'interface
- Logs ffmpeg consultables depuis le navigateur
- Reconnexion automatique si ffmpeg s'arrête
- Compatible Kodi 18 / Python 2.7 tout en restant préparé pour les versions plus récentes

## Prérequis

- Kodi 18 (Leia) ou supérieur
- Box sous CoreELEC, LibreELEC ou Linux
- ffmpeg installé (par exemple via Entware sur CoreELEC)
- IPTV Simple Client configuré avec un M3U vidéo
- Un second M3U pour les flux audio

## Installation

### 1. Installer ffmpeg

En SSH sur la box :

    installentware
    # La box redémarre
    opkg update
    opkg install ffmpeg
    which ffmpeg

Le chemin par défaut de l'addon est `/opt/bin/ffmpeg`.

### 2. Installer l'addon

Téléchargez le ZIP de la release puis, dans Kodi :

Extensions → icône dossier ouvert → installer depuis un fichier ZIP.

### 3. Configurer

Kodi → Extensions → Mes extensions → Programmes → TV Audio Sync → Configurer.

- Fichier M3U des chaînes TV : le même que dans IPTV Simple Client
- Fichier M3U des commentaires audio : votre playlist audio
- Chemin de ffmpeg : `/opt/bin/ffmpeg`
- Port local ffmpeg : `5588` par défaut
- User-Agent : vide sauf si nécessaire
- Jeton web : laisser vide pour que l'addon en génère automatiquement un, ou définir votre propre jeton

## Utilisation

1. Lancez une chaîne TV depuis IPTV Simple Client.
2. Ouvrez le menu contextuel.
3. Choisissez **Commentaire audio (chaine en cours)**.
4. Sélectionnez le commentaire audio.
5. L'addon démarre ffmpeg puis remplace la lecture par le flux fusionné.
6. Une notification affiche l'URL exacte de l'interface web.

### Interface web

Le serveur essaie le port **8090**, puis **8091 à 8099** si le port précédent est déjà utilisé. Cela évite notamment le conflit avec l'interface web intégrée de Kodi.

L'URL affichée par Kodi ressemble à :

    http://IP_DE_LA_BOX:8091/?token=...

Le port réel peut donc être différent de 8090.

L'interface permet :

- **Live** : offset, volume, stop et état ffmpeg
- **Chaînes** : changement de chaîne à la volée
- **Audios** : changement de commentaire
- **Presets** : sauvegarde, chargement et suppression
- **Logs** : consultation des dernières lignes ffmpeg

## Sécurité

L'interface web est protégée par un jeton. Si aucun jeton n'est configuré dans les paramètres, un jeton aléatoire est généré et conservé dans le profil de l'addon.

Les requêtes de commande sont validées :

- offset limité à ±60000 ms
- volume limité à 0–200 %
- taille des POST limitée
- nombre de lignes de logs limité
- actions HTTP limitées à la liste prévue par l'addon
- presets protégés contre les écritures concurrentes

Ne partagez pas l'URL contenant le jeton avec des personnes non autorisées.

## Point important : ffmpeg `-listen 1`

L'addon **ne se connecte jamais au port ffmpeg pour vérifier qu'il est ouvert**.

C'est volontaire : ffmpeg utilise `-listen 1`, donc une connexion de test pourrait consommer l'unique connexion disponible avant que Kodi ne lise le flux.

La disponibilité est vérifiée via `/proc/net/tcp`, `/proc/net/tcp6` ou `ss` sans ouvrir de connexion TCP.

## Dépannage

### Le site web ne s'ouvre plus

Regardez la notification Kodi : le port peut avoir basculé de 8090 vers 8091–8099.

Sur la box :

    netstat -tlnp | grep -E "8090|8091|8092|8093|8094|8095|8096|8097|8098|8099"

### ffmpeg ne démarre pas

    which ffmpeg
    netstat -tln | grep 5588

L'addon peut choisir automatiquement un port voisin si 5588 est déjà occupé.

### ffmpeg quitte immédiatement

Consultez :

    tail -f /storage/.kodi/userdata/addon_data/script.tvaudiosync/ffmpeg.log

### Écran noir / timeout Kodi

Vérifiez que l'URL vidéo et l'URL audio renvoient bien les flux attendus. Un endpoint HTML à la place d'un flux média provoquera l'échec de ffmpeg.

### Logs Kodi

    tail -f /storage/.kodi/temp/kodi.log

## Licence

MIT — voir LICENSE.
