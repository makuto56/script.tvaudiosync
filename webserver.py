# -*- coding: utf-8 -*-
import os
import json
import time
import threading

try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

WEB_PORT = 8090
WEB_PORT_MAX = 8099
START_TIME = time.time()
COMMAND_QUEUE = None
PRESETS_FILE = None
LOG_FILE = None
M3U_CHANNELS = []
M3U_AUDIOS = []
WEB_TOKEN = ''
WEB_BIND = '0.0.0.0'
_SERVER = None
WEB_ACTUAL_PORT = 0

STATE = {
    'channel': '', 'audio': '', 'offset': 0, 'volume': 100,
    'status': 'idle', 'ffmpeg_pid': 0, 'ffmpeg_port': 0,
    'web_port': 0, 'error': ''
}
_STATE_LOCK = threading.Lock()
_PRESET_LOCK = threading.Lock()


class _Reuse(HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def update_state(**kwargs):
    with _STATE_LOCK:
        STATE.update(kwargs)


def get_state():
    with _STATE_LOCK:
        return dict(STATE)


def get_port():
    return WEB_ACTUAL_PORT


def get_token():
    return WEB_TOKEN


HTML = u"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TV Audio Sync</title><style>*{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#1a1a1a;color:#e0e0e0;margin:0;padding:16px;max-width:900px;margin:auto}h1{font-size:20px;margin:0 0 12px;color:#4ea1ff}.tabs{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}.tab{padding:8px 14px;background:#2a2a2a;border:none;color:#e0e0e0;border-radius:6px;cursor:pointer;font-size:14px}.tab.on{background:#4ea1ff;color:#fff}.panel{display:none;background:#242424;padding:16px;border-radius:8px}.panel.on{display:block}.status{display:grid;grid-template-columns:auto 1fr;gap:8px;margin-bottom:16px;font-size:14px}.status .lbl{color:#888}.big{font-size:36px;font-weight:bold;color:#ffd54f;text-align:center;margin:16px}.row{display:flex;gap:8px;margin:8px 0;flex-wrap:wrap;align-items:center}button{padding:10px 18px;font-size:15px;background:#4ea1ff;color:#fff;border:none;border-radius:6px;cursor:pointer}button.d{background:#d33}button.s{background:#555}input,select{font-size:15px;padding:8px;background:#333;color:#eee;border:1px solid #444;border-radius:6px;width:100%}select{height:auto}pre{background:#111;color:#ddd;padding:12px;border-radius:6px;overflow:auto;max-height:400px;font-size:12px;line-height:1.4;white-space:pre-wrap}.badge{padding:2px 8px;border-radius:4px;font-size:12px}.b-r{background:#2e7d32;color:#fff}.b-i{background:#555;color:#ccc}.b-e{background:#c62828;color:#fff}label{display:block;margin-top:12px;margin-bottom:4px;color:#aaa;font-size:13px}.item{display:flex;justify-content:space-between;align-items:center;padding:8px;background:#2a2a2a;border-radius:6px;margin-bottom:6px;gap:8px}.item span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}</style></head><body><h1>TV Audio Sync</h1><div class="tabs"><button class="tab on" data-p="live">Live</button><button class="tab" data-p="channels">Cha&icirc;nes</button><button class="tab" data-p="audios">Audios</button><button class="tab" data-p="presets">Presets</button><button class="tab" data-p="logs">Logs</button></div><div class="panel on" id="p-live"><div class="status"><span class="lbl">Statut</span><span id="st-status">-</span><span class="lbl">Cha&icirc;ne</span><span id="st-channel">-</span><span class="lbl">Audio</span><span id="st-audio">-</span><span class="lbl">Uptime</span><span id="st-uptime">-</span><span class="lbl">PID ffmpeg</span><span id="st-pid">-</span><span class="lbl">Port ffmpeg</span><span id="st-fport">-</span></div><div class="big" id="st-offset">0 ms</div><div class="row" style="justify-content:center"><button onclick="cmd('offset',-500)">-500</button><button onclick="cmd('offset',-100)">-100</button><button onclick="cmd('offset',100)">+100</button><button onclick="cmd('offset',500)">+500</button></div><div class="row"><input id="in-offset" type="number" placeholder="Offset manuel (ms)"><button onclick="setOff()">Appliquer</button><button class="s" onclick="cmd('reset')">Reset 0</button></div><label>Volume commentaire : <span id="vol-val">100</span>%</label><input id="in-vol" type="range" min="0" max="200" step="5" value="100" oninput="document.getElementById('vol-val').textContent=this.value"><div class="row"><button onclick="setVol()">Appliquer volume</button></div><div class="row" style="margin-top:20px"><button class="d" onclick="cmd('stop')">Stop</button></div></div><div class="panel" id="p-channels"><p>Choisis une cha&icirc;ne.</p><label>Filtre :</label><input id="ch-filter" placeholder="Rechercher..." oninput="renderCh()"><label>Cha&icirc;ne :</label><select id="ch-sel" size="10"></select><div class="row"><button onclick="switchCh()">Basculer</button></div></div><div class="panel" id="p-audios"><p>Choisis le commentaire audio.</p><label>Filtre :</label><input id="au-filter" placeholder="Rechercher..." oninput="renderAu()"><label>Audio :</label><select id="au-sel" size="10"></select><div class="row"><button onclick="switchAu()">Basculer</button></div></div><div class="panel" id="p-presets"><p>Enregistre la combinaison actuelle.</p><label>Nom du preset :</label><div class="row"><input id="pr-name" placeholder="Ex: TF1 FR"><button onclick="savePreset()">Enregistrer</button></div><div id="pr-list" style="margin-top:16px"></div></div><div class="panel" id="p-logs"><div class="row"><button onclick="refreshLog()">Rafra&icirc;chir</button><span style="color:#888">50 derni&egrave;res lignes</span></div><pre id="log-box">Chargement...</pre></div><script>var tabs=document.querySelectorAll('.tab');tabs.forEach(function(t){t.onclick=function(){tabs.forEach(function(x){x.classList.remove('on');});document.querySelectorAll('.panel').forEach(function(x){x.classList.remove('on');});t.classList.add('on');document.getElementById('p-'+t.dataset.p).classList.add('on');if(t.dataset.p==='logs')refreshLog();if(t.dataset.p==='channels')refreshCh();if(t.dataset.p==='audios')refreshAu();if(t.dataset.p==='presets')refreshPr();};});var channels=[],audios=[],presets=[];var TOKEN=__TOKEN_JSON__;function esc(s){return String(s==null?'':s).replace(/[&<>\"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c];});}function api(u,o){o=o||{};o.headers=o.headers||{};if(TOKEN)o.headers['X-Auth-Token']=TOKEN;return fetch(u,o).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();});}function cmd(a,v){return api('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a,value:v||0})}).then(refresh).catch(function(){});}function setOff(){var v=parseInt(document.getElementById('in-offset').value)||0;cmd('set_offset',v);}function setVol(){var v=parseInt(document.getElementById('in-vol').value)||100;cmd('set_volume',v);}function fmtUp(s){if(s<60)return s+'s';if(s<3600)return Math.floor(s/60)+'m '+Math.floor(s%60)+'s';return Math.floor(s/3600)+'h '+Math.floor((s%3600)/60)+'m';}function refresh(){api('/api/state').then(function(s){var cls=s.status==='running'?'b-r':(s.status==='error'?'b-e':'b-i');document.getElementById('st-status').innerHTML='<span class="badge '+cls+'">'+esc(s.status)+'</span>';document.getElementById('st-channel').textContent=s.channel||'-';document.getElementById('st-audio').textContent=s.audio||'-';document.getElementById('st-uptime').textContent=fmtUp(s.uptime);document.getElementById('st-pid').textContent=s.ffmpeg_pid||'-';document.getElementById('st-fport').textContent=s.ffmpeg_port||'-';document.getElementById('st-offset').textContent=(s.offset>0?'+':'')+s.offset+' ms';document.getElementById('in-vol').value=s.volume;document.getElementById('vol-val').textContent=s.volume;}).catch(function(){});}function refreshCh(){api('/api/channels').then(function(d){channels=d;renderCh();}).catch(function(){});}function renderCh(){var f=(document.getElementById('ch-filter').value||'').toLowerCase(),sel=document.getElementById('ch-sel');sel.innerHTML='';(channels.list||[]).forEach(function(n){if(f&&n.toLowerCase().indexOf(f)<0)return;var o=document.createElement('option');o.value=n;o.textContent=(n===channels.current?'&gt; ':'  ')+n;sel.appendChild(o);});}function refreshAu(){api('/api/audios').then(function(d){audios=d;renderAu();}).catch(function(){});}function renderAu(){var f=(document.getElementById('au-filter').value||'').toLowerCase(),sel=document.getElementById('au-sel');sel.innerHTML='';(audios.list||[]).forEach(function(n){if(f&&n.toLowerCase().indexOf(f)<0)return;var o=document.createElement('option');o.value=n;o.textContent=(n===audios.current?'&gt; ':'  ')+n;sel.appendChild(o);});}function switchCh(){var v=document.getElementById('ch-sel').value;if(v)cmd('switch_channel',v);}function switchAu(){var v=document.getElementById('au-sel').value;if(v)cmd('switch_audio',v);}function refreshPr(){api('/api/presets').then(function(d){presets=d.presets||[];renderPr();}).catch(function(){});}function renderPr(){var box=document.getElementById('pr-list');box.innerHTML='';if(!presets.length){box.innerHTML='<p style="color:#888">Aucun preset.</p>';return;}presets.forEach(function(p){var d=document.createElement('div');d.className='item';d.innerHTML='<span><b>'+esc(p.name)+'</b><br><small style="color:#888">'+esc(p.channel)+' &rarr; '+esc(p.audio)+' ('+esc(p.offset)+'ms, '+esc(p.volume)+'%)</small></span>';var b1=document.createElement('button');b1.textContent='&gt;';b1.onclick=function(){cmd('load_preset',p.id);};var b2=document.createElement('button');b2.textContent='X';b2.className='d';b2.onclick=function(){cmd('delete_preset',p.id);setTimeout(refreshPr,400);};d.appendChild(b1);d.appendChild(b2);box.appendChild(d);});}function savePreset(){var n=document.getElementById('pr-name').value;if(!n)return;cmd('save_preset',n);setTimeout(refreshPr,500);}function refreshLog(){api('/api/log?lines=50').then(function(d){document.getElementById('log-box').textContent=(d.lines||[]).join('\n')||'(vide)';}).catch(function(){});}setInterval(function(){if(document.getElementById('p-live').classList.contains('on'))refresh();},2000);refresh();</script></body></html>"""

LOGIN_HTML = u"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TV Audio Sync</title><style>body{font-family:system-ui,sans-serif;background:#1a1a1a;color:#e0e0e0;padding:32px;max-width:520px;margin:auto}code{background:#2a2a2a;padding:2px 6px;border-radius:4px}</style></head><body><h2>Acces protege</h2><p>Un jeton d'acces est configure. Utilisez l'URL fournie par Kodi.</p></body></html>"""


def _safe_int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _presets_load_unlocked():
    if not PRESETS_FILE or not os.path.exists(PRESETS_FILE):
        return []
    try:
        f = open(PRESETS_FILE, 'r')
        try:
            data = json.load(f)
        finally:
            f.close()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _presets_save_unlocked(presets):
    if not PRESETS_FILE:
        return
    tmp = PRESETS_FILE + '.tmp'
    try:
        f = open(tmp, 'w')
        try:
            json.dump(presets, f, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        finally:
            f.close()
        os.rename(tmp, PRESETS_FILE)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def _presets_load():
    with _PRESET_LOCK:
        data = _presets_load_unlocked()
        changed = False
        for i, p in enumerate(data):
            if isinstance(p, dict) and not p.get('id'):
                p['id'] = 'legacy-{0}'.format(i)
                changed = True
        if changed:
            _presets_save_unlocked(data)
        return data


def _presets_save(presets):
    with _PRESET_LOCK:
        _presets_save_unlocked(presets)


def _qs_get(path, key, default=''):
    if '?' not in path:
        return default
    try:
        from urllib.parse import unquote
    except ImportError:
        from urllib import unquote
    for kv in path.split('?', 1)[1].split('&'):
        k, _, v = kv.partition('=')
        if k == key:
            return unquote(v)[:1024]
    return default


class Handler(BaseHTTPRequestHandler):
    server_version = 'TVAudioSync/1.2'
    sys_version = ''

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        try:
            data = json.dumps(obj).encode('utf-8')
        except Exception:
            data = b'{"error":"serialization"}'
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _html(self, txt, code=200):
        data = txt.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        if not WEB_TOKEN:
            return False
        tok = self.headers.get('X-Auth-Token', '') or _qs_get(self.path, 'token', '')
        return tok == WEB_TOKEN

    def do_GET(self):
        p = self.path.split('?', 1)[0]
        if p in ('/', '/index.html'):
            if not self._authorized():
                return self._html(LOGIN_HTML, code=401)
            return self._html(HTML.replace('__TOKEN_JSON__', json.dumps(WEB_TOKEN)))
        if not self._authorized():
            return self._json({'error': 'unauthorized'}, code=401)
        if p == '/api/state':
            s = get_state()
            s['uptime'] = int(time.time() - START_TIME)
            return self._json(s)
        if p == '/api/channels':
            return self._json({'current': get_state().get('channel', ''), 'list': M3U_CHANNELS})
        if p == '/api/audios':
            return self._json({'current': get_state().get('audio', ''), 'list': M3U_AUDIOS})
        if p == '/api/presets':
            return self._json({'presets': _presets_load()})
        if p == '/api/log':
            n = _safe_int(_qs_get(self.path, 'lines', '50'), 50, 1, 200)
            lines = []
            if LOG_FILE and os.path.exists(LOG_FILE):
                try:
                    f = open(LOG_FILE, 'r')
                    try:
                        lines = [l.rstrip() for l in f.readlines()[-n:]]
                    finally:
                        f.close()
                except Exception:
                    pass
            return self._json({'lines': lines})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path.split('?', 1)[0] != '/api/cmd':
            self.send_response(404)
            self.end_headers()
            return
        if not self._authorized():
            return self._json({'error': 'unauthorized'}, code=401)
        try:
            ln = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            ln = 0
        if ln < 0 or ln > 8192:
            return self._json({'error': 'invalid body'}, code=413)
        try:
            body = self.rfile.read(ln).decode('utf-8') if ln else '{}'
            data = json.loads(body)
        except Exception:
            return self._json({'error': 'invalid json'}, code=400)
        if not isinstance(data, dict):
            return self._json({'error': 'invalid json'}, code=400)
        a = data.get('action')
        v = data.get('value')
        allowed = ('stop', 'restart', 'offset', 'set_offset', 'reset', 'set_volume', 'switch_channel', 'switch_audio', 'save_preset', 'delete_preset', 'load_preset')
        if a not in allowed:
            return self._json({'error': 'unknown action'}, code=400)
        if a in ('offset', 'set_offset'):
            try:
                v = max(-60000, min(60000, int(v)))
            except (TypeError, ValueError):
                return self._json({'error': 'invalid offset'}, code=400)
        elif a == 'set_volume':
            try:
                v = max(0, min(200, int(v)))
            except (TypeError, ValueError):
                return self._json({'error': 'invalid volume'}, code=400)
        elif a in ('switch_channel', 'switch_audio'):
            if not isinstance(v, (str, bytes)):
                return self._json({'error': 'invalid name'}, code=400)
            v = v[:512]
        elif a == 'save_preset':
            if not isinstance(v, (str, bytes)):
                return self._json({'error': 'invalid preset name'}, code=400)
            v = v.strip()[:128]
            if not v:
                return self._json({'error': 'empty preset name'}, code=400)
            snap = get_state()
            with _PRESET_LOCK:
                ps = _presets_load_unlocked()
                ps.append({'id': str(int(time.time() * 1000)), 'name': v,
                           'channel': snap.get('channel', ''), 'audio': snap.get('audio', ''),
                           'offset': max(-60000, min(60000, int(snap.get('offset', 0)))),
                           'volume': max(0, min(200, int(snap.get('volume', 100))))})
                _presets_save_unlocked(ps)
            return self._json({'ok': True})
        elif a == 'delete_preset':
            v = str(v)[:128]
            with _PRESET_LOCK:
                ps = [x for x in _presets_load_unlocked() if str(x.get('id')) != v]
                _presets_save_unlocked(ps)
            return self._json({'ok': True})
        elif a == 'load_preset':
            v = str(v)[:128]
            preset = None
            with _PRESET_LOCK:
                for x in _presets_load_unlocked():
                    if str(x.get('id')) == v:
                        preset = x
                        break
            if preset is None:
                return self._json({'ok': False}, code=404)
            if COMMAND_QUEUE is not None:
                COMMAND_QUEUE.put({'action': 'load_preset', 'value': preset})
            return self._json({'ok': True})
        if COMMAND_QUEUE is not None:
            COMMAND_QUEUE.put({'action': a, 'value': v})
        return self._json({'ok': True})


def start_server(command_queue, presets_file, log_file, channels, audios, preferred_port=WEB_PORT, max_port=WEB_PORT_MAX, web_token=''):
    global COMMAND_QUEUE, PRESETS_FILE, LOG_FILE, M3U_CHANNELS, M3U_AUDIOS, WEB_TOKEN, _SERVER, WEB_ACTUAL_PORT
    COMMAND_QUEUE = command_queue
    PRESETS_FILE = presets_file
    LOG_FILE = log_file
    M3U_CHANNELS = list(channels or [])[:10000]
    M3U_AUDIOS = list(audios or [])[:10000]
    WEB_TOKEN = (web_token or '').strip()[:128]
    stop_server()
    try:
        preferred_port, max_port = int(preferred_port), int(max_port)
    except (TypeError, ValueError):
        preferred_port, max_port = WEB_PORT, WEB_PORT_MAX
    preferred_port = max(1024, min(65535, preferred_port))
    max_port = max(preferred_port, min(65535, max_port))
    for port in range(preferred_port, max_port + 1):
        try:
            _SERVER = _Reuse((WEB_BIND, port), Handler)
            WEB_ACTUAL_PORT = port
            update_state(web_port=port)
            t = threading.Thread(target=_SERVER.serve_forever)
            t.daemon = True
            t.start()
            return _SERVER
        except OSError as exc:
            _SERVER = None
            try:
                import xbmc
                xbmc.log('[script.tvaudiosync] Port web {0} indisponible: {1}'.format(port, exc), level=getattr(xbmc, 'LOGINFO', 1))
            except Exception:
                pass
    WEB_ACTUAL_PORT = 0
    return None


def stop_server():
    global _SERVER, WEB_ACTUAL_PORT
    if _SERVER is not None:
        try:
            _SERVER.shutdown()
        except Exception:
            pass
        try:
            _SERVER.server_close()
        except Exception:
            pass
    _SERVER = None
    WEB_ACTUAL_PORT = 0
