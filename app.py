from flask import Flask, render_template, request, jsonify
import boto3
import re
import os
import tempfile
import shutil
import subprocess
from datetime import datetime

<<<<<<< HEAD

# AWS Credentials + Region – loaded safely from environment variables
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN     = os.getenv("AWS_SESSION_TOKEN")      # only needed for temporary creds
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")  # default region if not set
# Now boto3 will automatically pick up your temp credentials!
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Initialize Flask app
=======
>>>>>>> mohamed-fix
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
    """Get the current status of the pipeline execution"""
    try:
        # Get pipeline state
        response = codepipeline.get_pipeline_execution(
            pipelineName=PIPELINE_NAME,
            pipelineExecutionId=execution_id
        )
        
        overall_status = response['pipelineExecution']['status']
        
        # Get detailed stage states
        state_response = codepipeline.get_pipeline_state(name=PIPELINE_NAME)
        
        stages = []
        for stage in state_response['stageStates']:
            stage_name = stage['stageName']
            
            # Get latest action state
            if 'latestExecution' in stage:
                status = stage['latestExecution']['status']
            else:
                status = 'Pending'
            
            # Get action details if available
            action_status = 'Pending'
            if 'actionStates' in stage and len(stage['actionStates']) > 0:
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
        return {
            'success': False,
            'error': str(e)
        }


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/deploy', methods=['POST'])
def deploy():
    try:
        data = request.get_json()
        github_url = data.get('github_url', '').strip()
<<<<<<< HEAD
        
        if not github_url:
            return jsonify({'success': False, 'error': 'Please provide a GitHub URL'}), 400
        
        if not validate_github_url(github_url):
            return jsonify({'success': False, 'error': 'Invalid GitHub URL format'}), 400
        
        subdomain = generate_subdomain()
        
        # This is the line that triggers everything
        trigger_pipeline(github_url, subdomain)
        
=======

        if not github_url or not validate_github_url(github_url):
            return jsonify({'success': False, 'error': 'Invalid GitHub URL'}), 400

        subdomain = generate_subdomain()
        print(f"Starting deployment for {github_url} → {subdomain}")

        result = trigger_pipeline(github_url, subdomain)

>>>>>>> mohamed-fix
        return jsonify({
            'success': True,
            'message': 'Deployment started successfully!',
            'subdomain': subdomain,
            'execution_id': result['execution_id']
        })
<<<<<<< HEAD
        
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
=======

    except Exception as e:
        return jsonify({'success': False, 'error': f"Failed: {str(e)}"}), 500


@app.route('/status/<execution_id>', methods=['GET'])
def check_status(execution_id):
    """Endpoint to check pipeline status"""
    result = get_pipeline_status(execution_id)
    return jsonify(result)

>>>>>>> mohamed-fix

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
    print("=" * 60)
    print("DEPLOYMENT PORTAL IS NOW LIVE")
    print(f"Bucket → {S3_BUCKET_NAME}")
    print(f"Pipeline → {PIPELINE_NAME}")
    print(f"Go to: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)