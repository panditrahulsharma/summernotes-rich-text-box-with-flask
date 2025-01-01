import os
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template, url_for
import boto3
import secrets
import string
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import datetime
from sqlalchemy import desc

app = Flask(__name__)

# Configure the app
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///content.db'  # Update to your database
app.config['UPLOAD_FOLDER'] = 'static/uploads'  # Folder to save files
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit uploads to 10MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif','zip','pdf',  'csv','txt', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'}

# AWS S3 configuration
S3_BUCKET = 'bucket-name'
S3_REGION = 'ap-south-1'  # e.g., 'us-west-1'
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY')
AWS_SECRET_KEY =os.environ.get('AWS_SECRET_KEY')
AWS_SESSION_TOKEN = os.environ.get('AWS_SESSION_TOKEN') 

#initialize the s3 client
s3_client = boto3.client('s3', 
                         region_name=S3_REGION, 
                         aws_access_key_id=AWS_ACCESS_KEY, 
                         aws_secret_access_key=AWS_SECRET_KEY, 
                         aws_session_token=AWS_SESSION_TOKEN
        )

S3_DOMAIN='https://aws.com'

# Initialize the database
db = SQLAlchemy(app)


# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Define the Content model
class Content(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    attachments = db.Column(db.Text, nullable=True)  # Store file paths as comma-separated strings
    
# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_extension(filename):
    return filename.rsplit('.', 1)[1].lower()




def generate_random_filename(extension="png"):
    """Generate a timestamped filename with a random string."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_at_%I.%M.%S_%p")
    random_string = secrets.token_hex(10)  # Generate an 8-character random string
    return f"{random_string}-{timestamp}.{extension}"


@app.route('/delete/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    comment = Content.query.get(comment_id)
    
    if comment:
        
        content = comment.content  # HTML content
        soup = BeautifulSoup(content, 'html.parser')
        image_urls = [img['src'] for img in soup.find_all('img') if 'src' in img.attrs]
        print("image_urls",image_urls)
        
        # Delete files from S3
        for url in image_urls:
            parsed_url = urlparse(url)
            file_path = parsed_url.path.lstrip('/')  # Extract S3 key from URL
            filename=file_path.split('/')[-1]
            s3_directory_loc = f'files/{filename}'
            try:
                s3_client.delete_object(Bucket=S3_BUCKET, Key=s3_directory_loc)
            except Exception as e:
                print(f'Error deleting file {s3_directory_loc} from S3: {e}')
                return jsonify({'message': f'Error deleting file {s3_directory_loc}'}), 500
    
    
        db.session.delete(comment)
        db.session.commit()
        return jsonify({'message': 'Comment deleted successfully!'}), 200
    return jsonify({'message': 'Comment not found!'}), 404




@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'message': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename_ext = get_file_extension(file.filename)
        filename = generate_random_filename(filename_ext)
        
        print("Debug-1")
        s3_directory_loc = f'files/{filename}'
        try:
            # Upload file to S3
            s3_client.upload_fileobj(
                file,
                S3_BUCKET,
                s3_directory_loc
            )
            
            print("Debug-2")
            # Generate file URL
            
            
            file_url = os.path.join(S3_DOMAIN, filename)
            print("file_url",file_url)
            # Save record in database
            # file_record = FileRecord(filename=filename, url=file_url)
            # db.session.add(file_record)
            # db.session.commit()

            return jsonify({'url': file_url}), 201
        except Exception as e:
            print(e)
            return jsonify({'message': f'Error uploading file: {str(e)}'}), 500

    return jsonify({'message': 'Invalid file type'}), 400



@app.route('/',methods=['GET','POST'])
def index():
    if request.method=='POST':
        content = request.form['editordata']
        if not content:
            return jsonify({'message': 'Content is required!'}), 400
        attachments = request.files.getlist('attachments')
        attachment_paths = []
        print("content",content)
        print("attachments",attachments)
        
        for file in attachments:
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                attachment_paths.append(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        attachment_paths = ','.join(attachment_paths)
        new_content = Content(content=content, attachments=attachment_paths)
        db.session.add(new_content)
        db.session.commit()

    all_content = Content.query.order_by(desc(Content.id)).all()

    return render_template('index.html',content=all_content)


# Initialize the database
with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
