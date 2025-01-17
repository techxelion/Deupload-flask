

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import os
import threading
import requests
import paho.mqtt.client as mqtt
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId
import base64
from flask_talisman import Talisman
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from logging.handlers import RotatingFileHandler
import cv2
import base64
import werkzeug
from flask import Flask, request, render_template, send_from_directory, redirect, url_for
from flask import  jsonify
from flask_talisman import Talisman

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
handler = RotatingFileHandler('app.log', maxBytes=10000000, backupCount=5)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
handler.setLevel(logging.INFO)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this in production

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client.document_management

app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['WATCHED_FOLDER'] = 'watched/'
app.config['PROCESSED_FOLDER'] = 'processed/'
app.logger.addHandler(handler)

# Initialize Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.user_data = user_data

    def get_id(self):
        return str(self.user_data['_id'])

    @property
    def id(self):
        return str(self.user_data['_id'])

    @property
    def username(self):
        return self.user_data['username']

@login_manager.user_loader
def load_user(user_id):
    user_data = db.users.find_one({'_id': ObjectId(user_id)})
    return User(user_data) if user_data else None

def create_indexes():
    # Create text index for documents
    db.documents.create_index([('text', 'text')])
    # Create unique index for username
    db.users.create_index('username', unique=True)


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            user_data = db.users.find_one({'username': request.form['username']})
            if user_data and check_password_hash(user_data['password_hash'], request.form['password']):
                user = User(user_data)
                login_user(user)
                app.logger.info(f'User {user.username} logged in successfully')
                return redirect(url_for('upload'))
            flash('Invalid username or password')
            app.logger.warning(f'Failed login attempt for username: {request.form["username"]}')
        except Exception as e:
            app.logger.error(f'Login error: {str(e)}')
            flash('An error occurred during login')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        try:
            file = request.files['document']
            if file:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                new_doc = {
                    'filename': filename,
                    'user_id': ObjectId(current_user.id),
                    'status': 'hochgeladen',
                    'created_at': datetime.utcnow(),
                    'text': ''
                }
                db.documents.insert_one(new_doc)
                
                app.logger.info(f'Document {filename} uploaded successfully by user {current_user.username}')
                return redirect(url_for('status'))
                
        except Exception as e:
            app.logger.error(f'Error during file upload: {str(e)}')
            flash('Error uploading file. Please try again.')
            
    return render_template('upload.html')
