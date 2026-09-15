# -*- coding: utf-8 -*-
import os
import time
import socket
import signal
import subprocess

import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon

import webserver

try:
    import Queue as Q
except ImportError:
    import queue as Q

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')

try:
    PROFILE_DIR = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
except AttributeError:
    PROFILE_DIR = xbmc.translatePath(ADDON.getAddonInfo('profile'))

if not xbmcvfs.exists(PROFILE_DIR):
    xbmcvfs.mkdirs(PROFILE_DIR)

PID_FILE = os.path.join(PROFILE_DIR, 'ffmpeg.pid')
OFFSET_FILE = os.path.join(PROFILE_DIR, 'offset.txt')
LOG_FILE = os.path.join(PROFILE_DIR, 'ffmpeg.log')
PRESETS_FILE = os.path.join(PROFILE_DIR, 'presets.json')

WEB_PORT = 8090
STEP_MS = 100
STEP_MS_BIG = 500


def log(msg):
    xbmc.log('[{0}] {1}'.format(ADDON_ID, msg), level=xbmc.LOGNOTICE)


def notify(msg, error=False, time_ms=3500):
    icon = xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO
    xbmcgui.Dialog().notification(ADDON_NAME, msg, icon, time_ms)


def normalize(s):
    if not s:
        return u''
    s = s.lower().strip()
    for old, new in [(u'\u00e9', 'e'), (u'\u00e8', 'e'), (u'\u00ea', 'e'),
                     (u'\u00e0', 'a'), (u'\u00e2', 'a'), (u'\u00ee', 'i'),
                     (u'\u00ef', 'i'), (u'\u00f4', 'o'), (u'\u00fb', 'u'),
                     (u'\u00f9', 'u'), (u'\u00e7', 'c')]:
        s = s.replace(old, new)
    for suffix in [u' hd', u' fhd', u' uhd', u' 4k', u' sd', u' hd+']:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    return u' '.join(s.split())


def parse_m3u(path):
    entries = []
    if not path:
        return entries
    try:
        f = xbmcvfs.File(path, 'r')
        try:
            raw = f.read()
        finally:
            f.close()
    except Exception as exc:
        log('Lecture M3U impossible ({0}): {1}'.format(path, exc))
        return entries
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', 'ignore')
    title = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#EXTINF'):
            parts = line.split(',', 1)
            title = parts[1].strip() if len(parts) > 1 else u'Sans nom'
        elif not line.startswith('#'):
            entries.append((line, title or line))
            title = None
    return entries


def find_url_by_name(entries, name):
    if not name:
        return None
    target = normalize(name)
    for url, title in entries:
        if normalize(title) == target:
            return url
    for url, title in entries:
        t = normalize(title)
        if t and (target in t or t in target):
            return url
    return None


def name_by_url(entries, url):
    for u, t in entries:
        if u == url:
            return t
    return u''


def get_current_channel_name():
    if not xbmc.getCondVisibility('Pvr.IsPlayingTv'):
        return None
    for label in ('VideoPlayer.ChannelName', 'ListItem.ChannelName',
                  'Player.ChannelName'):
        v = xbmc.getInfoLabel(label)
        if v:
            return v
    return None


def get_current_video_url(video_entries):
    name = get_current_channel_name()
    if not name:
        return None, None
    url = find_url_by_name(video_entries, name)
    return url, name


def choose_video_manually(video_entries):
    if not video_entries:
        notify(u'Playlist video vide', error=True)
        return None, None
    labels = [t for _, t in video_entries]
    idx = xbmcgui.Dialog().select(u'Choisir une chaine TV', labels)
    if idx < 0:
        return None, None
    return video_entries[idx][0], video_entries[idx][1]


def choose_audio(audio_entries):
    if not audio_entries:
        notify(u'Playlist audio vide', error=True)
        return None
    labels = [t for _, t in audio_entries]
    idx = xbmcgui.Dialog().select(u'Choisir un commentaire audio', labels)
    if idx < 0:
        return None
    return audio_entries[idx][0]


def read_offset():
    try:
        f = xbmcvfs.File(OFFSET_FILE, 'r')
        v = f.read()
        f.close()
        return int(v)
    except Exception:
        return 0


