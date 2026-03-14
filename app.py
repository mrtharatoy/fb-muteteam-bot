import os
import requests
import re
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

# --- 1. โหลดรายชื่อรูป ---
def update_file_list():
    global CACHED_FILES
    print("🔄 Loading file list...")
    api_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{REPO_NAME}/contents/{FOLDER_NAME}?ref={BRANCH}"
    headers = {"User-Agent": "Bot", "Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN: headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    try:
        r = requests.get(api_url, headers=headers)
        if r.status_code == 200:
            data = r.json()
            CACHED_FILES.clear()
            for item in data:
                if item['type'] == 'file':
                    key = item['name'].rsplit('.', 1)[0].strip().lower()
                    CACHED_FILES[key] = item['name']
            print(f"📂 FILES READY: {len(CACHED_FILES)} images.")
    except Exception as e:
        print(f"❌ Error: {e}")

update_file_list()

def get_image_url(filename):
    return f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{REPO_NAME}/{BRANCH}/{FOLDER_NAME}/{filename}"

# --- ฟังก์ชันส่งข้อความ (ฝัง Metadata กันลูป) ---
def send_message(recipient_id, text):
    print(f"💬 Sending message to {recipient_id}: {text}")
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text,
            "metadata": "BOT_SENT_THIS" # กันลูป
        }
    }
    requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data)

def send_image(recipient_id, image_url):
    print(f"📤 Sending image to {recipient_id}...")
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": image_url, "is_reusable": True}
            },
            "metadata": "BOT_SENT_THIS" # กันลูป
        }
    }
    requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data)

# --- 2. LOGIC วิเคราะห์ข้อความ ---
def process_message(target_id, text, is_admin_sender):
    text_lower = text.lower()
    found_actions = [] 
    
    # 1️⃣ หารหัสที่ถูกต้อง
    for code_key, full_filename in CACHED_FILES.items():
        if code_key in text_lower:
            if (code_key, full_filename) not in found_actions:
                found_actions.append((code_key, full_filename))

    # ✅ เจอรูป -> ส่ง
    if found_actions:
        # --- ส่งข้อความเปิดหัว (ส่งแค่รอบเดียว) ---
        intro_msg = (
            "📸 ขออนุญาตส่งภาพนะครับ\n"
            "รวมภาพงานพิธี กดได้ที่ link นี้\n\n"
            " -> linktr.ee/mahabucha\n\n"
            "หรือ รับชมได้ที่หน้าเพจ \"มหาบูชา\"\n\n"
            "ทีมงานเทวาลัยสยามคเณศ ขอขอบคุณครับ"
        )
        send_message(target_id, intro_msg)
        # ---------------------------------------------

        # วนลูปส่งรูปตามรายการที่หาเจอ
        for code_key, filename in found_actions:
            print(f"✅ Code found ({code_key}) -> Sending to {target_id}")
            
            # ข้อความระบุรหัส
            msg = f"ภาพถาดถวาย รหัส : {code_key}"
            send_message(target_id, msg)
            
            # ส่งรูป
            send_image(target_id, get_image_url(filename))
            
    # ถ้าเป็น Admin ให้จบแค่นี้
    if is_admin_sender:
        return 

    # --- ส่วนของ User Only ---
    unknown_codes = []
    potential_matches = re.findall(r'[a-z0-9]*\d+[a-z0-9]*', text_lower)
    
    for word in potential_matches:
        if len(word) >= 4:
            is_known = False
            for found_key, _ in found_actions:
                if found_key in word or word in found_key:
                    is_known = True
                    break
            if not is_known:
                for known_key in CACHED_FILES.keys():
                    if known_key in word: 
                        is_known = True
                        break
            if not is_known and word not in unknown_codes:
                unknown_codes.append(word)

    # แจ้งเตือนรหัสที่ไม่พบ
    if unknown_codes:
        for bad_code in unknown_codes:
            msg = f"⚠️ รหัส '{bad_code}' ไม่พบในระบบ หรืออาจพิมพ์ผิดครับ"
            send_message(target_id, msg)

    # ถ้าไม่เจออะไรเลย + มีคำว่า รูป/ภาพ
    if not found_actions and not unknown_codes:
        if 'รูป' in text_lower or 'ภาพ' in text_lower:
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
                        
                        # --- 🛑 กันลูปด้วย Metadata ---
                        if event.get('message', {}).get('metadata') == "BOT_SENT_THIS":
                            continue
                        # ----------------------------

                        is_echo = event.get('message', {}).get('is_echo', False)
                        
                        if is_echo:
                            # Admin พิมพ์
                            if 'recipient' in event and 'id' in event['recipient']:
                                target_id = event['recipient']['id']
                                print(f"👮 Admin typed: {text}")
                                process_message(target_id, text, is_admin_sender=True)
                        else:
                            # ลูกค้าพิมพ์
                            target_id = event['sender']['id']
                            print(f"👤 User typed: {text}")
                            process_message(target_id, text, is_admin_sender=False)
                        
    return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)
