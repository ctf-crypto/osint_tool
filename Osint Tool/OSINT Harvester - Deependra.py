#!/usr/bin/env python3
# OSINT Harvester — compacted + singleton OSINT Image window + singleton Developer Info
import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
import socket, re, subprocess, threading, random, time, json, webbrowser
from urllib.parse import quote_plus
from datetime import datetime, timezone
import requests
from requests.exceptions import ConnectionError, RequestException
from PIL import Image, ImageTk, ExifTags

# Optional whois
try:
    import whois as pywhois
    HAVE_PYWHOIS = True
except Exception:
    pywhois = None
    HAVE_PYWHOIS = False

DEV_PHOTO_PATH = r"Dev Photo\Profile(Social Media).jpg"
EMAIL_RE = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
ONION_RE = re.compile(r'[a-z2-7]{16,56}\.onion', re.IGNORECASE)
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
]
DEFAULT_HEADERS = {"User-Agent": UA_POOL[0]}

# ---------- network / helpers ----------
def safe_get(url, method="get", timeout=15, headers=None, data=None, proxies=None, stealth=False):
    if stealth:
        headers = dict(headers or DEFAULT_HEADERS); headers["User-Agent"] = random.choice(UA_POOL); time.sleep(random.uniform(0.6,1.4))
    else:
        headers = headers or DEFAULT_HEADERS
    try:
        if method.lower()=="get":
            r = requests.get(url, headers=headers, timeout=timeout, proxies=proxies, allow_redirects=True)
        else:
            r = requests.post(url, headers=headers, data=data, timeout=timeout, proxies=proxies)
        return True, r.text, r.status_code
    except ConnectionError as ce:
        try:
            if method.lower()=="get":
                r = requests.get(url, headers=headers, timeout=timeout, proxies={"http": None, "https": None}, allow_redirects=True)
            else:
                r = requests.post(url, headers=headers, data=data, timeout=timeout, proxies={"http": None, "https": None})
            return True, r.text, r.status_code
        except Exception as e2:
            return False, f"Connection error (proxy): {ce}; direct retry failed: {e2}", None
    except RequestException as rexc:
        return False, str(rexc), None
    except Exception as exc:
        return False, str(exc), None

def _resolve_ip(d): 
    try: return socket.gethostbyname(d)
    except: return ""

def _iso_date(d):
    if d is None: return ""
    if isinstance(d, (list,tuple)):
        try:
            dt=[x for x in d if isinstance(x, datetime)]
            if dt: return min(dt).astimezone(timezone.utc).isoformat()
        except: pass
        return str(d[0])
    if isinstance(d, datetime): return d.astimezone(timezone.utc).isoformat()
    return str(d)

def _valid_email(e):
    if not e or len(e)<6: return False
    if re.fullmatch(r'\d+', e.split('@',1)[0]): return False
    return True

# ---------- whois / parsing ----------
def parse_whois_with_library(domain):
    info = pywhois.whois(domain)
    registrar = getattr(info,"registrar","") or ""
    created = _iso_date(getattr(info,"creation_date",None))
    emails = getattr(info,"emails",None)
    if isinstance(emails,str): emails=[emails]
    emails=[x for x in (emails or []) if _valid_email(x)]
    return {"domain":domain,"ip":_resolve_ip(domain),"registrar":registrar,"creation_date":created,"emails":sorted(emails)}

def parse_whois_raw(domain, raw):
    reg=""; creation=""; emails=set()
    m=re.search(r'Registrar:\s*(.+)', raw, flags=re.IGNORECASE)
    if m: reg=m.group(1).strip()
    m=re.search(r'Creation Date:\s*(.+)', raw, flags=re.IGNORECASE) or re.search(r'Created On:\s*(.+)', raw, flags=re.IGNORECASE)
    if m: creation=m.group(1).strip()
    if not creation:
        m=re.search(r'(\d{4}-\d{2}-\d{2})', raw)
        if m: creation=m.group(1)
    for e in EMAIL_RE.findall(raw):
        if _valid_email(e): emails.add(e)
    return {"domain":domain,"ip":_resolve_ip(domain),"registrar":reg,"creation_date":creation,"emails":sorted(emails)}

