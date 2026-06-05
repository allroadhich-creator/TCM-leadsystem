import os, json, datetime, threading, requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials
from elevenlabs.client import ElevenLabs
from elevenlabs import save

app = Flask(__name__)
CORS(app)

WATI_ENDPOINT  = "https://eu.wati.io/1117736"
WATI_TOKEN     = "wati_7454bf20-b280-4d9f-b5af-88162373e6c5.ZO2iZnO_YC0JJ2h22OMGLMkZzDWz1BOKC9xRfkdp3KD_cOgJU21Jcy2HB7MkmictAQTNr0Y0UdiHTTORJRYzXHqVKzqjW_kCWRfawF6vWrryL7k5JdbCxpn9lm4wOw5m"
ELEVENLABS_KEY = "sk_32d8fa6411e4ce968938a4bfd08c323b543663cc309f6cf2"
VOICE_SAMIR    = "WwyYo7OeC5EOwvNF60Va"
VOICE_LAMIA    = "Wg9hZkxHnIru9Ywb9KpC"
SHEET_ID       = "1XfkH4Qa0vnyMJMHKg6Jh2qcL4mV2pafJXhRuGZB9OEo"
CREDS_FILE     = "/root/credentials.json"

TEAM = {
    "hicham":  "212661864599",
    "lamia":   "212668689132",
    "samir":   "31611625043",
    "zakaria": "31684721588",
}

logs = []
leads = []
lead_counter = 1

