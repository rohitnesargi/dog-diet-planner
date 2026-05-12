import os
import datetime
import threading

# Global variables
app_instance = None
model = None
model_ready = False

def load_model_background():
    global model, model_ready
    try:
        print(">>> BACKGROUND: Starting AI Model Load...")
        import tensorflow as tf
        model = tf.keras.applications.MobileNetV2(weights='imagenet')
        model_ready = True
        print(">>> BACKGROUND: AI Model Loaded and Ready!")
    except Exception as e:
        print(f">>> BACKGROUND ERROR: {e}")

def get_app():
    from flask import Flask, render_template, request, redirect, url_for, session, send_file
    from werkzeug.utils import secure_filename
    import openpyxl
    
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

    # START THE BACKGROUND LOAD
    thread = threading.Thread(target=load_model_background)
    thread.daemon = True
    thread.start()

    return app, EXCEL_FILE, HEALTH_FILE, ADMIN_EMAIL, ADMIN_PASSWORD

app, EXCEL_FILE, HEALTH_FILE, ADMIN_EMAIL, ADMIN_PASSWORD = get_app()

@app.route('/')
def home():
    from flask import redirect, url_for
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    from flask import render_template, request, redirect, url_for, session
    import openpyxl
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['admin'] = True; return redirect(url_for('admin_dashboard'))
        wb = openpyxl.load_workbook(EXCEL_FILE); sheet = wb.active
        user = None
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if row and len(row) >= 3 and str(row[1]).strip().lower() == email.lower() and str(row[2]).strip() == password:
                user = row[0]; break
        if user:
            session['user'] = user; return redirect(url_for('index'))
        return render_template('login.html', message="Invalid Credentials")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    from flask import render_template, request, redirect, url_for
    import openpyxl
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

        # WAIT FOR MODEL TO BE READY (if it's still loading)
        global model, model_ready
        if not model_ready:
            print(">>> PREDICTION: Waiting for model to finish loading...")
            # If it's not ready, we have to import it now (fallback)
            import tensorflow as tf
            if model is None:
                model = tf.keras.applications.MobileNetV2(weights='imagenet')
                model_ready = True

        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input, decode_predictions
        img = Image.open(filepath).convert('RGB').resize((224, 224))
        img_array = np.array(img).astype(np.float32)
        img_array = preprocess_input(img_array)
        img_array = np.expand_dims(img_array, axis=0)

        predictions = model.predict(img_array)
        decoded = decode_predictions(predictions, top=1)[0][0]

        breed = str(decoded[1])
        confidence = int(round(decoded[2] * 100))
        size = str(get_size_category(breed))
        diet = generate_diet_plan(breed, size)
        
        session.update({'breed': breed, 'confidence': confidence, 'size': size, 'diet': diet})
        relative_path = os.path.join('uploads', filename).replace('\\', '/')

        return render_template('result.html', image=relative_path, breed=breed, confidence=confidence, 
                               diet=diet, size=size, exact_size=get_exact_size(breed, size),
                               youtube_link=f"https://www.youtube.com/results?search_query={breed}+training",
                               amazon_link="https://www.amazon.in/s?k=" + diet['food'].replace(" ", "+"),
                               user=session['user'])
    return render_template('index.html', user=session['user'])

@app.route('/health')
def health_check():
    return "OK", 200

if __name__ == '__main__':
    app.run(debug=True)