def write_offset(ms):
    try:
        f = xbmcvfs.File(OFFSET_FILE, 'w')
        f.write(str(int(ms)))
        f.close()
    except Exception:
        pass


def read_pid():
    try:
        f = xbmcvfs.File(PID_FILE, 'r')
        v = f.read()
        f.close()
        return int(v)
    except Exception:
        return None


def is_pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_previous_ffmpeg():
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.3)
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        except OSError:
            pass
    try:
        xbmcvfs.delete(PID_FILE)
    except Exception:
        pass


def wait_port_open(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            out = subprocess.check_output(
                ['netstat', '-tln'], stderr=subprocess.STDOUT)
            if isinstance(out, bytes):
                out = out.decode('utf-8', 'ignore')
            if ':{0} '.format(port) in out:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def build_cmd(ffmpeg, video_url, audio_url, offset_ms, port, ua, volume):
    ua_opt = ['-user_agent', ua] if ua else []
    recon = ['-reconnect', '1', '-reconnect_streamed', '1',
             '-reconnect_delay_max', '5']
    voff = []
    aoff = []
    if offset_ms > 0:
        aoff = ['-itsoffset', '{:.3f}'.format(offset_ms / 1000.0)]
    elif offset_ms < 0:
        voff = ['-itsoffset', '{:.3f}'.format(abs(offset_ms) / 1000.0)]
    cmd = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'warning']
    cmd += ua_opt + recon + voff + ['-i', video_url]
    cmd += ua_opt + recon + aoff + ['-i', audio_url]
    cmd += [
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '128k', '-ac', '2',
    ]
    if int(volume) != 100:
        cmd += ['-af', 'volume={0}'.format(float(volume) / 100.0)]
    cmd += [
        '-f', 'mpegts',
        '-listen', '1',
        'http://127.0.0.1:{0}/live.ts'.format(port),
    ]
    return cmd


def start_ffmpeg(video_url, audio_url, offset_ms, volume=100):
    ffmpeg = ADDON.getSetting('ffmpeg_path') or '/opt/bin/ffmpeg'
    try:
        port = int(ADDON.getSetting('http_port') or '5588')
    except ValueError:
        port = 5588
    ua = ADDON.getSetting('user_agent') or ''

    if not xbmcvfs.exists(ffmpeg):
        notify(u'ffmpeg introuvable: ' + ffmpeg, error=True)
        return None

    kill_previous_ffmpeg()
    time.sleep(0.5)

    cmd = build_cmd(ffmpeg, video_url, audio_url, offset_ms, port, ua, volume)
    log('Lancement: {0}'.format(' '.join(cmd)))

    try:
        with open(LOG_FILE, 'wb'):
            pass
        logf = open(LOG_FILE, 'ab')
        proc = subprocess.Popen(cmd, stdout=logf, stderr=logf,
                                preexec_fn=os.setsid, close_fds=True)
    except Exception as exc:
        notify(u'Echec lancement ffmpeg', error=True)
        log('Popen echoue: {0}'.format(exc))
        return None

    try:
        pf = xbmcvfs.File(PID_FILE, 'w')
        pf.write(str(proc.pid))
        pf.close()
    except Exception:
        pass

    time.sleep(1.0)
    if proc.poll() is not None:
        notify(u'ffmpeg a quitte immediatement', error=True)
        return None

    if not wait_port_open(port, timeout=12):
        notify(u"ffmpeg n'ouvre pas le port {0}".format(port), error=True)
        kill_previous_ffmpeg()
        return None

    write_offset(offset_ms)
    return 'http://127.0.0.1:{0}/live.ts'.format(port)


def play(url):
    li = xbmcgui.ListItem(path=url)
    li.setProperty('IsPlayable', 'true')
    try:
        li.setMimeType('video/mp2t')
        li.setContentLookup(False)
    except Exception:
        pass
    xbmc.Player().play(url, li)


def apply_and_play(video_url, audio_url, offset, volume):
    m = start_ffmpeg(video_url, audio_url, offset, volume)
    if not m:
        return False
    pid = read_pid()
    webserver.update_state(ffmpeg_pid=pid or 0)
    play(m)
    xbmc.sleep(800)
    webserver.update_state(status='running', offset=offset, volume=volume)
    return True


