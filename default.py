# -*- coding: utf-8 -*-
import os
import time
import signal
import subprocess
import binascii
import unicodedata

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
WEB_TOKEN_FILE = os.path.join(PROFILE_DIR, 'web.token')

WEB_PORT = 8090
WEB_PORT_MAX = 8099
FFMPEG_PORT_DEFAULT = 5588
STEP_MS = 100
STEP_MS_BIG = 500
OFFSET_LIMIT_MS = 60000
MAX_M3U_ENTRIES = 10000
MAX_NAME_LEN = 512

_LOG_LEVEL = getattr(xbmc, 'LOGINFO', None)
if _LOG_LEVEL is None:
    _LOG_LEVEL = getattr(xbmc, 'LOGNOTICE', 2)


def log(msg):
    try:
        xbmc.log('[{0}] {1}'.format(ADDON_ID, msg), level=_LOG_LEVEL)
    except Exception:
        pass


def clamp(value, lo, hi, default=0):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(lo, min(hi, value))


def notify(msg, error=False, time_ms=3500):
    icon = xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO
    xbmcgui.Dialog().notification(ADDON_NAME, msg, icon, time_ms)


def normalize(s):
    if not s:
        return u''
    try:
        if not isinstance(s, unicode):
            s = s.decode('utf-8', 'ignore')
    except NameError:
        if isinstance(s, bytes):
            s = s.decode('utf-8', 'ignore')
    s = s.strip().lower()
    try:
        s = unicodedata.normalize('NFKD', s)
        s = u''.join(c for c in s if not unicodedata.combining(c))
    except Exception:
        pass
    for suffix in [u' hd+', u' fhd', u' uhd', u' 4k', u' hd', u' sd']:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
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
            title = (parts[1].strip() if len(parts) > 1 else u'Sans nom')[:MAX_NAME_LEN]
        elif not line.startswith('#'):
            url = line[:4096]
            entries.append((url, (title or url)[:MAX_NAME_LEN]))
            title = None
            if len(entries) >= MAX_M3U_ENTRIES:
                log('Playlist limitee a {0} entrees'.format(MAX_M3U_ENTRIES))
                break
    return entries


def find_url_by_name(entries, name):
    if not name:
        return None
    target = normalize(name)
    exact = []
    for url, title in entries:
        if normalize(title) == target and url not in exact:
            exact.append(url)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    candidates = []
    for url, title in entries:
        t = normalize(title)
        if t and (target in t or t in target) and url not in candidates:
            candidates.append(url)
    return candidates[0] if len(candidates) == 1 else None


def name_by_url(entries, url):
    for u, t in entries:
        if u == url:
            return t
    return u''


def get_current_channel_name():
    if not xbmc.getCondVisibility('Pvr.IsPlayingTv'):
        return None
    for label in ('VideoPlayer.ChannelName', 'ListItem.ChannelName', 'Player.ChannelName'):
        value = xbmc.getInfoLabel(label)
        if value:
            return value
    return None


def get_current_video_url(video_entries):
    name = get_current_channel_name()
    if not name:
        return None, None
    return find_url_by_name(video_entries, name), name


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
        try:
            return clamp(f.read(), -OFFSET_LIMIT_MS, OFFSET_LIMIT_MS)
        finally:
            f.close()
    except Exception:
        return 0


def write_offset(ms):
    try:
        f = xbmcvfs.File(OFFSET_FILE, 'w')
        try:
            f.write(str(clamp(ms, -OFFSET_LIMIT_MS, OFFSET_LIMIT_MS)))
        finally:
            f.close()
    except Exception:
        pass


def read_pid():
    try:
        f = xbmcvfs.File(PID_FILE, 'r')
        try:
            return int(f.read())
        finally:
            f.close()
    except Exception:
        return None


def _proc_cmdline(pid):
    try:
        f = open('/proc/{0}/cmdline'.format(int(pid)), 'rb')
        try:
            return f.read().replace(b'\x00', b' ')
        finally:
            f.close()
    except Exception:
        return b''


def is_ffmpeg_pid(pid):
    if not pid:
        return False
    return b'ffmpeg' in _proc_cmdline(pid).lower()


def is_pid_alive(pid):
    if not pid or not is_ffmpeg_pid(pid):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_previous_ffmpeg():
    pid = read_pid()
    if not pid or not is_ffmpeg_pid(pid):
        try:
            xbmcvfs.delete(PID_FILE)
        except Exception:
            pass
        return
    try:
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + 3.0
        while time.time() < deadline and is_pid_alive(pid):
            time.sleep(0.1)
        if is_pid_alive(pid):
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