def log(t, msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    logs.append({"type": t, "time": ts, "msg": msg})
    if len(logs) > 200: logs.pop(0)
    print(f"[{ts}][{t}] {msg}")

def new_lead_id():
    global lead_counter
    lid = f"LEAD-{datetime.date.today().strftime('%Y%m%d')}-{lead_counter:03d}"
    lead_counter += 1
    return lid

def get_sheet():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(SHEET_ID).sheet1

def sheet_append(row):
    try: get_sheet().append_row(row)
    except Exception as e: log("error", f"Sheet append: {e}")

def sheet_update(lead_id, status, tips=""):
    try:
        sh = get_sheet()
        for i, row in enumerate(sh.get_all_values()):
            if row and row[0] == lead_id:
                sh.update_cell(i+1, 10, status)
                if tips: sh.update_cell(i+1, 11, tips)
                break
    except Exception as e: log("error", f"Sheet update: {e}")

def wati_text(phone, msg):
    try:
        r = requests.post(f"{WATI_ENDPOINT}/api/v1/sendSessionMessage/{phone}",
            headers={"Authorization": f"Bearer {WATI_TOKEN}", "Content-Type": "application/json"},
            json={"messageText": msg}, timeout=10)
        log("ok", f"WA text → {phone}: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        log("error", f"WATI text: {e}"); return False

def wati_audio(phone, path):
    try:
        with open(path, "rb") as f:
            r = requests.post(f"{WATI_ENDPOINT}/api/v1/sendMedia/{phone}",
                headers={"Authorization": f"Bearer {WATI_TOKEN}"},
                files={"file": ("voice.mp3", f, "audio/mpeg")},
                data={"caption": "🎙️ Travel Concept Morocco"}, timeout=30)
        log("ok", f"WA audio → {phone}: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        log("error", f"WATI audio: {e}"); return False

def voice_text(lead, tips=""):
    lang = lead.get("language", "fr").lower()
    name = lead.get("name", "")
    dest = lead.get("destination", "Maroc")
    pax  = lead.get("pax", "2")
    dates= lead.get("dates", "")
    d    = f" le {dates}" if dates else ""
    ex   = f" {tips}" if tips else ""
    if "de" in lang:
        return (f"Hallo {name}, hier ist Samir von Travel Concept Morocco. "
                f"Vielen Dank für Ihre Anfrage für eine Reise nach {dest} für {pax} Personen{d}. "
                f"Wir bereiten ein persönliches Angebot für Sie vor.{ex} "
                f"Wann darf ich Sie zurückrufen?")
    elif "nl" in lang:
        return (f"Hallo {name}, met Samir van Travel Concept Morocco. "
                f"Bedankt voor uw aanvraag voor een reis naar {dest} voor {pax} personen{d}. "
                f"We stellen graag een persoonlijk aanbod voor u samen.{ex} "
                f"Wanneer kan ik u terugbellen?")
    else:
        return (f"Bonjour {name}, je suis Lamia de Travel Concept Morocco. "
                f"Nous avons bien reçu votre demande pour un voyage au {dest} pour {pax} personnes{d}. "
                f"Nous préparons une offre personnalisée pour vous.{ex} "
                f"À quel moment puis-je vous rappeler pour discuter de votre programme ?")

def voice_id(lead):
    lang = lead.get("language", "fr").lower()
    return VOICE_SAMIR if ("de" in lang or "nl" in lang) else VOICE_LAMIA

def gen_voice(text, vid, path):
    try:
        audio = ElevenLabs(api_key=ELEVENLABS_KEY).text_to_speech.convert(
            voice_id=vid, text=text, model_id="eleven_multilingual_v2")
        save(audio, path)
        log("ok", f"Voice OK: {path}"); return True
    except Exception as e:
        log("error", f"ElevenLabs: {e}"); return False

@app.route("/api/leads")
def api_leads(): return jsonify(leads)

@app.route("/api/logs")
def api_logs(): return jsonify(logs[-50:])

@app.route("/api/lead/add", methods=["POST"])
def api_add():
    d = request.json
    lid = new_lead_id()
    lead = {"id": lid, "name": d.get("name",""), "phone": d.get("phone","").replace("+","").replace(" ",""),
            "destination": d.get("destination","Maroc"), "language": d.get("language","fr"),
            "pax": d.get("pax","2"), "dates": d.get("dates",""), "budget": d.get("budget",""),
            "notes": d.get("notes",""), "status": "new",
            "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    leads.append(lead)
    log("ok", f"Lead {lid}: {lead['name']} → {lead['destination']}")
    msg = (f"🔔 NEW LEAD {lid}\n👤 {lead['name']}\n📍 {lead['destination']}\n"
           f"👥 {lead['pax']} pax\n📅 {lead['dates']}\n💰 {lead['budget']}\n"
           f"🌐 {lead['language'].upper()}\n📞 +{lead['phone']}")
    for num in TEAM.values(): wati_text(num, msg)
    sheet_append([lid, lead["name"], lead["phone"], lead["destination"],
                  lead["language"], lead["pax"], lead["dates"], lead["budget"],
                  lead["notes"], "new", "", lead["created"]])
    return jsonify({"status": "ok", "id": lid})

@app.route("/api/send", methods=["POST"])
def api_send():
    d = request.json
    lead = next((l for l in leads if l["id"] == d.get("lead_id")), None)
    if not lead: return jsonify({"error": "not found"}), 404
    tips = d.get("tips", "")
    lead["status"] = "processing"
    log("info", f"Processing {lead['id']}...")
    def process():
        path = f"/tmp/{lead['id']}.mp3"
        txt  = voice_text(lead, tips)
        vid  = voice_id(lead)
        log("info", f"Voice text: {txt[:60]}...")
        if gen_voice(txt, vid, path):
            lead["status"] = "sent" if wati_audio(lead["phone"], path) else "audio_error"
        else:
            wati_text(lead["phone"], txt)
            lead["status"] = "sent_text"
        sheet_update(lead["id"], lead["status"], tips)
        log("ok", f"{lead['id']} done → {lead['status']}")
    threading.Thread(target=process).start()
    return jsonify({"status": "processing"})

@app.route("/api/test_notify", methods=["POST"])
def api_test():
    d = request.json
    target = d.get("target", "hicham")
    phone = TEAM.get(target)
    if not phone: return jsonify({"error": "unknown"}), 400
    ok = wati_text(phone, f"✅ TCM System test — {target.upper()} OK! 🚀")
    return jsonify({"status": "ok" if ok else "error", "phone": phone})

@app.route("/")
def index(): return render_template_string(HTML)

HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TCM Lead System</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0f1117;color:#e0e0e0}
header{background:#1a1d27;padding:16px 24px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a2d3a}
header h1{font-size:20px;color:#fff}.badge{background:#25d366;color:#000;font-size:11px;font-weight:bold;padding:3px 8px;border-radius:20px}
.wrap{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:20px;max-width:1400px;margin:0 auto}
.panel{background:#1a1d27;border-radius:12px;padding:20px;border:1px solid #2a2d3a}
.panel h2{font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px}
input,select,textarea{width:100%;background:#0f1117;border:1px solid #2a2d3a;border-radius:8px;color:#e0e0e0;padding:10px 12px;font-size:14px;margin-bottom:10px}
textarea{height:60px;resize:vertical}
.btn{width:100%;background:#25d366;color:#000;border:none;border-radius:8px;padding:12px;font-size:14px;font-weight:bold;cursor:pointer;margin-bottom:8px}
.btn:hover{background:#1ebe57}.btn.blue{background:#0066ff;color:#fff}.btn.blue:hover{background:#0052cc}
.tbtn{background:#1a2d3a;color:#66aaff;border:1px solid #2a3a4a;border-radius:6px;padding:7px 14px;font-size:13px;cursor:pointer;margin:3px}
.tbtn:hover{background:#2a3d4a}
.card{background:#0f1117;border:1px solid #2a2d3a;border-radius:10px;padding:14px;margin-bottom:12px}
.lid{font-size:11px;color:#25d366;font-weight:bold}.lname{font-size:15px;color:#fff;margin:4px 0}
.meta{font-size:12px;color:#666;margin-bottom:3px}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:bold}
.new{background:#1a3a2a;color:#25d366}.processing{background:#1a2a3a;color:#66aaff}
.sent{background:#2a1a3a;color:#aa66ff}.sent_text{background:#2a2a1a;color:#ffaa44}.audio_error{background:#3a1a1a;color:#ff6666}
.term{background:#000;border-radius:8px;padding:14px;height:280px;overflow-y:auto;font-family:monospace;font-size:12px}
.term .ok{color:#25d366}.term .error{color:#ff4444}.term .warn{color:#ffaa00}.term .info{color:#66aaff}
.full{grid-column:1/-1}
</style></head><body>
<header><h1>🌍 TCM Lead System</h1><span class="badge">LIVE</span></header>
<div class="wrap">
  <div class="panel">
    <h2>➕ New Lead</h2>
    <input id="name" placeholder="Full name"/>
    <input id="phone" placeholder="Phone — 31612345678 (no +)"/>
    <input id="destination" placeholder="Destination"/>
    <select id="language">
      <option value="fr">🇫🇷 French → Lamia</option>
      <option value="de">🇩🇪 German → Samir</option>
      <option value="nl">🇳🇱 Dutch → Samir</option>
    </select>
    <input id="pax" placeholder="Persons"/>
    <input id="dates" placeholder="Travel dates"/>
    <input id="budget" placeholder="Budget (€)"/>
    <textarea id="notes" placeholder="Notes..."></textarea>
    <button class="btn" onclick="addLead()">➕ ADD LEAD + NOTIFY TEAM</button>
    <h2 style="margin-top:16px">🧪 Test WhatsApp</h2>
    <div style="display:flex;flex-wrap:wrap">
      <button class="tbtn" onclick="testWA('hicham')">📱 Hicham</button>
      <button class="tbtn" onclick="testWA('lamia')">📱 Lamia</button>
      <button class="tbtn" onclick="testWA('samir')">📱 Samir</button>
      <button class="tbtn" onclick="testWA('zakaria')">📱 Zakaria</button>
    </div>
  </div>
  <div class="panel"><h2>📋 Leads</h2><div id="leads"></div></div>
  <div class="panel full"><h2>📟 Terminal</h2><div class="term" id="term"></div></div>
</div>
<script>
async function addLead(){
  const l={name:v('name'),phone:v('phone'),destination:v('destination'),language:v('language'),pax:v('pax'),dates:v('dates'),budget:v('budget'),notes:v('notes')};
  if(!l.name||!l.phone){alert('Name + phone required');return;}
  const r=await fetch('/api/lead/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(l)});
  const d=await r.json();
  addLog('ok','Lead added: '+d.id);
  ['name','phone','destination','pax','dates','budget','notes'].forEach(id=>document.getElementById(id).value='');
  loadLeads();
}
async function sendLead(id){
  const tips=document.getElementById('t-'+id).value;
  addLog('info','Generating voice for '+id+'...');
  await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lead_id:id,tips:tips})});
  setTimeout(loadLeads,4000);
}
async function testWA(target){
  addLog('info','Testing → '+target);
  const r=await fetch('/api/test_notify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:target})});
  const d=await r.json();
  addLog(d.status==='ok'?'ok':'error','Test '+target+': '+d.status);
}
async function loadLeads(){
  const r=await fetch('/api/leads');const ls=await r.json();
  const c=document.getElementById('leads');
  if(!ls.length){c.innerHTML='<p style="color:#666;font-size:13px">No leads yet</p>';return;}
  c.innerHTML='';[...ls].reverse().forEach(l=>{
    const d=document.createElement('div');d.className='card';
    d.innerHTML=`<div class="lid">${l.id}</div>
    <div class="lname">${l.name} <span class="tag ${l.status}">${l.status}</span></div>
    <div class="meta">📍 ${l.destination} · 👥 ${l.pax} · 🌐 ${l.language.toUpperCase()} · 📞 +${l.phone}</div>
    <div class="meta">📅 ${l.dates} · 💰 ${l.budget}</div>
    <textarea id="t-${l.id}" placeholder="Extra tips for voice..."></textarea>
    <button class="btn blue" onclick="sendLead('${l.id}')">🎙️ SEND VOICE OFFER</button>`;
    c.appendChild(d);
  });
}
async function loadLogs(){
  try{const r=await fetch('/api/logs');const ls=await r.json();
  const t=document.getElementById('term');
  t.innerHTML=ls.map(l=>`<div class="${l.type}">[${l.time}] ${l.msg}</div>`).join('');
  t.scrollTop=t.scrollHeight;}catch(e){}
}
function v(id){return document.getElementById(id).value;}
function addLog(t,m){const term=document.getElementById('term');const d=document.createElement('div');d.className=t;d.textContent='['+new Date().toTimeString().slice(0,8)+'] '+m;term.appendChild(d);term.scrollTop=term.scrollHeight;}
loadLeads();setInterval(loadLogs,2000);setInterval(loadLeads,10000);
</script></body></html>"""

if __name__ == '__main__':
    log("ok", "TCM Lead System v1.0")
    log("ok", "Team: Hicham / Lamia / Samir / Zakaria")
    log("ok", "Voices: FR→Lamia | DE/NL→Samir")
    log("ok", "Dashboard: http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
