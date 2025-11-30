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
# CONFIGURATION
# ========================================
PIPELINE_NAME = 'UserDeploymentPipeline'
EC2_PUBLIC_IP = "52.90.98.13"
S3_BUCKET_NAME = "devops-deploy-artifacts-fr-saas"
AWS_REGION = 'us-east-1'

# AWS clients – boto3 automatically uses your credentials from environment or AWS config
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


def get_pipeline_status(execution_id):
    try:
        response = codepipeline.get_pipeline_execution(
            pipelineName=PIPELINE_NAME,
            pipelineExecutionId=execution_id
        )
        overall_status = response['pipelineExecution']['status']

        state_response = codepipeline.get_pipeline_state(name=PIPELINE_NAME)
        stages = []

        for stage in state_response['stageStates']:
            stage_name = stage['stageName']
            status = stage['latestExecution']['status'] if 'latestExecution' in stage else 'Pending'
            action_status = 'Pending'
            if 'actionStates' in stage and stage['actionStates']:
                action = stage['actionStates'][0]
                if 'latestExecution' in action:
                    action_status = action['latestExecution']['status']

            stages.append({
                'name': stage_name,
                'status': status,
                'action_status': action_status
            })

        return {
            'success': True,
            'overall_status': overall_status,
            'stages': stages,
            'deployment_url': f"http://{EC2_PUBLIC_IP}" if overall_status == 'Succeeded' else None
        }

    except Exception as e:
        print(f"Error getting pipeline status: {e}")
        return {'success': False, 'error': str(e)}


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
            'execution_id': result['execution_id']
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f"Failed: {str(e)}"}), 500


@app.route('/status/<execution_id>', methods=['GET'])
def check_status(execution_id):
    result = get_pipeline_status(execution_id)
    return jsonify(result)


if __name__ == '__main__':
    print("=" * 60)
    print("DEPLOYMENT PORTAL IS NOW LIVE")
    print(f"Bucket → {S3_BUCKET_NAME}")
    print(f"Pipeline → {PIPELINE_NAME}")
    print(f"Go to: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)