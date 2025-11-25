from flask import Flask, render_template, request, jsonify
import boto3
import re
import os
from datetime import datetime


# AWS Credentials + Region – loaded safely from environment variables
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN     = os.getenv("AWS_SESSION_TOKEN")      # only needed for temporary creds
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")  # default region if not set
# Now boto3 will automatically pick up your temp credentials!
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Initialize Flask app
app = Flask(__name__)

# AWS Configuration (we'll set these up later)
AWS_REGION = 'us-east-1'  # Change to your preferred region
PIPELINE_NAME = 'UserDeploymentPipeline'
EC2_PUBLIC_IP ="52.90.98.13"
# Initialize AWS clients (we'll configure credentials later)
try:
    codepipeline = boto3.client('codepipeline', region_name=AWS_REGION)
    route53 = boto3.client('route53', region_name=AWS_REGION)
except Exception as e:
    print(f"AWS clients not configured yet: {e}")

def validate_github_url(url):
    """
    Validate if the URL is a proper GitHub repository URL
    """
    pattern = r'^https://github\.com/[\w-]+/[\w.-]+/?$'
    return re.match(pattern, url) is not None

def generate_subdomain():
    """
    Generate a unique subdomain for the deployment
    """
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"deploy-{timestamp}"

@app.route('/')
def home():
    """
    Home page - shows the deployment form
    """
    return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy():
    """
    Handle deployment request
    """
    try:
        data = request.get_json()
        github_url = data.get('github_url', '').strip()
        
        if not github_url:
            return jsonify({'success': False, 'error': 'Please provide a GitHub URL'}), 400
        
        if not validate_github_url(github_url):
            return jsonify({'success': False, 'error': 'Invalid GitHub URL format'}), 400
        
        subdomain = generate_subdomain()
        
        # This is the line that triggers everything
        trigger_pipeline(github_url, subdomain)
        
        return jsonify({
            'success': True,
            'message': 'Deployment started successfully!',
            'subdomain': subdomain,
            'deployment_url': f"http://{EC2_PUBLIC_IP}",
            'status': 'In Progress'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f"Deployment failed: {str(e)}"
        }), 500

@app.route('/status/<deployment_id>')
def check_status(deployment_id):
    """
    Check deployment status
    """
    # TODO: Implement status checking with AWS
    return jsonify({
        'deployment_id': deployment_id,
        'status': 'Building',
        'progress': 50
    })

def trigger_pipeline(github_url, subdomain):
    import subprocess
    import tempfile
    import shutil
    import os

    try:
        # Use REAL temp folder that Windows can't mess with
        temp_dir = tempfile.mkdtemp(prefix="deploy_")
        repo_path = os.path.join(temp_dir, "repo")
        zip_path = os.path.join(temp_dir, "source.zip")

        print("Cloning repo...")
        result = subprocess.run(
            ['git', 'clone', '--depth', '1', github_url, repo_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise Exception(f"Git clone failed: {result.stderr}")

        # Inject buildspec.yml
        with open(os.path.join(repo_path, "buildspec.yml"), "w") as f:
            f.write("""version: 0.2
phases:
  build:
    commands:
      - echo "Static site - nothing to build"
artifacts:
  files:
    - '**/*'
  base-directory: repo
""")

        # Inject appspec.yml
        with open(os.path.join(repo_path, "appspec.yml"), "w") as f:
            f.write("""version: 0.0
os: linux
files:
  - source: /
    destination: /usr/share/nginx/html/
permissions:
  - object: /
    pattern: "**"
    owner: nginx
    group: nginx
""")

        # Zip from inside the temp folder
        shutil.make_archive(zip_path.replace(".zip", ""), 'zip', temp_dir, "repo")

        # Upload
        session = boto3.Session()
        s3 = session.client('s3')
        with open(zip_path, "rb") as f:
            s3.upload_fileobj(f, 'devops-deploy-artifacts-fr-saas', "source.zip")

        print("SUCCESS → source.zip uploaded! Pipeline running...")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {'success': True}

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True) if 'temp_dir' in locals() else None
        raise Exception(f"Failed: {str(e)}")
    
if __name__ == '__main__':
    # Run the Flask app in development mode
    app.run(debug=True, host='0.0.0.0', port=5000)