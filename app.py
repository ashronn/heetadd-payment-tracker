from flask import Flask, render_template, request, redirect, url_for, session, make_response
from pymongo import MongoClient
from bson.json_util import dumps, loads
from bson.objectid import ObjectId
import webbrowser
import os
from datetime import datetime

# ----------------------------------------------------
# *** 1. การตั้งค่าและการเชื่อมต่อ MongoDB ***
# ----------------------------------------------------
# 🚨 ตรวจสอบ: รหัสผ่านต้องถูกต้อง (Pass123456)
MONGO_URI = "mongodb+srv://heetadd_app_user:Pass123456@heetaddcluster.py4h1je.mongodb.net/?retryWrites=true&w=majority&appName=HeetAddCluster" 

DB_NAME = "heetadd_db" 
COLLECTION_MEMBERS = "members"
COLLECTION_PAYMENTS = "payments"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
members_collection = db[COLLECTION_MEMBERS]
payments_collection = db[COLLECTION_PAYMENTS]

# ----------------------------------------------------
# *** 2. การตั้งค่า Flask และตัวแปรคงที่ ***
# ----------------------------------------------------
app = Flask(__name__)
app.secret_key = 'your_super_secret_key_for_multipage' 

# ตัวแปรเดือนที่ใช้ดูย้อนหลัง (ยังคงเก็บไว้ แต่จะดึงจาก DB ใน Route)
AVAILABLE_MONTHS = [
    {'id': '2025-10', 'name': 'ตุลาคม 2568'},
    {'id': '2025-09', 'name': 'กันยายน 2568'},
    {'id': '2025-08', 'name': 'สิงหาคม 2568'},
]

# การตั้งค่าโฟลเดอร์สำหรับเก็บสลิป
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# -------------------------------------------------------------------------
# ROUTE ควบคุมขั้นตอนการเข้าใช้งาน
# -------------------------------------------------------------------------

@app.route('/')
def index():
    if 'studentId' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

# -------------------------------------------------------------------------
# ขั้นตอนที่ 1: ล็อกอิน / สมัครสมาชิก
# -------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        student_id = request.form.get('student_id').strip()
        
        member = members_collection.find_one({'studentId': student_id})
        
        if member:
            session.clear() 
            session['studentId'] = student_id
            resp = make_response(redirect(url_for('home')))
            return resp
        else:
            error = "รหัสนักศึกษาไม่ถูกต้อง หรือยังไม่ได้สมัครสมาชิก"
            
    return render_template('login.html', error=error)

@app.route('/register', methods=['POST'])
def register():
    new_student_id = request.form.get('new_student_id').strip()
    new_name = request.form.get('new_name').strip()
    
    try:
        if members_collection.find_one({'studentId': new_student_id}):
            return render_template('login.html', error="รหัสนักศึกษานี้มีผู้ใช้งานแล้ว")
            
        members_collection.insert_one({
            'studentId': new_student_id,
            'name': new_name,
            'role': 'user'
        })
        
        # 3. สร้างรายการจ่ายเงินเริ่มต้น
        payment_initial = {
            'studentId': new_student_id,
            'name': new_name,
            # ใช้เดือนเริ่มต้นที่ hardcoded สำหรับการสร้างรายการแรก
            'paymentMonth': AVAILABLE_MONTHS[0]['id'], 
            'paid': False,
            'slipUrl': None,
            'amount': 50
        }
        payments_collection.insert_one(payment_initial)
        
        # 4. ล็อกอินอัตโนมัติและ REDIRECT (เมื่อทุกอย่างสำเร็จ)
        session.clear() 
        session['studentId'] = new_student_id
        return redirect(url_for('home')) 
        
    except Exception as e:
        print(f"Database Error during registration: {e}")
        return render_template('login.html', error="เกิดข้อผิดพลาดในการบันทึกข้อมูล กรุณาลองใหม่")

# -------------------------------------------------------------------------
# ขั้นตอนที่ 2: หน้าหลัก (แสดงสถานะ - ดึงจาก MongoDB)
# -------------------------------------------------------------------------

