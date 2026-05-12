import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
import datetime
import gc

# Global variables
model = None

def get_model():
    """Lazy-load the model only when needed."""
    global model
    if model is None:
        try:
            print(">>> AI: Loading TensorFlow for the first time...")
            import tensorflow as tf
            
            # Memory optimization: Limit TensorFlow threads to save RAM
            tf.config.threading.set_intra_op_parallelism_threads(1)
            tf.config.threading.set_inter_op_parallelism_threads(1)
            
            # Load the model
            model = tf.keras.applications.MobileNetV2(weights='imagenet')
            print(">>> AI: Model loaded successfully!")
            gc.collect()
        except Exception as e:
            print(f">>> AI ERROR: Failed to load model: {e}")
            return None
    return model

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

        # GET THE MODEL (Lazy Loaded)
        current_model = get_model()
        if current_model is None:
            return render_template('index.html', user=session['user'], message="AI Server busy. Try again.")

        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input, decode_predictions
        img = Image.open(filepath).convert('RGB').resize((224, 224))
        img_array = np.array(img).astype(np.float32)
        img_array = preprocess_input(img_array)
        img_array = np.expand_dims(img_array, axis=0)

        predictions = current_model.predict(img_array)
        decoded = decode_predictions(predictions, top=1)[0][0]

        breed = str(decoded[1])
        confidence = int(round(decoded[2] * 100))
        size = str(get_size_category(breed))
        diet = generate_diet_plan(breed, size)
        
        session.update({'breed': breed, 'confidence': confidence, 'size': size, 'diet': diet})
        relative_path = os.path.join('uploads', filename).replace('\\', '/')

        # Clean up memory after heavy prediction
        gc.collect()
        
        # Free up TensorFlow memory explicitly if possible
        # (Though with lazy loading it stays in memory once loaded)

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