def _proc_port_listening(port):
    needle = '{0:04X}'.format(int(port)).upper()
    for path in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            f = open(path, 'r')
            try:
                for line in f.readlines()[1:]:
                    fields = line.split()
                    if len(fields) >= 4:
                        local = fields[1]
                        state = fields[3]
                        if local.rsplit(':', 1)[-1].upper() == needle and state == '0A':
                            return True
            finally:
                f.close()
        except Exception:
            pass
    return False


def _ss_port_listening(port):
    try:
        out = subprocess.check_output(['ss', '-ltn'], stderr=subprocess.STDOUT)
        if isinstance(out, bytes):
            out = out.decode('utf-8', 'ignore')
        for line in out.splitlines():
            if 'LISTEN' in line and (':{0} '.format(port) in line or line.rstrip().endswith(':{0}'.format(port))):
                return True
    except Exception:
        pass
    return False


def port_listening(port):
    return _proc_port_listening(port) or _ss_port_listening(port)


def wait_port_open(port, timeout=15):
    # CRITIQUE : ne jamais ouvrir de connexion TCP ici. ffmpeg utilise
    # -listen 1 et la premiere connexion disponible est reservee a Kodi.
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_listening(port):
            return True
        time.sleep(0.25)
    return False


def choose_ffmpeg_port(preferred):
    preferred = clamp(preferred, 1024, 65535, FFMPEG_PORT_DEFAULT)
    candidates = [preferred]
    for port in range(preferred + 1, min(preferred + 11, 65535)):
        candidates.append(port)
    for port in candidates:
        if not port_listening(port):
            return port
    return preferred


def build_cmd(ffmpeg, video_url, audio_url, offset_ms, port, ua, volume):
    ua_opt = ['-user_agent', ua] if ua else []
    recon = ['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5']
    voff = []
    aoff = []
    if offset_ms > 0:
        aoff = ['-itsoffset', '{:.3f}'.format(offset_ms / 1000.0)]
    elif offset_ms < 0:
        voff = ['-itsoffset', '{:.3f}'.format(abs(offset_ms) / 1000.0)]
    cmd = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'warning']
    cmd += ua_opt + recon + voff + ['-i', video_url]
    cmd += ua_opt + recon + aoff + ['-i', audio_url]
    cmd += ['-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac',
            '-b:a', '128k', '-ac', '2']
    if int(volume) != 100:
        cmd += ['-af', 'volume={0}'.format(float(volume) / 100.0)]
    cmd += ['-f', 'mpegts', '-listen', '1',
            'http://127.0.0.1:{0}/live.ts'.format(port)]
    return cmd


def _start_one_ffmpeg(ffmpeg, video_url, audio_url, offset_ms, volume, port, ua):
    cmd = build_cmd(ffmpeg, video_url, audio_url, offset_ms, port, ua, volume)
    log('Lancement ffmpeg sur 127.0.0.1:{0}'.format(port))
    try:
        logf = open(LOG_FILE, 'ab')
        proc = subprocess.Popen(cmd, stdout=logf, stderr=logf,
                                preexec_fn=os.setsid, close_fds=True)
        logf.close()
    except Exception as exc:
        log('Popen ffmpeg echoue: {0}'.format(exc))
        return None
    try:
        pf = xbmcvfs.File(PID_FILE, 'w')
        try:
            pf.write(str(proc.pid))
        finally:
            pf.close()
    except Exception:
        pass
    time.sleep(0.7)
    if proc.poll() is not None:
        return None
    if not wait_port_open(port, timeout=12):
        log('Port ffmpeg {0} non detecte'.format(port))
        kill_previous_ffmpeg()
        return None
    return proc


def start_ffmpeg(video_url, audio_url, offset_ms, volume=100):
    ffmpeg = ADDON.getSetting('ffmpeg_path') or '/opt/bin/ffmpeg'
    try:
        preferred = int(ADDON.getSetting('http_port') or str(FFMPEG_PORT_DEFAULT))
    except (TypeError, ValueError):
        preferred = FFMPEG_PORT_DEFAULT
    ua = ADDON.getSetting('user_agent') or ''

    if not (os.path.isfile(ffmpeg) or xbmcvfs.exists(ffmpeg)):
        notify(u'ffmpeg introuvable: ' + ffmpeg, error=True)
        return None

    kill_previous_ffmpeg()
    time.sleep(0.2)
    port = choose_ffmpeg_port(preferred)
    proc = _start_one_ffmpeg(ffmpeg, video_url, audio_url, offset_ms, volume, port, ua)
    if not proc:
        return None
    write_offset(offset_ms)
    webserver.update_state(ffmpeg_pid=proc.pid, ffmpeg_port=port)
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
        webserver.update_state(status='error', error='ffmpeg')
        return False
    play(m)
    xbmc.sleep(800)
    webserver.update_state(status='running', offset=offset, volume=volume, error='')
    return True