def get_domain_info(domain):
    domain=domain.strip()
    if HAVE_PYWHOIS:
        try: return parse_whois_with_library(domain)
        except: pass
    try:
        proc=subprocess.run(["whois",domain], capture_output=True, text=True, timeout=12)
        raw=proc.stdout or proc.stderr or ""
        if raw.strip(): return parse_whois_raw(domain, raw)
    except: pass
    return {"domain":domain,"ip":_resolve_ip(domain),"registrar":"","creation_date":"","emails":[]}

# ---------- search engines / probes ----------
def _build_proxies(tor_enabled, tor_hostport):
    if not tor_enabled or not tor_hostport: return None
    return {"http": f"socks5h://{tor_hostport}", "https": f"socks5h://{tor_hostport}"}

def search_duckduckgo(domain, proxies=None, stealth=False):
    q=f"site:{domain} email OR contact OR mail"; url="https://duckduckgo.com/html/"; ok,data,_=safe_get(url, method="post", data={"q":q}, headers=None, proxies=proxies, stealth=stealth); return data if ok else ""
def search_bing(domain, proxies=None, stealth=False):
    q=quote_plus(f"site:{domain} email OR contact OR mail"); url=f"https://www.bing.com/search?q={q}"; ok,data,_=safe_get(url, method="get", headers=None, proxies=proxies, stealth=stealth); return data if ok else ""
def search_ahmia(domain, proxies=None, stealth=False):
    q=quote_plus(domain); url=f"https://ahmia.fi/search/?q={q}"; ok,data,_=safe_get(url, method="get", headers=None, proxies=proxies, stealth=stealth); return data if ok else ""
def search_github(domain, proxies=None, stealth=False):
    q=quote_plus(domain); url=f"https://github.com/search?q={q}"; ok,data,_=safe_get(url, method="get", headers=None, proxies=proxies, stealth=stealth); return data if ok else ""

SEARCH_ENGINES={"DuckDuckGo":search_duckduckgo,"Bing":search_bing,"Ahmia":search_ahmia,"GitHub":search_github}

def aggregate_search(domain, tor_enabled=False, tor_hostport="127.0.0.1:9050", stealth=False, timeout_per_thread=18):
    lock=threading.Lock(); emails=set(); onions=set(); engine_status={}
    proxies=_build_proxies(tor_enabled, tor_hostport)
    def w(name,fn):
        try:
            text=fn(domain, proxies=proxies, stealth=stealth)
            if isinstance(text,str) and text:
                for e in EMAIL_RE.findall(text):
                    if _valid_email(e): emails.add(e.lower())
                for o in ONION_RE.findall(text): onions.add(o.lower())
                engine_status[name]="ok"
            else: engine_status[name]="no-data"
        except: engine_status[name]="error"
    threads=[threading.Thread(target=w,args=(n,f),daemon=True) for n,f in SEARCH_ENGINES.items()]
    for t in threads: t.start()
    for t in threads: t.join(timeout_per_thread)
    return sorted(emails), sorted(onions), engine_status

PLATFORM_URLS = {
 "GitHub":"https://github.com/{u}","Twitter":"https://twitter.com/{u}","Instagram":"https://www.instagram.com/{u}/",
 "Reddit":"https://www.reddit.com/user/{u}","LinkedIn":"https://www.linkedin.com/in/{u}","Facebook":"https://www.facebook.com/{u}",
 "StackOverflow":"https://stackoverflow.com/users/{u}","Medium":"https://medium.com/@{u}","YouTube":"https://www.youtube.com/{u}",
 "Telegram":"https://t.me/{u}","Mastodon (mastodon.social)":"https://mastodon.social/@{u}","Keybase":"https://keybase.io/{u}",
 "Pinterest":"https://www.pinterest.com/{u}","Tumblr":"https://{u}.tumblr.com","Wordpress":"https://{u}.wordpress.com",
 "SoundCloud":"https://soundcloud.com/{u}","Twitch":"https://www.twitch.tv/{u}","Snapchat":"https://www.snapchat.com/add/{u}",
 "Telegram (web)":"https://web.telegram.org/#/im?p=@{u}","Pastebin":"https://pastebin.com/u/{u}","Bitbucket":"https://bitbucket.org/{u}"
}

