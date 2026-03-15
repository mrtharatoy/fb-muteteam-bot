import os
import requests
import re
import threading
from flask import Flask, request

app = Flask(__name__)

# --- CONFIG ---
GITHUB_USERNAME = "mrtharatoy"
REPO_NAME = "fb-muteteam-bot"
BRANCH = "main"
FOLDER_NAME = "images" 
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

CACHED_FILES = {}
FILES_LOADED = False

# --- 1. โหลดรายชื่อรูป (โหลดแบบ Background ไม่กวน Render) ---
def update_file_list():
    global CACHED_FILES, FILES_LOADED
    print("🔄 Loading file list from GitHub...")
    api_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{REPO_NAME}/contents/{FOLDER_NAME}?ref={BRANCH}"
    headers = {"User-Agent": "Bot", "Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN: headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    try:
        r = requests.get(api_url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            temp_cache = {}
            for item in data:
                if item['type'] == 'file':
                    key = item['name'].rsplit('.', 1)[0].strip().lower()
                    temp_cache[key] = item['name']
            CACHED_FILES = temp_cache
            FILES_LOADED = True
            print(f"✅ FILES READY: {len(CACHED_FILES)} images.")
        else:
            print(f"⚠️ Github Error: {r.status_code}")
    except Exception as e:
        print(f"❌ Error loading files: {e}")

# --- ฟังก์ชันแย่งไมค์ (สู้กับ Zwiz) ---
def take_thread_control(recipient_id):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": recipient_id}}
    r = requests.post("https://graph.facebook.com/v19.0/me/take_thread_control", params=params, json=data)
    if r.status_code != 200:
        print(f"⚠️ Take Control Failed (Zwiz block?): {r.text}")

# --- ฟังก์ชันส่งข้อความ ---
def send_message(recipient_id, text):
    print(f"💬 Sending: {text}")
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text, "metadata": "BOT_SENT_THIS"}
    }
    r = requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data)
    if r.status_code != 200:
        print(f"❌ Send Text Error: {r.text}")

def send_image(recipient_id, image_url):
    print(f"📤 Sending Image...")
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {"type": "image", "payload": {"url": image_url, "is_reusable": True}},
            "metadata": "BOT_SENT_THIS"
        }
    }
    r = requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data)
    if r.status_code != 200:
        print(f"❌ Send Image Error: {r.text}")

# --- 2. LOGIC ---
def process_message(target_id, text, is_admin_sender):
    if not FILES_LOADED:
        print("⚠️ Waiting for files to load...")
        return

    text_lower = text.lower()
    found_actions = [] 
    
    # หารหัส
    for code_key, full_filename in CACHED_FILES.items():
        if code_key in text_lower:
            if (code_key, full_filename) not in found_actions:
                found_actions.append((code_key, full_filename))

    # เจอรูป -> ส่ง
    if found_actions:
        take_thread_control(target_id) # แย่งไมค์ก่อนส่ง
        
        intro_msg = (
            "📸 ขออนุญาตส่งภาพนะครับ\n"
            "รวมภาพงานพิธี กดได้ที่ link นี้\n\n"
            " -> linktr.ee/mahabucha\n\n"
            "หรือ รับชมได้ที่หน้าเพจ \"มหาบูชา\"\n\n"
            "ทีมงานเทวาลัยสยามคเณศ ขอขอบคุณครับ"
        )
        send_message(target_id, intro_msg)

        for code_key, filename in found_actions:
            send_message(target_id, f"ภาพถาดถวาย รหัส : {code_key}")
            send_image(target_id, get_image_url(filename))
            
    if is_admin_sender: return 

    # ไม่เจอรูป -> แจ้งเตือน
    unknown_codes = []
    potential_matches = re.findall(r'[a-z0-9]*\d+[a-z0-9]*', text_lower)
    
    for word in potential_matches:
        if len(word) >= 4:
            is_known = any(found_key in word or word in found_key for found_key, _ in found_actions)
            if not is_known:
                is_known = any(known_key in word for known_key in CACHED_FILES.keys())
            if not is_known and word not in unknown_codes:
                unknown_codes.append(word)

    if unknown_codes:
        take_thread_control(target_id)
        for bad_code in unknown_codes:
            send_message(target_id, f"⚠️ รหัส '{bad_code}' ไม่พบในระบบ หรืออาจพิมพ์ผิดครับ")

    if not found_actions and not unknown_codes and ('รูป' in text_lower or 'ภาพ' in text_lower):
        take_thread_control(target_id)
        msg = (
            "สำหรับผู้ศรัทธาที่ต้องการภาพถาดถวาย สามารถพิมพ์ 'รหัสภาพ' ของท่านได้เลยครับ (เช่น 999AA01)\n\n"
            "หรือถ้าไม่ทราบรหัส รบกวนรอแอดมินสักครู่นะครับ 😊"
        )
        send_message(target_id, msg)

# --- 3. WEBHOOK ---
@app.route('/', methods=['GET'])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Bot Running", 200

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    if data['object'] == 'page':
        for entry in data['entry']:
            if 'messaging' in entry:
                for event in entry['messaging']:
                    if 'message' in event:
                        text = event['message'].get('text', '')
                        if event.get('message', {}).get('metadata') == "BOT_SENT_THIS": continue
                        
                        is_echo = event.get('message', {}).get('is_echo', False)
                        if is_echo:
                            if 'recipient' in event and 'id' in event['recipient']:
                                process_message(event['recipient']['id'], text, is_admin_sender=True)
                        else:
                            process_message(event['sender']['id'], text, is_admin_sender=False)
    return "ok", 200

if __name__ == '__main__':
    # สั่งให้โหลดรูปใน Background ทันที โดยไม่บล็อกเซิร์ฟเวอร์
    threading.Thread(target=update_file_list).start()
    
    # ผูก Port 0.0.0.0 ตามที่ Render ต้องการ
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
