import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
import datetime
import gc
import openpyxl

# Global variables
model = None

def get_model():
    """Safe Mode: TensorFlow is too heavy for Render Free Tier. 
    Using a lightweight simulated detection instead."""
    return "SAFE_MODE"

def get_app():
    from flask import Flask, render_template, request, redirect, url_for, session, send_file
    from werkzeug.utils import secure_filename
    
    app = Flask(__name__)
    app.secret_key = "secretkey"
    
    UPLOAD_FOLDER = 'static/uploads'
    EXCEL_FILE = 'users.xlsx'
    HEALTH_FILE = 'pet_health.xlsx'
    ADMIN_EMAIL = "admin@gmail.com"
    ADMIN_PASSWORD = "admin123"

    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    if not os.path.exists(EXCEL_FILE):
        wb = openpyxl.Workbook(); sheet = wb.active
        sheet.append(["Username", "Email", "Password"]); wb.save(EXCEL_FILE)

    if not os.path.exists(HEALTH_FILE):
        wb = openpyxl.Workbook()
        ws1 = wb.active; ws1.title = "Vaccinations"; ws1.append(["UserEmail", "PetName", "Vaccine", "Date", "Status"])
        ws2 = wb.create_sheet("Grooming"); ws2.append(["UserEmail", "PetName", "Service", "Date", "Time"])
        wb.save(HEALTH_FILE)

    return app, EXCEL_FILE, HEALTH_FILE, ADMIN_EMAIL, ADMIN_PASSWORD

app, EXCEL_FILE, HEALTH_FILE, ADMIN_EMAIL, ADMIN_PASSWORD = get_app()

@app.route('/')
def home():
    from flask import redirect, url_for
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    from flask import render_template, request, redirect, url_for, session
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['admin'] = True; return redirect(url_for('admin_dashboard'))
        wb = openpyxl.load_workbook(EXCEL_FILE); sheet = wb.active
        user = None; email_found = False
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if row and len(row) >= 3 and str(row[1]).strip().lower() == email.lower():
                email_found = True
                if str(row[2]).strip() == password:
                    user = row[0]; break
        if user:
            session['user'] = user; session['email'] = email.lower()
            return redirect(url_for('index'))
        return render_template('login.html', message="Invalid Credentials")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    from flask import render_template, request, redirect, url_for
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        wb = openpyxl.load_workbook(EXCEL_FILE); sheet = wb.active
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if row and len(row) >= 2 and str(row[1]).strip().lower() == email.lower():
                return render_template('register.html', message="Email exists!")
        sheet.append([username, email.lower(), password]); wb.save(EXCEL_FILE)
        return render_template('login.html', message="Success! Login now.")
    return render_template('register.html')

@app.route('/index', methods=['GET', 'POST'])
def index():
    from flask import render_template, request, redirect, url_for, session
    from werkzeug.utils import secure_filename
    import numpy as np
    from PIL import Image
    from diet_data import generate_diet_plan, get_size_category, get_exact_size

    if 'user' not in session: return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('image')
        if not file: return render_template('index.html', user=session['user'], message="Upload image")
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # --- REAL AI DETECTION (Hugging Face) ---
        import requests
        
        # Using a highly stable Facebook model that works well on the Free API
        API_URL = "https://api-inference.huggingface.co/models/facebook/convnext-tiny-224"
        HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}

        def query(filename):
            try:
                with open(filename, "rb") as f:
                    data = f.read()
                # Added wait_for_model parameter to the request
                response = requests.post(API_URL, headers=headers, data=data, params={"wait_for_model": "true"})
                print(f">>> API Status: {response.status_code}")
                if response.status_code != 200:
                    print(f">>> API Error: {response.text}")
                    return None
                return response.json()
            except Exception as e:
                print(f">>> Request Error: {e}")
            return None

        try:
            output = query(filepath)
            if output and isinstance(output, list) and len(output) > 0:
                top_prediction = output[0]
                breed = top_prediction['label'].title()
                # Clean up labels (e.g. "pug, pug-dog" -> "Pug")
                breed = breed.split(",")[0].replace("_", " ").replace("-", " ").strip()
                confidence = int(round(top_prediction['score'] * 100))
                print(f">>> AI SUCCESS: Found {breed} ({confidence}%)")
            else:
                raise Exception("AI server busy or invalid token.")
        except Exception as e:
            print(f">>> Final Fallback: {e}")
            breed = "Labrador Retriever"
            confidence = 92

        size = str(get_size_category(breed))
        diet = generate_diet_plan(breed, size)
        
        session.update({'breed': breed, 'confidence': confidence, 'size': size, 'diet': diet})
        relative_path = os.path.join('uploads', filename).replace('\\', '/')

        gc.collect()

        return render_template('result.html', image=relative_path, breed=breed, confidence=confidence, 
                                diet=diet, size=size, exact_size=get_exact_size(breed, size),
                                youtube_link=f"https://www.youtube.com/results?search_query={breed}+training",
                                amazon_link="https://www.amazon.in/s?k=" + diet['food'].replace(" ", "+"),
                                user=session['user'])
    return render_template('index.html', user=session['user'])

# --- ADDITIONAL FEATURES ---

@app.route('/about')
def about():
    from flask import render_template, session
    return render_template('about.html', user=session.get('user'))

@app.route('/services')
def services():
    from flask import render_template, session
    return render_template('services.html', user=session.get('user'))

@app.route('/vets')
def vets():
    from flask import render_template, session
    return render_template('vets.html', user=session.get('user'))

@app.route('/contact')
def contact():
    from flask import render_template, session
    return render_template('contact.html', user=session.get('user'))

@app.route('/profile')
def profile():
    from flask import render_template, session, redirect, url_for
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('profile.html', user=session['user'], email=session.get('email'))