def probe_profiles(username, tor_enabled=False, tor_hostport="127.0.0.1:9050", stealth=False, timeout_per_site=10):
    proxies=_build_proxies(tor_enabled, tor_hostport); results=[]; lock=threading.Lock()
    def w(platform, tmpl):
        url=tmpl.format(u=username)
        ok,data,status=safe_get(url, method="get", headers=None, proxies=proxies, stealth=stealth)
        exists=False; title=""
        if ok and status and 200<=status<400:
            exists=True
            m=re.search(r'<title[^>]*>(.*?)</title>', (data or ""), flags=re.IGNORECASE|re.DOTALL)
            if m: title=re.sub(r'\s+',' ',m.group(1)).strip()[:120]
        if platform=="Reddit" and ok and data and "page not found" in data.lower(): exists=False
        with lock: results.append({"platform":platform,"url":url,"exists":exists,"status":status,"title":title})
    threads=[]
    for p,tmpl in PLATFORM_URLS.items():
        t=threading.Thread(target=w,args=(p,tmpl),daemon=True); threads.append(t); t.start(); time.sleep(0.03)
    for t in threads: t.join(timeout=timeout_per_site+2)
    results.sort(key=lambda x:(not x["exists"], x["platform"])); return results

# ---------- orchestration ----------
def run_domain_scan(domain, tor_enabled=False, tor_hostport="", stealth=False):
    whois_info=get_domain_info(domain)
    emails,onions,engine_status=aggregate_search(domain, tor_enabled=tor_enabled, tor_hostport=tor_hostport, stealth=stealth)
    final=[]; seen=set()
    for e in whois_info.get("emails",[]) or []:
        le=e.lower()
        if le not in seen and _valid_email(le): final.append(le); seen.add(le)
    for e in emails:
        if e not in seen and _valid_email(e): final.append(e); seen.add(e)
    lines=[f"Domain: {whois_info.get('domain','')}"]
    if whois_info.get('ip'): lines.append(f"IP: {whois_info.get('ip')}")
    if whois_info.get('registrar'): lines.append(f"Registrar: {whois_info.get('registrar')}")
    if whois_info.get('creation_date'): lines.append(f"Creation: {whois_info.get('creation_date')}")
    if final:
        lines.append(""); lines.append("Emails:"); lines += final
    if onions:
        lines.append(""); lines.append(".onion addresses:"); lines += sorted(onions)
    lines.append(""); lines.append("Sources:")
    for k,v in sorted(engine_status.items()): lines.append(f"{k}: {v}")
    return "\n".join(lines).strip()

def run_username_scan(username, tor_enabled=False, tor_hostport="", stealth=False):
    results=probe_profiles(username, tor_enabled=tor_enabled, tor_hostport=tor_hostport, stealth=stealth)
    lines=[f"Username: {username}","","Profiles found:"]; found=False
    for r in results:
        if r["exists"]:
            found=True
            title=f" - {r['title']}" if r.get("title") else ""
            lines.append(f"{r['platform']}: {r['url']} (status={r['status']}){title}")
    if not found: lines.append("No public profiles detected on the checked platforms.")
    lines.append(""); lines.append("Checked platforms summary:")
    for r in results: lines.append(f"{r['platform']}: {'FOUND' if r['exists'] else 'not found'} (status={r['status']})")
    return "\n".join(lines).strip()

# ---------- OSINT Image helpers (local to window) ----------
def open_in_browser(url): 
    try: webbrowser.open_new_tab(url)
    except: pass