def main():
    video_entries = parse_m3u(ADDON.getSetting('video_m3u'))
    audio_entries = parse_m3u(ADDON.getSetting('audio_m3u'))

    video_url, channel_name = get_current_video_url(video_entries)
    if not video_url:
        if channel_name:
            notify(u"Chaine '{0}' introuvable".format(channel_name))
        video_url, channel_name = choose_video_manually(video_entries)
        if not video_url:
            return

    audio_url = choose_audio(audio_entries)
    if not audio_url:
        return
    audio_name = name_by_url(audio_entries, audio_url)

    offset = read_offset()
    volume = 100

    q = Q.Queue()
    webserver.START_TIME = time.time()
    webserver.update_state(channel=channel_name or '', audio=audio_name or '',
                           offset=offset, volume=volume,
                           status='starting', ffmpeg_pid=0, error='')

    webserver.start_server(
        command_queue=q,
        presets_file=PRESETS_FILE,
        log_file=LOG_FILE,
        channels=[t for _, t in video_entries],
        audios=[t for _, t in audio_entries],
        port=WEB_PORT)

    ip = xbmc.getIPAddress() or 'IP_DE_LA_BOX'
    notify(u'Web: http://{0}:{1}'.format(ip, WEB_PORT), time_ms=4000)
    log('Interface web : http://{0}:{1}'.format(ip, WEB_PORT))

    if not apply_and_play(video_url, audio_url, offset, volume):
        webserver.update_state(status='error')
        notify(u'Retour a la chaine TV', error=True)
        try:
            play(video_url)
        except Exception:
            pass
        webserver.stop_server()
        return

    monitor = xbmc.Monitor()
    player = xbmc.Player()

    while not monitor.abortRequested():
        try:
            c = q.get_nowait()
        except Q.Empty:
            c = None

        if c:
            action = c.get('action')
            value = c.get('value')

            if action == 'stop':
                break

            if action == 'offset':
                offset += int(value or 0)
                webserver.update_state(status='restarting')
                apply_and_play(video_url, audio_url, offset, volume)

            elif action == 'set_offset':
                offset = int(value or 0)
                webserver.update_state(status='restarting')
                apply_and_play(video_url, audio_url, offset, volume)

            elif action == 'reset':
                offset = 0
                webserver.update_state(status='restarting')
                apply_and_play(video_url, audio_url, 0, volume)

            elif action == 'set_volume':
                volume = int(value or 100)
                webserver.update_state(status='restarting')
                apply_and_play(video_url, audio_url, offset, volume)

            elif action == 'switch_channel':
                new_url = find_url_by_name(video_entries, value)
                if new_url:
                    video_url = new_url
                    channel_name = value
                    webserver.update_state(channel=channel_name,
                                           status='restarting')
                    apply_and_play(video_url, audio_url, offset, volume)

            elif action == 'switch_audio':
                new_url = find_url_by_name(audio_entries, value)
                if new_url:
                    audio_url = new_url
                    audio_name = value
                    webserver.update_state(audio=audio_name,
                                           status='restarting')
                    apply_and_play(video_url, audio_url, offset, volume)

            elif action == 'load_preset':
                p = value or {}
                nv = find_url_by_name(video_entries, p.get('channel', ''))
                na = find_url_by_name(audio_entries, p.get('audio', ''))
                if nv and na:
                    video_url = nv
                    audio_url = na
                    channel_name = p.get('channel', '')
                    audio_name = p.get('audio', '')
                    offset = int(p.get('offset', 0))
                    volume = int(p.get('volume', 100))
                    webserver.update_state(channel=channel_name,
                                           audio=audio_name,
                                           offset=offset, volume=volume,
                                           status='restarting')
                    apply_and_play(video_url, audio_url, offset, volume)

        # Reconnexion auto si ffmpeg est mort
        if webserver.STATE.get('status') == 'running':
            pid = read_pid()
            if pid and not is_pid_alive(pid):
                log('ffmpeg mort -> reconnexion auto')
                webserver.update_state(status='reconnecting')
                if not apply_and_play(video_url, audio_url, offset, volume):
                    webserver.update_state(status='error')

        if not player.isPlaying():
            break
        if monitor.waitForAbort(1):
            break

    webserver.update_state(status='idle', ffmpeg_pid=0)
    webserver.stop_server()
    kill_previous_ffmpeg()
    log('Session terminee')


if __name__ == '__main__':
    main()