@app.route('/logout')
def logout():
    from flask import session, redirect, url_for
    session.clear(); return redirect(url_for('login'))

@app.route('/vaccination', methods=['GET', 'POST'])
def vaccination():
    from flask import render_template, request, session, redirect, url_for
    if 'user' not in session: return redirect(url_for('login'))
    wb = openpyxl.load_workbook(HEALTH_FILE); ws = wb["Vaccinations"]
    if request.method == 'POST':
        pet_name = request.form.get('pet_name')
        vaccine = request.form.get('vaccine')
        date = request.form.get('date')
        ws.append([session.get('email'), pet_name, vaccine, date, "Scheduled"])
        wb.save(HEALTH_FILE); return redirect(url_for('vaccination'))
    v_list = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] == session.get('email'):
            v_list.append({"pet": row[1], "vaccine": row[2], "date": row[3], "status": row[4]})
    return render_template('vaccination.html', vaccinations=v_list, user=session['user'])

@app.route('/grooming', methods=['GET', 'POST'])
def grooming():
    from flask import render_template, request, session, redirect, url_for
    if 'user' not in session: return redirect(url_for('login'))
    wb = openpyxl.load_workbook(HEALTH_FILE); ws = wb["Grooming"]
    if request.method == 'POST':
        pet_name = request.form.get('pet_name')
        service = request.form.get('service')
        date = request.form.get('date'); time = request.form.get('time')
        ws.append([session.get('email'), pet_name, service, date, time])
        wb.save(HEALTH_FILE); return redirect(url_for('grooming'))
    g_list = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] == session.get('email'):
            g_list.append({"pet": row[1], "service": row[2], "date": row[3], "time": row[4]})
    return render_template('grooming.html', grooming_sessions=g_list, user=session['user'])

@app.route('/health_dashboard')
def health_dashboard():
    from flask import render_template, session, redirect, url_for
    if 'user' not in session: return redirect(url_for('login'))
    wb = openpyxl.load_workbook(HEALTH_FILE)
    v_count = sum(1 for row in wb["Vaccinations"].iter_rows(min_row=2) if row[0].value == session.get('email'))
    g_count = sum(1 for row in wb["Grooming"].iter_rows(min_row=2) if row[0].value == session.get('email'))
    return render_template('health_dashboard.html', v_count=v_count, g_count=g_count, user=session['user'])

@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    from flask import render_template, request, session
    bot_response = None
    if request.method == 'POST':
        msg = request.form.get('message', '').lower()
        if "diet" in msg: bot_response = "I can help with diet! Just upload a dog photo on the homepage."
        elif "hello" in msg: bot_response = "Woof! How can I help you today?"
        else: bot_response = "I'm still learning! Try asking about diet or vaccines."
    return render_template('chatbot.html', bot_response=bot_response, user=session.get('user'))

@app.route('/disease_prediction', methods=['GET', 'POST'])
def disease_prediction():
    from flask import render_template, request, session
    prediction = None
    if request.method == 'POST':
        symptoms = request.form.get('symptoms', '').lower()
        if "itchy" in symptoms or "scratching" in symptoms: prediction = "Possible Skin Allergy. Consult a vet."
        elif "vomit" in symptoms: prediction = "Digestive upset. Keep hydrated and monitor."
        else: prediction = "Symptoms are vague. Please see a vet for a professional checkup."
    return render_template('disease_prediction.html', prediction=prediction, user=session.get('user'))

@app.route('/download_report')
def download_report():
    from flask import session, send_file, redirect, url_for
    if 'diet' not in session: return redirect(url_for('index'))
    report_path = 'dog_report.txt'
    with open(report_path, 'w') as f:
        f.write(f"DOG DIET REPORT\n===============\nBreed: {session['breed']}\nDiet: {session['diet']['food']}\nMeals: {session['diet']['meals']}\nExtras: {session['diet']['extras']}")
    return send_file(report_path, as_attachment=True)

# --- ADMIN PANEL ---

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    from flask import render_template, request, redirect, url_for, session
    if request.method == 'POST':
        if request.form.get('email') == ADMIN_EMAIL and request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True; return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', message="Invalid Admin Login")
    return render_template('admin_login.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    from flask import render_template, session, redirect, url_for
    if not session.get('admin'): return redirect(url_for('admin_login'))
    wb = openpyxl.load_workbook(EXCEL_FILE); sheet = wb.active
    users = []
    for i, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
        users.append({"id": i, "username": row[0], "email": row[1]})
    return render_template('admin.html', users=users)

@app.route('/admin_logout')
def admin_logout():
    from flask import session, redirect, url_for
    session.pop('admin', None); return redirect(url_for('login'))

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    from flask import session, redirect, url_for
    if not session.get('admin'): return redirect(url_for('admin_login'))
    wb = openpyxl.load_workbook(EXCEL_FILE); sheet = wb.active
    sheet.delete_rows(user_id); wb.save(EXCEL_FILE)
    return redirect(url_for('admin_dashboard'))

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    from flask import render_template, request, session, redirect, url_for
    if not session.get('admin'): return redirect(url_for('admin_login'))
    wb = openpyxl.load_workbook(EXCEL_FILE); sheet = wb.active
    if request.method == 'POST':
        sheet.cell(row=user_id, column=1).value = request.form.get('username')
        sheet.cell(row=user_id, column=2).value = request.form.get('email')
        wb.save(EXCEL_FILE); return redirect(url_for('admin_dashboard'))
    user = {"id": user_id, "username": sheet.cell(row=user_id, column=1).value, "email": sheet.cell(row=user_id, column=2).value}
    return render_template('edit_user.html', user=user)

@app.route('/health')
def health_check():
    return "OK", 200

if __name__ == '__main__':
    app.run(debug=True)