@app.route('/preview/<filename>')
@login_required
def preview(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# @app.route('/scan_document', methods=['GET'])
# @login_required
# def scan_document():
#     cap = cv2.VideoCapture(0)
#     ret, frame = cap.read()
#     cap.release()
#     if ret:
#         filename = f"scanned_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg"
#         filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#         cv2.imwrite(filepath, frame)
#         db.documents.insert_one({
#             'filename': filename,
#             'user_id': ObjectId(current_user.id),
#             'status': 'scanned',
#             'created_at': datetime.utcnow()
#         })
#         return jsonify({'message': 'Document scanned successfully', 'filename': filename})
#     return jsonify({'error': 'Failed to scan document'}), 500
# @app.route('/scan_document', methods=['GET', 'POST'])
# @login_required
# def scan_document():
#     if request.method == 'POST':
#         cap = cv2.VideoCapture(0)
#         ret, frame = cap.read()
#         cap.release()
#         if ret:
#             filename = f"scanned_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg"
#             filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             cv2.imwrite(filepath, frame)
#             db.documents.insert_one({
#                 'filename': filename,
#                 'user_id': ObjectId(current_user.id),
#                 'status': 'scanned',
#                 'created_at': datetime.utcnow()
#             })
#             return jsonify({'message': 'Document scanned successfully', 'filename': filename})
#         return jsonify({'error': 'Failed to scan document'}), 500
#     return render_template('scanned.html')
@app.route('/scan_document', methods=['GET', 'POST'])
@login_required
def scan_document():
    if request.method == 'POST':
        data = request.get_json()  # Get JSON data from the POST request
        image_data = data.get('image')  # Extract image data

        if image_data:
            # Extract base64 image data (remove 'data:image/jpeg;base64,' part)
            img_data = image_data.split(',')[1]
            filename = f"scanned_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # Save the image data as a file
            with open(filepath, 'wb') as f:
                f.write(base64.b64decode(img_data))

            # Store the document in the database
            db.documents.insert_one({
                'filename': filename,
                'user_id': ObjectId(current_user.id),
                'status': 'scanned',
                'created_at': datetime.utcnow()
            })

            # Return success message with filename
            return jsonify({'message': 'Document scanned successfully', 'filename': filename})

        # If image data isn't received
        return jsonify({'error': 'Failed to scan document'}), 500

    # For GET requests, render the scan document page
    return render_template('scanned.html')

@app.route('/status')
@login_required
def status():
    try:
        documents = list(db.documents.find({'user_id': ObjectId(current_user.id)}))
        return render_template('status.html', documents=documents)
    except Exception as e:
        app.logger.error(f'Error fetching status: {str(e)}')
        flash('Error loading documents')
        return redirect(url_for('upload'))

@app.route('/status_data')
@login_required
def status_data():
    try:
        documents = list(db.documents.find({'user_id': ObjectId(current_user.id)}))
        return jsonify([{
            'id': str(doc['_id']),
            'filename': doc['filename'],
            'status': doc['status']
        } for doc in documents])
    except Exception as e:
        app.logger.error(f'Error fetching status data: {str(e)}')
        return jsonify({'error': 'Error fetching documents'}), 500

@app.route('/search')
@login_required
def search():
    query = request.args.get('query', '')
    results = []
    if query:
        try:
            documents = db.documents.find({
                'user_id': ObjectId(current_user.id),
                'text': {'$regex': query, '$options': 'i'}
            })
            
            for doc in documents:
                text = doc.get('text', '')
                index = text.lower().find(query.lower())
                start = max(index - 30, 0)
                end = min(index + 30, len(text))
                context = text[start:end]
                context = context.replace(query, f"<mark>{query}</mark>")
                results.append({
                    'id': str(doc['_id']),
                    'filename': doc['filename'],
                    'context': context
                })
        except Exception as e:
            app.logger.error(f'Search error: {str(e)}')
            flash('Error performing search')
            
    return render_template('search.html', results=results, query=query)

def process_document(document_id):
    try:
        doc = db.documents.find_one({'_id': ObjectId(document_id)})
        if not doc:
            app.logger.error(f'Document {document_id} not found')
            return

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], doc['filename'])
        api_key = os.getenv('OCR_API_KEY')
        
        if not api_key:
            app.logger.error('OCR API key not found')
            db.documents.update_one(
                {'_id': ObjectId(document_id)},
                {'$set': {'status': 'Fehler: Kein API-Schlüssel'}}
            )
            return

        with open(filepath, 'rb') as f:
            response = requests.post(
                'https://api.ocr.space/parse/image',
                files={'filename': f},
                data={'apikey': api_key, 'language': 'ger'}
            )
            
        result = response.json()
        if result.get('IsErroredOnProcessing'):
            status = 'Fehler bei Verarbeitung'
            app.logger.error(f'OCR processing error for document {document_id}')
        else:
            text = result['ParsedResults'][0]['ParsedText']
            status = 'verarbeitet'
            db.documents.update_one(
                {'_id': ObjectId(document_id)},
                {'$set': {'text': text, 'status': status}}
            )
            app.logger.info(f'Document {document_id} processed successfully')
            
    except Exception as e:
        app.logger.error(f'Error processing document {document_id}: {str(e)}')
        db.documents.update_one(
            {'_id': ObjectId(document_id)},
            {'$set': {'status': 'Verarbeitungsfehler'}}
        )

def create_admin_user():
    try:
        if not db.users.find_one({'username': 'admin'}):
            password_hash = generate_password_hash('password')
            db.users.insert_one({
                'username': 'admin',
                'password_hash': password_hash,
                'created_at': datetime.utcnow()
            })
            print("Admin user created successfully")
    except Exception as e:
        print(f"Error creating admin user: {str(e)}")

if __name__ == '__main__':
    # Create required directories
    for folder in [app.config['UPLOAD_FOLDER'], app.config['WATCHED_FOLDER'], 
                  app.config['PROCESSED_FOLDER']]:
        if not os.path.exists(folder):
            os.makedirs(folder)

    # Create indexes and admin user
    create_indexes()
    create_admin_user()

    # Start scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: [process_document(str(doc['_id'])) 
                     for doc in db.documents.find({'status': 'hochgeladen'})],
        trigger="interval",
        minutes=5
    )
    scheduler.start()

    try:
        # Run app in debug mode for local development
        app.run(debug=True, host='localhost', port=5000)
    except Exception as e:
        app.logger.error(f'Error starting server: {str(e)}')
    finally:
        scheduler.shutdown()