def wayback_snapshots_list(url_or_domain, timeout=12):
    try:
        u=url_or_domain.strip()
        if not u: return False,"No URL/domain provided."
        if not (u.startswith("http://") or u.startswith("https://")): u="http://"+u
        api=f"https://web.archive.org/cdx/search/cdx?url={quote_plus(u)}&output=json&limit=50&filter=statuscode:200&from=1990&collapse=digest"
        ok,text,_=safe_get(api, method="get", timeout=timeout)
        if not ok: return False, f"Wayback CDX error: {text}"
        data=json.loads(text)
        if len(data)<=1: return False, "No snapshots found (CDX)."
        snaps=[]
        for row in data[1:]:
            try: ts=row[1]; orig=row[2]; snaps.append((ts, f"https://web.archive.org/web/{ts}/{orig}"))
            except: continue
        return (True, snaps) if snaps else (False,"No snapshots parsed.")
    except Exception as e: return False, str(e)

def exif_from_image_file(path):
    try:
        img=Image.open(path); exif=img._getexif()
        if not exif: return False, ["No EXIF metadata found."]
        res=[]
        for tid,val in exif.items():
            name=ExifTags.TAGS.get(tid, tid)
            if name=="GPSInfo":
                gps={}; 
                for t,v in val.items(): gps[ExifTags.GPSTAGS.get(t,t)]=v
                latlon=_gps_to_decimal(gps)
                res.append(f"GPS (decimal): {latlon[0]:.6f}, {latlon[1]:.6f}" if latlon else f"GPS Info: {gps}")
            else:
                res.append(f"{name}: {val}")
        return True, res
    except Exception as e: return False, [f"EXIF extraction error: {e}"]

def _gps_to_decimal(gps):
    try:
        if not gps: return None
        def rf(r): 
            try: return float(r[0])/float(r[1])
            except: return float(r)
        if "GPSLatitude" in gps and "GPSLongitude" in gps and "GPSLatitudeRef" in gps and "GPSLongitudeRef" in gps:
            lat_t=gps["GPSLatitude"]; lon_t=gps["GPSLongitude"]
            lat=rf(lat_t[0])+rf(lat_t[1])/60.0+rf(lat_t[2])/3600.0
            lon=rf(lon_t[0])+rf(lon_t[1])/60.0+rf(lon_t[2])/3600.0
            if gps.get("GPSLatitudeRef","N")!="N": lat=-lat
            if gps.get("GPSLongitudeRef","E")!="E": lon=-lon
            return (lat,lon)
    except: pass
    return None

def reverse_image_search_urls(image_url):
    return {
        "Google": f"https://www.google.com/searchbyimage?&image_url={quote_plus(image_url)}",
        "TinEye": f"https://tineye.com/search?url={quote_plus(image_url)}",
        "Bing": f"https://www.bing.com/images/search?q=imgurl:{quote_plus(image_url)}&view=detailv2"
    }

# ---------- GUI ----------
root=tk.Tk(); root.title("OSINT Harvester — Domain & Username mode"); root.geometry("1120x760")
tk.Label(root, text="Enter Domain or Username:",bg="Blue", fg="White", font=("Segoe UI",14,"bold")).pack(pady=6)
entry=tk.Entry(root, width=90); entry.pack(pady=4)
control_frame=tk.Frame(root); control_frame.pack(pady=4, fill="x", padx=8)

run_btn = tk.Button(control_frame, text="Run Scan", command=lambda:start_scan_wrapper(), bg="#3A7FF6", fg="white", width=10); run_btn.grid(row=0,column=0,padx=6,pady=4)
reset_btn = tk.Button(control_frame, text="Reset", command=lambda:reset_output(), bg="red", fg="white", width=10); reset_btn.grid(row=0,column=1,padx=6)
toolinfo_btn = tk.Button(control_frame, text="Tool Info", command=lambda:show_tool_info(), bg="#333333", fg="#00ff00", width=10); toolinfo_btn.grid(row=0,column=2,padx=6)
osint_img_btn = tk.Button(control_frame, text="OSINT Image", command=lambda:show_best_tools(), bg="#0b6623", fg="#ffffff", width=12); osint_img_btn.grid(row=0,column=3,padx=6)

