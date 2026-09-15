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
START_TIME = time.time()
COMMAND_QUEUE = None
PRESETS_FILE = None
LOG_FILE = None
M3U_CHANNELS = []
M3U_AUDIOS = []
_SERVER = None

STATE = {
    'channel': '', 'audio': '', 'offset': 0, 'volume': 100,
    'status': 'idle', 'ffmpeg_pid': 0, 'error': ''
}


class _Reuse(HTTPServer):
    allow_reuse_address = True


def update_state(**kwargs):
    STATE.update(kwargs)


HTML = u"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TV Audio Sync</title>
<style>
*{box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:#1a1a1a;color:#e0e0e0;margin:0;padding:16px;max-width:900px;margin:auto}
h1{font-size:20px;margin:0 0 12px;color:#4ea1ff}
.tabs{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}
.tab{padding:8px 14px;background:#2a2a2a;border:none;color:#e0e0e0;border-radius:6px;cursor:pointer;font-size:14px}
.tab.on{background:#4ea1ff;color:#fff}
.panel{display:none;background:#242424;padding:16px;border-radius:8px}
.panel.on{display:block}
.status{display:grid;grid-template-columns:auto 1fr;gap:8px;margin-bottom:16px;font-size:14px}
.status .lbl{color:#888}
.big{font-size:36px;font-weight:bold;color:#ffd54f;text-align:center;margin:16px}
.row{display:flex;gap:8px;margin:8px 0;flex-wrap:wrap;align-items:center}
button{padding:10px 18px;font-size:15px;background:#4ea1ff;color:#fff;border:none;border-radius:6px;cursor:pointer}
button:hover{background:#6cb5ff}
button.d{background:#d33}button.d:hover{background:#e44}
button.s{background:#555}button.s:hover{background:#666}
input,select{font-size:15px;padding:8px;background:#333;color:#eee;border:1px solid #444;border-radius:6px;width:100%}
select{height:auto}
pre{background:#111;color:#ddd;padding:12px;border-radius:6px;overflow:auto;max-height:400px;font-size:12px;line-height:1.4;white-space:pre-wrap}
.badge{padding:2px 8px;border-radius:4px;font-size:12px}
.b-r{background:#2e7d32;color:#fff}
.b-i{background:#555;color:#ccc}
.b-e{background:#c62828;color:#fff}
.b-w{background:#f9a825;color:#000}
label{display:block;margin-top:12px;margin-bottom:4px;color:#aaa;font-size:13px}
.item{display:flex;justify-content:space-between;align-items:center;padding:8px;background:#2a2a2a;border-radius:6px;margin-bottom:6px;gap:8px}
.item span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
</style></head><body>
<h1>&#127916; TV Audio Sync</h1>
<div class="tabs">
 <button class="tab on" data-p="live">Live</button>
 <button class="tab" data-p="channels">Cha&icirc;nes</button>
 <button class="tab" data-p="audios">Audios</button>
 <button class="tab" data-p="presets">Presets</button>
 <button class="tab" data-p="logs">Logs</button>
</div>
<div class="panel on" id="p-live">
 <div class="status">
  <span class="lbl">Statut</span><span id="st-status">-</span>
  <span class="lbl">Cha&icirc;ne</span><span id="st-channel">-</span>
  <span class="lbl">Audio</span><span id="st-audio">-</span>
  <span class="lbl">Uptime</span><span id="st-uptime">-</span>
  <span class="lbl">PID ffmpeg</span><span id="st-pid">-</span>
 </div>
 <div class="big" id="st-offset">0 ms</div>
 <div class="row" style="justify-content:center">
  <button onclick="cmd('offset',-500)">-500</button>
  <button onclick="cmd('offset',-100)">-100</button>
  <button onclick="cmd('offset',100)">+100</button>
  <button onclick="cmd('offset',500)">+500</button>
 </div>
 <div class="row">
  <input id="in-offset" type="number" placeholder="Offset manuel (ms)">
  <button onclick="setOff()">Appliquer</button>
  <button class="s" onclick="cmd('reset')">Reset 0</button>
 </div>
 <label>Volume commentaire : <span id="vol-val">100</span>%</label>
 <input id="in-vol" type="range" min="0" max="200" step="5" value="100"
        oninput="document.getElementById('vol-val').textContent=this.value">
 <div class="row"><button onclick="setVol()">Appliquer volume</button></div>
 <div class="row" style="margin-top:20px">
  <button class="d" onclick="cmd('stop')">&#9209; Stop</button>
 </div>
</div>
<div class="panel" id="p-channels">
 <p>Choisis une cha&icirc;ne. La lecture actuelle est relanc&eacute;e avec la nouvelle.</p>
 <label>Filtre :</label>
 <input id="ch-filter" placeholder="Rechercher..." oninput="renderCh()">
 <label>Cha&icirc;ne :</label>
 <select id="ch-sel" size="10"></select>
 <div class="row"><button onclick="switchCh()">&#9654; Basculer sur cette cha&icirc;ne</button></div>
</div>
<div class="panel" id="p-audios">
 <p>Choisis le commentaire audio &agrave; superposer.</p>
 <label>Filtre :</label>
 <input id="au-filter" placeholder="Rechercher..." oninput="renderAu()">
 <label>Audio :</label>
 <select id="au-sel" size="10"></select>
 <div class="row"><button onclick="switchAu()">&#127908; Basculer sur cet audio</button></div>
</div>
<div class="panel" id="p-presets">
 <p>Enregistre la combinaison actuelle (cha&icirc;ne + audio + offset + volume).</p>
 <label>Nom du preset :</label>
 <div class="row">
  <input id="pr-name" placeholder="Ex: TF1 FR">
  <button onclick="savePreset()">&#128190; Enregistrer</button>
 </div>
 <div id="pr-list" style="margin-top:16px"></div>
</div>
<div class="panel" id="p-logs">
 <div class="row">
  <button onclick="refreshLog()">&#128260; Rafra&icirc;chir</button>
  <span style="color:#888">50 derni&egrave;res lignes</span>
 </div>
 <pre id="log-box">Chargement...</pre>
</div>
<script>
var tabs=document.querySelectorAll('.tab');
tabs.forEach(function(t){t.onclick=function(){
 tabs.forEach(function(x){x.classList.remove('on');});
 document.querySelectorAll('.panel').forEach(function(x){x.classList.remove('on');});
 t.classList.add('on');
 document.getElementById('p-'+t.dataset.p).classList.add('on');
 if(t.dataset.p==='logs')refreshLog();
 if(t.dataset.p==='channels')refreshCh();
 if(t.dataset.p==='audios')refreshAu();
 if(t.dataset.p==='presets')refreshPr();
};});
var state={},channels=[],audios=[],presets=[];
function api(u,o){return fetch(u,o).then(function(r){return r.json();});}
function cmd(a,v){api('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({action:a,value:v||0})}).then(refresh);}
function setOff(){var v=parseInt(document.getElementById('in-offset').value)||0;cmd('set_offset',v);}
function setVol(){var v=parseInt(document.getElementById('in-vol').value)||100;cmd('set_volume',v);}
function fmtUp(s){if(s<60)return s+'s';if(s<3600)return Math.floor(s/60)+'m '+Math.floor(s%60)+'s';
 return Math.floor(s/3600)+'h '+Math.floor((s%3600)/60)+'m';}
function refresh(){
 api('/api/state').then(function(s){
  state=s;
  var cls=s.status==='running'?'b-r':(s.status==='error'?'b-e':'b-i');
  document.getElementById('st-status').innerHTML='<span class="badge '+cls+'">'+s.status+'</span>';
  document.getElementById('st-channel').textContent=s.channel||'-';
  document.getElementById('st-audio').textContent=s.audio||'-';
  document.getElementById('st-uptime').textContent=fmtUp(s.uptime);
  document.getElementById('st-pid').textContent=s.ffmpeg_pid||'-';
  document.getElementById('st-offset').textContent=(s.offset>0?'+':'')+s.offset+' ms';
  document.getElementById('in-vol').value=s.volume;
  document.getElementById('vol-val').textContent=s.volume;
 });
}
function refreshCh(){api('/api/channels').then(function(d){channels=d;renderCh();});}
function renderCh(){
 var f=(document.getElementById('ch-filter').value||'').toLowerCase();
 var sel=document.getElementById('ch-sel');sel.innerHTML='';
 channels.list.forEach(function(n){
  if(f&&n.toLowerCase().indexOf(f)<0)return;
  var o=document.createElement('option');
  o.value=n;o.textContent=(n===channels.current?'\u25B6 ':'  ')+n;
  sel.appendChild(o);
 });
}
function refreshAu(){api('/api/audios').then(function(d){audios=d;renderAu();});}
function renderAu(){
 var f=(document.getElementById('au-filter').value||'').toLowerCase();
 var sel=document.getElementById('au-sel');sel.innerHTML='';
 audios.list.forEach(function(n){
  if(f&&n.toLowerCase().indexOf(f)<0)return;
  var o=document.createElement('option');
  o.value=n;o.textContent=(n===audios.current?'\u25B6 ':'  ')+n;
  sel.appendChild(o);
 });
}
function switchCh(){var v=document.getElementById('ch-sel').value;if(v)cmd('switch_channel',v);}
function switchAu(){var v=document.getElementById('au-sel').value;if(v)cmd('switch_audio',v);}
function refreshPr(){api('/api/presets').then(function(d){presets=d.presets||[];renderPr();});}
function renderPr(){
 var box=document.getElementById('pr-list');box.innerHTML='';
 if(!presets.length){box.innerHTML='<p style="color:#888">Aucun preset.</p>';return;}
 presets.forEach(function(p,i){
  var d=document.createElement('div');d.className='item';
  d.innerHTML='<span><b>'+p.name+'</b><br><small style="color:#888">'+p.channel+' &rarr; '+p.audio+' ('+p.offset+'ms, '+p.volume+'%)</small></span>';
  var b1=document.createElement('button');b1.textContent='\u25B6';b1.onclick=function(){cmd('load_preset',i);};
  var b2=document.createElement('button');b2.textContent='\uD83D\uDDD1';b2.className='d';b2.onclick=function(){cmd('delete_preset',i);setTimeout(refreshPr,400);};
  d.appendChild(b1);d.appendChild(b2);box.appendChild(d);
 });
}
function savePreset(){
 var n=document.getElementById('pr-name').value;if(!n)return;
 cmd('save_preset',n);setTimeout(refreshPr,500);
}
function refreshLog(){
 api('/api/log?lines=50').then(function(d){
  document.getElementById('log-box').textContent=(d.lines||[]).join('\\n')||'(vide)';
 });
}
setInterval(function(){if(document.getElementById('p-live').classList.contains('on'))refresh();},2000);
refresh();
</script></body></html>"""


def _presets_load():
    if not PRESETS_FILE or not os.path.exists(PRESETS_FILE):
        return []
    try:
        f = open(PRESETS_FILE, 'r')
        try:
            return json.load(f)
        finally:
            f.close()
    except Exception:
        return []


def _presets_save(p):
    if not PRESETS_FILE:
        return
    try:
        f = open(PRESETS_FILE, 'w')
        try:
            json.dump(p, f)
        finally:
            f.close()
    except Exception:
        pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj):
        try:
            data = json.dumps(obj).encode('utf-8')
        except Exception:
            data = b'{}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _html(self, txt):
        data = txt.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path.split('?')[0]
        if p in ('/', '/index.html'):
            return self._html(HTML)
        if p == '/api/state':
            s = dict(STATE)
            s['uptime'] = int(time.time() - START_TIME)
            return self._json(s)
        if p == '/api/channels':
            return self._json({'current': STATE.get('channel', ''), 'list': M3U_CHANNELS})
        if p == '/api/audios':
            return self._json({'current': STATE.get('audio', ''), 'list': M3U_AUDIOS})
        if p == '/api/presets':
            return self._json({'presets': _presets_load()})
        if p == '/api/log':
            n = 50
            if '?' in self.path:
                qs = self.path.split('?', 1)[1]
                for kv in qs.split('&'):
                    if kv.startswith('lines='):
                        try:
                            n = int(kv.split('=')[1])
                        except Exception:
                            pass
            lines = []
            if LOG_FILE and os.path.exists(LOG_FILE):
                try:
                    f = open(LOG_FILE, 'r')
                    try:
                        lines = f.readlines()[-n:]
                    finally:
                        f.close()
                    lines = [l.rstrip() for l in lines]
                except Exception:
                    lines = []
            return self._json({'lines': lines})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        ln = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(ln).decode('utf-8') if ln else '{}'
        try:
            data = json.loads(body)
        except Exception:
            data = {}
        if self.path != '/api/cmd':
            self.send_response(404)
            self.end_headers()
            return
        a = data.get('action')
        v = data.get('value')
        if a == 'save_preset':
            ps = _presets_load()
            ps.append({
                'name': v,
                'channel': STATE.get('channel', ''),
                'audio': STATE.get('audio', ''),
                'offset': STATE.get('offset', 0),
                'volume': STATE.get('volume', 100),
            })
            _presets_save(ps)
            return self._json({'ok': True})
        if a == 'delete_preset':
            ps = _presets_load()
            try:
                del ps[int(v)]
            except Exception:
                pass
            _presets_save(ps)
            return self._json({'ok': True})
        if a == 'load_preset':
            ps = _presets_load()
            try:
                preset = ps[int(v)]
            except Exception:
                return self._json({'ok': False})
            if COMMAND_QUEUE is not None:
                COMMAND_QUEUE.put({'action': 'load_preset', 'value': preset})
            return self._json({'ok': True})
        if COMMAND_QUEUE is not None:
            COMMAND_QUEUE.put({'action': a, 'value': v})
        return self._json({'ok': True})


def start_server(command_queue, presets_file, log_file, channels, audios, port=WEB_PORT):
    global COMMAND_QUEUE, PRESETS_FILE, LOG_FILE, M3U_CHANNELS, M3U_AUDIOS, _SERVER
    COMMAND_QUEUE = command_queue
    PRESETS_FILE = presets_file
    LOG_FILE = log_file
    M3U_CHANNELS = channels
    M3U_AUDIOS = audios
    stop_server()
    try:
        _SERVER = _Reuse(('0.0.0.0', port), Handler)
        t = threading.Thread(target=_SERVER.serve_forever)
        t.daemon = True
        t.start()
        return _SERVER
    except Exception:
        _SERVER = None
        return None


def stop_server():
    global _SERVER
    if _SERVER is not None:
        try:
            _SERVER.shutdown()
            _SERVER.server_close()
        except Exception:
            pass
        _SERVER = None