@app.route('/home', methods=['GET'])
def home():
    if 'studentId' not in session:
        return redirect(url_for('login'))
        
    user_data = members_collection.find_one({'studentId': session['studentId']})
    
    if not user_data: 
        return redirect(url_for('logout'))
    
    # 💥 FIX: ดึงรายการเดือนจาก DB แทนตัวแปร AVAILABLE_MONTHS
    available_months_db = payments_collection.distinct("paymentMonth")
    available_months_for_template = [{'id': m, 'name': m} for m in sorted(available_months_db, reverse=True)]

    # หาเดือนปัจจุบันที่ควรแสดง
    if not available_months_for_template:
        current_month_id = None
        current_month_name = "ยังไม่มีข้อมูลเดือน"
        payments_list = []
    else:
        current_month_id = request.args.get('month_id', available_months_for_template[0]['id'])
        current_month_name = next((m['name'] for m in available_months_for_template if m['id'] == current_month_id), "ไม่พบเดือน")
        
        # ดึงสถานะการจ่ายเงินทั้งหมดสำหรับเดือนนี้จาก MongoDB
        payments_cursor = payments_collection.find({'paymentMonth': current_month_id})
        
        # FIX: แปลง payments_list ให้เป็น JSON ที่ปลอดภัย
        payments_list = loads(dumps(list(payments_cursor)))
        
    # FIX: แปลง user_data ให้เป็น JSON ที่ปลอดภัย
    user_data = loads(dumps(user_data)) 

    return render_template('home.html', 
                           user=user_data,
                           payments=payments_list,
                           available_months=available_months_for_template, # ใช้ตัวแปรใหม่ที่ดึงจาก DB
                           current_month_id=current_month_id,
                           current_month_name=current_month_name
                           )

# -------------------------------------------------------------------------
# ขั้นตอนที่ 3: หน้ากรอกหลักฐานการชำระ (อัปเดต MongoDB + เคลียร์ยอดค้าง)
# -------------------------------------------------------------------------

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'studentId' not in session:
        return redirect(url_for('login'))
        
    user = members_collection.find_one({'studentId': session['studentId']})
    
    # FIX: ดึง available_months จาก DB
    available_months_db = payments_collection.distinct("paymentMonth")
    available_months_for_template = [{'id': m, 'name': m} for m in sorted(available_months_db, reverse=True)]
    
    # คำนวณยอดค้างชำระทั้งหมดสำหรับแสดงผล
    unpaid_payments_cursor = payments_collection.find({
        'studentId': user['studentId'],
        'paid': False
    }).sort('paymentMonth', 1) 
    
    unpaid_months = loads(dumps(list(unpaid_payments_cursor)))
    total_due = len(unpaid_months) * 50 

    
    if request.method == 'POST':
        payment_month_id = request.form.get('payment_month_id')
        amount_paid_str = request.form.get('amount_paid')
        
        try:
            amount_paid = int(amount_paid_str)
        except ValueError:
            return render_template('upload.html', 
                                   user=user, available_months=available_months_for_template, total_due=total_due,
                                   unpaid_months=unpaid_months, error="กรุณากรอกยอดเงินที่จ่ายเป็นตัวเลขเท่านั้น")

        # 1. จัดการไฟล์สลิป (บันทึกในโฟลเดอร์ uploads)
        file = request.files.get('slip_file')
        if not file or file.filename == '':
             return render_template('upload.html', user=user, available_months=available_months_for_template, total_due=total_due,
                                    unpaid_months=unpaid_months, error="กรุณาเลือกไฟล์สลิป")
            
        filename = f"{user['studentId']}_{payment_month_id}_{datetime.now().strftime('%H%M%S')}.jpg"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # 2. ประมวลผลการเคลียร์ยอดค้างชำระตามจำนวนเงิน
        
        remaining_amount = amount_paid
        
        # ค้นหาเดือนที่ยังไม่จ่าย (ใช้ ObjectId จริง)
        all_unpaid_months = payments_collection.find({
            'studentId': user['studentId'],
            'paid': False
        }).sort('paymentMonth', 1) 
        
        # เคลียร์ยอดค้างตามลำดับเดือนเก่าสุด
        for month_record in all_unpaid_months:
            if remaining_amount >= 50:
                payments_collection.update_one(
                    {'_id': month_record['_id']}, 
                    {
                        '$set': {
                            'paid': True, 
                            'slipUrl': url_for('static', filename=f'uploads/{filename}')
                        }
                    }
                )
                remaining_amount -= 50
        
        return redirect(url_for('home'))

    # สำหรับ GET Request: ส่งยอดค้างชำระไปที่ Template
    return render_template('upload.html', 
                           user=user, 
                           available_months=available_months_for_template,
                           total_due=total_due,
                           unpaid_months=unpaid_months)