mode_frame=tk.Frame(control_frame); mode_frame.grid(row=0,column=4,padx=20)
mode_var=tk.StringVar(value="domain"); tk.Radiobutton(mode_frame, text="Domain", variable=mode_var, value="domain").pack(side="left", padx=4); tk.Radiobutton(mode_frame, text="Username", variable=mode_var, value="username").pack(side="left", padx=4)

settings_frame=tk.Frame(control_frame); settings_frame.grid(row=0, column=5, sticky="e", padx=6)
var_tor=tk.BooleanVar(value=False); tor_chk=tk.Checkbutton(settings_frame, text="Use local Tor proxy", variable=var_tor); tor_chk.pack(side="left", padx=6)
tk.Label(settings_frame, text="Host:Port").pack(side="left"); tor_entry=tk.Entry(settings_frame, width=14); tor_entry.insert(0,"127.0.0.1:9050"); tor_entry.pack(side="left", padx=6)
var_stealth=tk.BooleanVar(value=False); stealth_chk=tk.Checkbutton(settings_frame, text="Stealth Mode (UA + pacing)", variable=var_stealth); stealth_chk.pack(side="left", padx=6)

output_frame = tk.Frame(root, bg="black", bd=2, relief="sunken"); output_frame.pack(padx=10,pady=10,fill="both",expand=True)
output = scrolledtext.ScrolledText(output_frame, width=115, height=36, bg="black", fg="#00ff00", insertbackground="#00ff00", font=("Consolas",10), wrap="word", borderwidth=0); output.pack(fill="both",expand=True)

welcome_text="Welcome to OSINT Harvester Developed by Deependra"
welcome_label=tk.Label(output_frame, text=welcome_text, bg="black", fg="#00ff00", font=("Segoe UI",14,"bold"), justify="center"); welcome_label.place(relx=0.5,rely=0.5,anchor="center")
scan_anim_label=tk.Label(output_frame, text="", bg="black", fg="#00ff00", font=("Segoe UI",10)); scan_anim_label.place(x=8,y=8)

# ---------- Developer Info (singleton) ----------
dev_window = None
def show_developer_info():
    global dev_window
    if dev_window and tk.Toplevel.winfo_exists(dev_window):
        dev_window.lift(); dev_window.focus_force(); return
    dev_window = tk.Toplevel(root); dev_window.title("Developer Info"); dev_window.geometry("420x520")
    tk.Label(dev_window, text="Developer Info", bg="#FFD400", fg="black", font=("Segoe UI",14,"bold")).pack(fill="x")
    try:
        img=Image.open(DEV_PHOTO_PATH); img=img.resize((260,260), Image.LANCZOS); photo=ImageTk.PhotoImage(img); lbl=tk.Label(dev_window,image=photo); lbl.image=photo; lbl.pack(pady=(12,6))
    except: tk.Label(dev_window, text="(Photo not available)", fg="red").pack(pady=12)
    tk.Label(dev_window, text="Developer Name: Deependra\nPursued: MSc Digital Forensic and Information Security\nInstitute: NFSU, Bhopal\n", justify="left", anchor="w", font=("Segoe UI",11)).pack(padx=12,pady=6)
    tk.Button(dev_window, text="Close", command=lambda: (dev_window.destroy(), globals().__setitem__('dev_window', None))).pack(pady=12)
    dev_window.protocol("WM_DELETE_WINDOW", lambda: (dev_window.destroy(), globals().__setitem__('dev_window', None)))

dev_btn_bottom=tk.Button(root, text="Developer Info", command=show_developer_info, bg="#FFD400", fg="black"); dev_btn_bottom.pack(pady=(6,12))

