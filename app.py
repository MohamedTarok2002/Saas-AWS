from flask import Flask, render_template, request, jsonify
import boto3
import re
import os
import tempfile
import shutil
import subprocess
import secrets
from datetime import datetime

app = Flask(__name__)

# ========================================
# CONFIGURATION
# ========================================
PIPELINE_NAME = 'UserDeploymentPipeline'
EC2_PUBLIC_IP = "52.90.98.13"
S3_BUCKET_NAME = "devops-deploy-artifacts-fr-saas"
AWS_REGION = 'us-east-1'

# AWS clients
s3 = boto3.client('s3', region_name=AWS_REGION)
codepipeline = boto3.client('codepipeline', region_name=AWS_REGION)

# Store deployments (in-memory for now, database later)
deployments = {}


def validate_github_url(url):
    pattern = r'^https://github\.com/[\w-]+/[\w.-]+/?$'
    return re.match(pattern, url.strip()) is not None


def generate_deployment_id():
    """Generate unique deployment ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = secrets.token_hex(4)
    return f"deploy-{timestamp}-{random_suffix}"


def generate_subdomain(github_url):
    """Generate subdomain from repo name"""
    repo_name = github_url.rstrip('/').split('/')[-1]
    clean_name = re.sub(r'[^a-zA-Z0-9-]', '-', repo_name).lower()
    suffix = secrets.token_hex(3)
    return f"{clean_name}-{suffix}"


def trigger_pipeline(github_url, deployment_id):
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

        # ============================================
        # NEW: Upload to unique path per deployment
        # ============================================
        s3_key = f"deployments/{deployment_id}/source.zip"
        
        print(f"Uploading to S3: {s3_key}")
        with open(zip_file_path, 'rb') as f:
            s3.upload_fileobj(f, S3_BUCKET_NAME, s3_key)
        print(f"Uploaded to s3://{S3_BUCKET_NAME}/{s3_key}")

        print("Starting CodePipeline...")
        response = codepipeline.start_pipeline_execution(name=PIPELINE_NAME)
        execution_id = response['pipelineExecutionId']
        print(f"Pipeline started: {execution_id}")

        return {
            'success': True, 
            'execution_id': execution_id,
            's3_key': s3_key
        }

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

        # Generate unique IDs
        deployment_id = generate_deployment_id()
        subdomain = generate_subdomain(github_url)
        
        print(f"=" * 50)
        print(f"NEW DEPLOYMENT: {deployment_id}")
        print(f"GitHub URL: {github_url}")
        print(f"Subdomain: {subdomain}")
        print(f"=" * 50)

        result = trigger_pipeline(github_url, deployment_id)

        # Store deployment info
        deployments[deployment_id] = {
            'deployment_id': deployment_id,
            'subdomain': subdomain,
            'github_url': github_url,
            's3_key': result['s3_key'],
            'execution_id': result['execution_id'],
            'status': 'deploying',
            'created_at': datetime.now().isoformat()
        }

        return jsonify({
            'success': True,
            'message': 'Deployment started successfully!',
            'deployment_id': deployment_id,
            'subdomain': subdomain,
            'execution_id': result['execution_id'],
            's3_path': result['s3_key']
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f"Failed: {str(e)}"}), 500


@app.route('/status/<execution_id>', methods=['GET'])
def check_status(execution_id):
    result = get_pipeline_status(execution_id)
    return jsonify(result)


@app.route('/deployments', methods=['GET'])
def list_deployments():
    """List all deployments"""
    return jsonify({
        'success': True,
        'count': len(deployments),
        'deployments': list(deployments.values())
    })


@app.route('/deployments/<deployment_id>', methods=['GET'])
def get_deployment(deployment_id):
    """Get single deployment info"""
    if deployment_id in deployments:
        return jsonify({'success': True, 'deployment': deployments[deployment_id]})
    return jsonify({'success': False, 'error': 'Deployment not found'}), 404


if __name__ == '__main__':
    print("=" * 60)
    print("DEPLOYFAST - MULTI-USER DEPLOYMENT SERVICE")
    print("=" * 60)
    print(f"Bucket    → {S3_BUCKET_NAME}")
    print(f"Pipeline  → {PIPELINE_NAME}")
    print(f"S3 Path   → deployments/<deployment_id>/source.zip")
    print("=" * 60)
    print(f"Go to: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)

'''

```

---

## **What Changed**

| Before | After |
|--------|-------|
| `source.zip` | `deployments/{deployment_id}/source.zip` |
| `generate_subdomain()` | `generate_deployment_id()` + `generate_subdomain()` |
| No tracking | `deployments` dict stores all info |
| No list endpoint | `/deployments` shows all deployments |

---

## **New S3 Structure**
```
s3://devops-deploy-artifacts-fr-saas/
│
└── deployments/
    ├── deploy-20241130120000-a1b2c3d4/
    │   └── source.zip
    │
    ├── deploy-20241130120500-e5f6g7h8/
    │   └── source.zip
    │
    └── deploy-20241130121000-i9j0k1l2/
        └── source.zip
'''