# -------------------------------------------------------------------------
# ADMIN ROUTES
# -------------------------------------------------------------------------
# ในไฟล์ app.py: แก้ไขที่ Route /admin/dashboard (ต้องใช้ ObjectId)

@app.route('/admin/dashboard', methods=['GET'])
def admin_dashboard():
    if 'studentId' not in session:
        return redirect(url_for('login'))

    user = members_collection.find_one({'studentId': session['studentId']})
    
    # 🛑 Authorization Check: ต้องเป็น 'admin' เท่านั้นจึงจะเข้าได้
    if not user or user.get('role') != 'admin': 
        return redirect(url_for('home'))

    # 1. ดึงข้อมูลสมาชิกทั้งหมด
    all_members = loads(dumps(list(members_collection.find())))
    
    # 2. ดึงสถานะการจ่ายเงินทั้งหมดในทุกเดือน
    all_payments = loads(dumps(list(payments_collection.find().sort('paymentMonth', -1))))

    # 3. ดึงรายการเดือนที่ไม่ซ้ำกัน
    unique_months_db = payments_collection.distinct("paymentMonth")
    unique_months = sorted(list(unique_months_db), reverse=True)

    return render_template('admin_dashboard.html', 
                           user=user,
                           all_members=all_members,
                           all_payments=all_payments,
                           unique_months=unique_months) 

@app.route('/admin/add_month', methods=['POST'])
def admin_add_month():
    if 'studentId' not in session or members_collection.find_one({'studentId': session['studentId']}).get('role') != 'admin':
        return redirect(url_for('home'))

    new_month_id = request.form.get('new_month_id').strip()
    new_month_name = request.form.get('new_month_name').strip()
    
    # 1. สร้างรายการจ่ายเงินเริ่มต้นสำหรับสมาชิกทุกคนในเดือนใหม่
    members_cursor = members_collection.find({})
    payments_to_insert = []
    
    for member in members_cursor:
        payments_to_insert.append({
            'studentId': member['studentId'],
            'name': member['name'],
            'paymentMonth': new_month_id,
            'paid': False,
            'slipUrl': None,
            'amount': 50
        })

    if payments_to_insert:
        payments_collection.insert_many(payments_to_insert)

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_month', methods=['POST'])
def admin_delete_month():
    if 'studentId' not in session or members_collection.find_one({'studentId': session['studentId']}).get('role') != 'admin':
        return redirect(url_for('home'))

    month_to_delete = request.form.get('month_id')
    
    delete_result = payments_collection.delete_many({'paymentMonth': month_to_delete})
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_payment', methods=['POST'])
def admin_edit_payment():
    if 'studentId' not in session or members_collection.find_one({'studentId': session['studentId']}).get('role') != 'admin':
        return redirect(url_for('home'))

    payment_id = request.form.get('payment_id')
    new_status = request.form.get('new_status')
    
    paid_status = True if new_status == 'paid' else False
    
    # อัปเดตใน MongoDB โดยใช้ ObjectId
    payments_collection.update_one(
        {'_id': ObjectId(payment_id)}, # <--- ใช้ ObjectId ที่ถูก Import
        {'$set': {'paid': paid_status}}
    )
    
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.pop('studentId', None)
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.static_folder = UPLOAD_FOLDER
    app.static_url_path = '/uploads'
    
    firefox_path = "C:/Program Files/Mozilla Firefox/firefox.exe" 
    
    try:
        webbrowser.register('firefox', None, webbrowser.BackgroundBrowser(firefox_path))
    except Exception as e:
        print(f"Warning: Could not register Firefox Path. Error: {e}")
        pass
    
    def open_browser():
        import time
        time.sleep(1.5) 
        
        try:
            firefox = webbrowser.get('firefox')
            firefox.open_new_tab('http://127.0.0.1:5000')
        except Exception as e:
            print(f"Error opening Firefox, falling back to default. Error: {e}")
            webbrowser.open_new_tab('http://127.0.0.1:5000')


    import threading
    threading.Thread(target=open_browser).start()
    
    app.run(debug=True, use_reloader=False)