TOOL_INFO_TEXT = ("Mode: Domain = WHOIS + multi-engine email/onion search. Username = probe common social platforms for profile existence.\n\nStealth Mode randomizes UA and adds small pacing. Tor option will route through a local SOCKS proxy if enabled.")
def show_tool_info():
    t=tk.Toplevel(root); t.title("Tool Info"); t.geometry("560x220")
    tk.Label(t, text="Tool Info", font=("Segoe UI",13,"bold")).pack(anchor="w", padx=12,pady=(8,4))
    txt=tk.Text(t, wrap="word", height=6, bg="white", fg="black"); txt.pack(fill="both",expand=True,padx=12,pady=(0,12)); txt.insert("1.0", TOOL_INFO_TEXT); txt.config(state="disabled")
    tk.Button(t, text="Close", command=t.destroy).pack(pady=(0,8))

copyright_label=tk.Label(root, text="© Copyright OSINT Harvester - Deependra", fg="gray"); copyright_label.pack(pady=(0,6))

_scanning=False; _scan_anim_job=None; _welcome_blink_job=None
def _animate_scan_label(d=[0]):
    if not _scanning: scan_anim_label.config(text=""); return
    d[0]=(d[0]+1)%4; scan_anim_label.config(text="Scanning"+"."*d[0]); global _scan_anim_job; _scan_anim_job=root.after(500,_animate_scan_label)
def _blink_welcome(s=[0]):
    if _scanning: welcome_label.place_forget(); return
    s[0]=1-s[0]; welcome_label.config(fg="#00ff00" if s[0] else "#66ff66"); global _welcome_blink_job; _welcome_blink_job=root.after(800,_blink_welcome)

def reset_output():
    global _scanning
    if _scanning: messagebox.showinfo("Reset","Scan is running — wait until it finishes or stop it first."); return
    output.config(state="normal"); output.delete(1.0,tk.END)
    welcome_label.config(font=("Segoe UI",14,"bold")); welcome_label.place(relx=0.5,rely=0.5,anchor="center")
    scan_anim_label.config(text=""); _blink_welcome(); output.config(state="normal")

def start_scan_wrapper():
    target=entry.get().strip()
    if not target: messagebox.showwarning("Input Error","Enter a domain or username."); return
    mode=mode_var.get(); global _scanning; _scanning=True; welcome_label.place_forget(); _animate_scan_label()
    run_btn.config(state="disabled"); reset_btn.config(state="disabled"); toolinfo_btn.config(state="disabled"); osint_img_btn.config(state="disabled")
    tor_enabled=var_tor.get(); tor_hostport=tor_entry.get().strip(); stealth=var_stealth.get()
    def worker():
        try:
            if mode=="domain":
                domain=re.sub(r"^https?://","",target).split("/")[0]; output_text=run_domain_scan(domain, tor_enabled=tor_enabled, tor_hostport=tor_hostport, stealth=stealth)
            else:
                username=target; output_text=run_username_scan(username, tor_enabled=tor_enabled, tor_hostport=tor_hostport, stealth=stealth)
            def write_result():
                output.config(state="normal"); output.delete(1.0,tk.END); output.insert(tk.END, output_text+"\n"); output.see(tk.END); output.config(state="disabled")
            root.after(0, write_result)
        finally:
            def finish():
                global _scanning
                _scanning=False
                if _scan_anim_job: root.after_cancel(_scan_anim_job)
                scan_anim_label.config(text=""); run_btn.config(state="normal"); reset_btn.config(state="normal"); toolinfo_btn.config(state="normal"); osint_img_btn.config(state="normal")
            root.after(0, finish)
    threading.Thread(target=worker, daemon=True).start()

