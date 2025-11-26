from flask import Flask, render_template, request, jsonify
import boto3
import re
import os
import tempfile
import shutil
import subprocess
from datetime import datetime

app = Flask(__name__)

# ========================================
# CONFIGURATION — FINAL CORRECT VERSION
# ========================================
PIPELINE_NAME = 'UserDeploymentPipeline'
EC2_PUBLIC_IP = "52.90.98.13"
S3_BUCKET_NAME = "devops-deploy-artifacts-fr-saas"   # ← NO SPACE AT THE END!!!

AWS_REGION = 'us-east-1'

# AWS clients
s3 = boto3.client('s3', region_name=AWS_REGION)
codepipeline = boto3.client('codepipeline', region_name=AWS_REGION)


def validate_github_url(url):
    pattern = r'^https://github\.com/[\w-]+/[\w.-]+/?$'
    return re.match(pattern, url.strip()) is not None


def generate_subdomain():
    return f"deploy-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def trigger_pipeline(github_url, subdomain):
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        repo_path = os.path.join(temp_dir, "repo")
        zip_base_path = os.path.join(temp_dir, "source")

        print(f"Cloning {github_url} ...")
        subprocess.run(
            ["git", "clone", "--depth", "1", github_url, repo_path],
            check=True, capture_output=True, timeout=300
        )
        print("Git clone successful!")

        # FIXED: use correct variable name
        zip_file_path = shutil.make_archive(zip_base_path, 'zip', repo_path)
        print(f"Zip created: {zip_file_path}")

        print("Uploading to S3...")
        with open(zip_file_path, 'rb') as f:
            s3.upload_fileobj(f, S3_BUCKET_NAME, 'source.zip')
        print(f"Uploaded to s3://{S3_BUCKET_NAME}/source.zip")

        print("Starting CodePipeline...")
        response = codepipeline.start_pipeline_execution(name=PIPELINE_NAME)
        execution_id = response['pipelineExecutionId']
        print(f"Pipeline started: {execution_id}")

        return {'success': True, 'execution_id': execution_id}

    except Exception as e:
        print(f"Deployment failed: {e}")
        raise
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/deploy', methods=['POST'])
def deploy():
    try:
        data = request.get_json()
        github_url = data.get('github_url', '').strip()

        if not github_url or not validate_github_url(github_url):
            return jsonify({'success': False, 'error': 'Invalid GitHub URL'}), 400

        subdomain = generate_subdomain()
        print(f"Starting deployment for {github_url} → {subdomain}")

        result = trigger_pipeline(github_url, subdomain)

        return jsonify({
            'success': True,
            'message': 'Deployment started successfully!',
            'subdomain': subdomain,
            'deployment_url': f"http://{EC2_PUBLIC_IP}",
            'execution_id': result['execution_id']
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f"Failed: {str(e)}"}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("DEPLOYMENT PORTAL IS NOW LIVE AND UNBREAKABLE")
    print(f"Bucket → {S3_BUCKET_NAME}")
    print(f"Pipeline → {PIPELINE_NAME}")
    print(f"Go to: http://{EC2_PUBLIC_IP}:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)