def get_web_token():
    configured = ADDON.getSetting('web_token') or ''
    if configured:
        return configured.strip()[:128]
    try:
        f = xbmcvfs.File(WEB_TOKEN_FILE, 'r')
        try:
            token = f.read().strip()
        finally:
            f.close()
        if token:
            return token
    except Exception:
        pass
    token = binascii.hexlify(os.urandom(16)).decode('ascii')
    try:
        f = xbmcvfs.File(WEB_TOKEN_FILE, 'w')
        try:
            f.write(token)
        finally:
            f.close()
    except Exception:
        pass
    return token


def web_url():
    port = webserver.get_port() or WEB_PORT
    ip = xbmc.getIPAddress() or 'IP_DE_LA_BOX'
    token = webserver.get_token()
    return 'http://{0}:{1}/?token={2}'.format(ip, port, token)


def main():
    video_entries = parse_m3u(ADDON.getSetting('video_m3u'))
    audio_entries = parse_m3u(ADDON.getSetting('audio_m3u'))
    web_token = get_web_token()

    video_url, channel_name = get_current_video_url(video_entries)
    if not video_url:
        if channel_name:
            notify(u"Chaine '{0}' introuvable ou ambiguë".format(channel_name), error=True)
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
                           offset=offset, volume=volume, status='starting',
                           ffmpeg_pid=0, ffmpeg_port=0, error='')
    server = webserver.start_server(
        command_queue=q,
        presets_file=PRESETS_FILE,
        log_file=LOG_FILE,
        channels=[t for _, t in video_entries],
        audios=[t for _, t in audio_entries],
        preferred_port=WEB_PORT,
        max_port=WEB_PORT_MAX,
        web_token=web_token)

    if server is not None:
        url = web_url()
        notify(u'Web: ' + url, time_ms=5000)
        log('Interface web active sur le port {0}'.format(webserver.get_port()))
    else:
        notify(u'Interface web indisponible; lecture maintenue', error=True)
        log('Impossible de demarrer l interface web')

    if not apply_and_play(video_url, audio_url, offset, volume):
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
            command = q.get_nowait()
        except Q.Empty:
            command = None

        if command:
            action = command.get('action')
            value = command.get('value')

            if action == 'stop':
                break
            elif action == 'restart':
                webserver.update_state(status='restarting')
                apply_and_play(video_url, audio_url, offset, volume)
            elif action == 'offset':
                offset = clamp(offset + clamp(value, -STEP_MS_BIG, STEP_MS_BIG),
                               -OFFSET_LIMIT_MS, OFFSET_LIMIT_MS)
                webserver.update_state(status='restarting')
                apply_and_play(video_url, audio_url, offset, volume)
            elif action == 'set_offset':
                offset = clamp(value, -OFFSET_LIMIT_MS, OFFSET_LIMIT_MS)
                webserver.update_state(status='restarting')
                apply_and_play(video_url, audio_url, offset, volume)
            elif action == 'reset':
                offset = 0
                webserver.update_state(status='restarting')
                apply_and_play(video_url, audio_url, 0, volume)
            elif action == 'set_volume':
                volume = clamp(value, 0, 200, default=100)
                webserver.update_state(status='restarting')
                apply_and_play(video_url, audio_url, offset, volume)
            elif action == 'switch_channel':
                new_url = find_url_by_name(video_entries, value)
                if new_url:
                    video_url = new_url
                    channel_name = value
                    webserver.update_state(channel=channel_name, status='restarting')
                    apply_and_play(video_url, audio_url, offset, volume)
            elif action == 'switch_audio':
                new_url = find_url_by_name(audio_entries, value)
                if new_url:
                    audio_url = new_url
                    audio_name = value
                    webserver.update_state(audio=audio_name, status='restarting')
                    apply_and_play(video_url, audio_url, offset, volume)
            elif action == 'load_preset':
                p = value or {}
                nv = find_url_by_name(video_entries, p.get('channel', ''))
                na = find_url_by_name(audio_entries, p.get('audio', ''))
                if nv and na:
                    video_url, audio_url = nv, na
                    channel_name, audio_name = p.get('channel', ''), p.get('audio', '')
                    offset = clamp(p.get('offset', 0), -OFFSET_LIMIT_MS, OFFSET_LIMIT_MS)
                    volume = clamp(p.get('volume', 100), 0, 200, default=100)
                    webserver.update_state(channel=channel_name, audio=audio_name,
                                           offset=offset, volume=volume, status='restarting')
                    apply_and_play(video_url, audio_url, offset, volume)

        state = webserver.get_state()
        if state.get('status') == 'running':
            pid = read_pid()
            if pid and not is_pid_alive(pid):
                log('ffmpeg mort -> reconnexion automatique')
                webserver.update_state(status='reconnecting', error='')
                if not apply_and_play(video_url, audio_url, offset, volume):
                    webserver.update_state(status='error', error='reconnexion ffmpeg impossible')

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