# ---------- singleton OSINT Image window ----------
osint_window = None
def show_best_tools():
    global osint_window
    if osint_window and tk.Toplevel.winfo_exists(osint_window):
        osint_window.lift(); osint_window.focus_force(); return
    osint_window = tk.Toplevel(root); bt=osint_window
    bt.title("OSINT Image — Wayback & EXIF"); bt.geometry("920x520")
    header_frame = tk.Frame(bt); header_frame.pack(fill="x", padx=12, pady=(8,4))
    tk.Label(header_frame, text="OSINT Image — Wayback snapshots & Image EXIF", font=("Segoe UI",14,"bold")).pack(side="left")
    tk.Label(header_frame, text="Wayback snapshots + EXIF & reverse-image helpers", fg="gray").pack(side="left", padx=12)
    inner=tk.Frame(bt); inner.pack(fill="both", expand=True, padx=12,pady=8)
    left=tk.Frame(inner); left.pack(side="left", fill="y", padx=(0,8))
    tk.Label(left, text="Wayback snapshots (domain / URL):", font=("Segoe UI",11,"bold")).pack(anchor="w")
    way_entry=tk.Entry(left, width=48); way_entry.pack(anchor="w", pady=(6,4))
    snaps_listbox=tk.Listbox(left, width=68, height=22, activestyle="dotbox", bg="black", fg="#00ff00", selectbackground="#0b6623"); snaps_listbox.pack(fill="both", expand=True, pady=(4,4))
    right=tk.Frame(inner); right.pack(side="left", fill="both", expand=True, padx=(8,0))
    tk.Label(right, text="Image EXIF / Reverse image", font=("Segoe UI",11,"bold")).pack(anchor="w")
    tk.Button(right, text="Choose local image (extract EXIF)", command=lambda: choose_image_and_extract_local(bt, result_text), bg="#333333", fg="#00ff00").pack(anchor="w", pady=(6,4))
    tk.Label(right, text="Or paste an image URL for reverse-image search:").pack(anchor="w", pady=(8,2))
    imgurl_entry=tk.Entry(right, width=48); imgurl_entry.pack(anchor="w", pady=(0,4))
    def do_rev_from_url_local():
        url=imgurl_entry.get().strip()
        if not url: messagebox.showwarning("Input","Enter an image URL."); return
        urls=reverse_image_search_urls(url)
        result_text.config(state="normal"); result_text.insert(tk.END, f"[Reverse image] Opening searches for: {url}\n"); result_text.see(tk.END); result_text.config(state="disabled")
        for _,u in urls.items(): open_in_browser(u)
    tk.Button(right, text="Reverse image (open searches)", command=do_rev_from_url_local, bg="#333333", fg="#00ff00").pack(anchor="w", pady=(4,6))
    tk.Label(right, text="OSINT Image results:", font=("Segoe UI",10,"bold")).pack(anchor="w", pady=(8,2))
    result_text=tk.Text(right, wrap="word", height=18, bg="#111111", fg="#00ff00", insertbackground="#00ff00"); result_text.pack(fill="both", expand=True)
    def on_snap_double(event):
        sel=snaps_listbox.curselection()
        if not sel: return
        url=snaps_listbox.get(sel[0]).split(" ",1)[1]; open_in_browser(url)
    snaps_listbox.bind("<Double-Button-1>", on_snap_double)
    way_btn=tk.Button(left, text="Fetch snapshots", command=lambda: do_wayback_full_local(way_entry.get().strip(), snaps_listbox, result_text), bg="#333333", fg="#00ff00"); way_btn.pack(anchor="w", pady=(6,4))
    def reset_osint_image_window():
        snaps_listbox.delete(0,tk.END); result_text.config(state="normal"); result_text.delete("1.0",tk.END)
        result_text.insert(tk.END, "OSINT Image — ready. Use the controls above to fetch Wayback snapshots or extract EXIF.\n"); result_text.config(state="disabled"); bt.lift()
    def export_osint_image_results():
        snaps=[snaps_listbox.get(i) for i in range(snaps_listbox.size())]; result_text.config(state="normal"); content=result_text.get("1.0",tk.END); result_text.config(state="disabled")
        fname=filedialog.asksaveasfilename(title="Export OSINT Image results", defaultextension=".txt", filetypes=[("Text files","*.txt"),("All files","*.*")], initialfile="osint_image_results.txt")
        if not fname: return
        try:
            with open(fname,"w",encoding="utf-8") as f:
                f.write("OSINT Image — Export\n"); f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n\n")
                f.write("Wayback snapshots:\n")
                if snaps:
                    for s in snaps: f.write(s+"\n")
                else: f.write("(no snapshots)\n")
                f.write("\nOSINT Image result pane:\n"); f.write(content)
            messagebox.showinfo("Export", f"OSINT Image results saved to:\n{fname}")
        except Exception as e:
            messagebox.showerror("Export error", f"Failed to write file: {e}")
    btn_frame=tk.Frame(bt); btn_frame.pack(pady=(6,12))
    tk.Button(btn_frame, text="Reset", command=reset_osint_image_window, bg="#d92b2b", fg="white", width=10).pack(side="left", padx=8)
    tk.Button(btn_frame, text="Export", command=export_osint_image_results, bg="#444444", fg="#00ff00", width=10).pack(side="left", padx=8)
    tk.Button(btn_frame, text="Close", command=lambda: (bt.destroy(), globals().__setitem__('osint_window', None)), bg="#333333", fg="#00ff00", width=10).pack(side="left", padx=8)
    result_text.config(state="normal"); result_text.delete("1.0",tk.END); result_text.insert(tk.END,"OSINT Image — ready. Use the controls above to fetch Wayback snapshots or extract EXIF.\n"); result_text.config(state="disabled")
    bt.protocol("WM_DELETE_WINDOW", lambda: (bt.destroy(), globals().__setitem__('osint_window', None)))

def do_wayback_full_local(target, listbox_widget, result_text_widget):
    if not target: messagebox.showwarning("Input","Enter a URL or domain for Wayback."); return
    listbox_widget.delete(0,tk.END); listbox_widget.insert(tk.END,"Fetching snapshots (please wait)...")
    result_text_widget.config(state="normal"); result_text_widget.delete("1.0",tk.END); result_text_widget.insert(tk.END,f"[Wayback] Fetching snapshots for: {target}\n"); result_text_widget.config(state="disabled")
    def worker():
        ok,snaps = wayback_snapshots_list(target)
        def update_ui():
            listbox_widget.delete(0,tk.END); result_text_widget.config(state="normal")
            if not ok:
                listbox_widget.insert(tk.END, f"Error: {snaps}"); result_text_widget.insert(tk.END, f"[Wayback] {snaps}\n"); result_text_widget.config(state="disabled"); return
            for ts,u in snaps: listbox_widget.insert(tk.END, f"{ts} {u}")
            result_text_widget.insert(tk.END, f"[Wayback] {len(snaps)} snapshots fetched for {target}. Double-click a line to open snapshot.\n"); result_text_widget.config(state="disabled")
        root.after(0, update_ui)
    threading.Thread(target=worker, daemon=True).start()

def choose_image_and_extract_local(owner_window, result_text_widget):
    path=filedialog.askopenfilename(title="Choose image", filetypes=[("Image files","*.jpg *.jpeg *.png *.tif *.tiff *.heic *.webp"),("All files","*.*")])
    if not path: return
    result_text_widget.config(state="normal"); result_text_widget.insert(tk.END, f"[Image EXIF] Extracting EXIF from: {path}\n"); result_text_widget.see(tk.END); result_text_widget.config(state="disabled")
    def worker():
        ok,lines=exif_from_image_file(path)
        def ui_write():
            result_text_widget.config(state="normal")
            if ok:
                result_text_widget.insert(tk.END, "[Image EXIF] Metadata lines:\n")
                for ln in lines: result_text_widget.insert(tk.END, f" - {ln}\n")
                result_text_widget.insert(tk.END,"\n")
            else:
                for ln in lines: result_text_widget.insert(tk.END, f"[Image EXIF] {ln}\n")
            result_text_widget.see(tk.END); result_text_widget.config(state="disabled"); owner_window.lift()
        root.after(0, ui_write)
    threading.Thread(target=worker, daemon=True).start()

# start welcome blink & run
_blink_welcome_job = root.after(200, _blink_welcome)
output.config(state="normal"); output.config(state="disabled")
root.mainloop()
