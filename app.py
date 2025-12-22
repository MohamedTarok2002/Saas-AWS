from flask import Flask, render_template, request, jsonify
import boto3
import re
import os
import tempfile
import shutil
import subprocess
import secrets
import time
import json
from datetime import datetime

app = Flask(__name__)

# ========================================
# CONFIGURATION - UPDATE THESE!
# ========================================
S3_BUCKET_NAME = "devops-deploy-artifacts-fr-saas"  # Your S3 bucket
AWS_REGION = 'us-east-1'  # Your region

# Your existing resources
CODEBUILD_PROJECT = 'DevOps-Deploy-CodeBuilder'  # Your CodeBuild project name

# Your new resources
LAUNCH_TEMPLATE_ID = 'lt-046e6e85369f05a3c'  # ← PUT YOUR LAUNCH TEMPLATE ID HERE!
LAMBDA_FUNCTION_NAME = 'DeployFast-Deployer'  # Lambda we just created

# ========================================
# AWS CLIENTS
# ========================================
s3 = boto3.client('s3', region_name=AWS_REGION)
ec2 = boto3.client('ec2', region_name=AWS_REGION)
codebuild = boto3.client('codebuild', region_name=AWS_REGION)
lambda_client = boto3.client('lambda', region_name=AWS_REGION)

# ========================================
# IN-MEMORY STORAGE (Database later)
# ========================================
deployments = {}


# ========================================
# HELPER FUNCTIONS
# ========================================

def validate_github_url(url):
    """
    Check if URL is a valid GitHub repository URL.
    
    Valid examples:
    - https://github.com/user/repo
    - https://github.com/user/repo/
    
    Invalid examples:
    - http://github.com/user/repo (no https)
    - https://gitlab.com/user/repo (not github)
    """
    pattern = r'^https://github\.com/[\w-]+/[\w.-]+/?$'
    return re.match(pattern, url.strip()) is not None


def generate_deployment_id():
    """
    Generate unique deployment ID.
    
    Format: deploy-{timestamp}-{random}
    Example: deploy-20241130143045-a1b2c3d4
    
    This ID is used for:
    - S3 path (deployments/{id}/source.zip)
    - EC2 tag (DeploymentId={id})
    - Tracking in our system
    """
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = secrets.token_hex(4)
    return f"deploy-{timestamp}-{random_suffix}"


def generate_subdomain(github_url):
    """
    Generate subdomain from repository name.
    
    Example:
    - Input: https://github.com/user/My-Cool-App
    - Output: my-cool-app-a1b2c3
    """
    repo_name = github_url.rstrip('/').split('/')[-1]
    clean_name = re.sub(r'[^a-zA-Z0-9-]', '-', repo_name).lower()
    suffix = secrets.token_hex(3)
    return f"{clean_name}-{suffix}"


# ========================================
# STEP 1: CREATE EC2 FROM LAUNCH TEMPLATE
# ========================================

def create_ec2_instance(deployment_id):
    """
    Create a new EC2 instance from Launch Template.
    
    IMPORTANT TAGS:
    - Name: Human-readable name in AWS Console
    - DeploymentId: Unique ID for this deployment (CodeDeploy targets this!)
    - ManagedBy: Group tag (for organizing/filtering)
    
    The Launch Template already has:
    - AMI (Amazon Linux)
    - Instance type (t2.micro)
    - Security group
    - User Data script (installs nginx + CodeDeploy agent)
    """
    
    print(f"[{deployment_id}] ========================================")
    print(f"[{deployment_id}] STEP 1: Creating EC2 instance")
    print(f"[{deployment_id}] ========================================")
    
    # Create EC2 from Launch Template
    response = ec2.run_instances(
        LaunchTemplate={
            'LaunchTemplateId': LAUNCH_TEMPLATE_ID,
            'Version': '$Latest'
        },
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[{
            'ResourceType': 'instance',
            'Tags': [
                {'Key': 'Name', 'Value': f'DeployFast-{deployment_id}'},
                {'Key': 'DeploymentId', 'Value': deployment_id},  # CodeDeploy targets this!
                {'Key': 'ManagedBy', 'Value': 'DeployFast'}
            ]
        }]
    )
    
    instance_id = response['Instances'][0]['InstanceId']
    print(f"[{deployment_id}] EC2 instance created: {instance_id}")
    
    # Wait for instance to be in "running" state
    print(f"[{deployment_id}] Waiting for EC2 to start...")
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])
    print(f"[{deployment_id}] EC2 is running!")
    
    # Get the public IP address
    instance_info = ec2.describe_instances(InstanceIds=[instance_id])
    public_ip = instance_info['Reservations'][0]['Instances'][0].get('PublicIpAddress')
    print(f"[{deployment_id}] EC2 public IP: {public_ip}")
    
    # Wait for User Data script to complete
    # The script installs nginx and CodeDeploy agent
    print(f"[{deployment_id}] Waiting 90 seconds for nginx + CodeDeploy agent to install...")
    time.sleep(90)
    print(f"[{deployment_id}] EC2 should be ready now!")
    
    return {
        'instance_id': instance_id,
        'public_ip': public_ip
    }


# ========================================
# STEP 2: UPLOAD CODE TO S3
# ========================================

def upload_to_s3(github_url, deployment_id):
    """
    Clone GitHub repository and upload to S3.
    
    Process:
    1. Create temp directory
    2. Git clone the repo
    3. Zip the repo
    4. Upload to S3 at: deployments/{deployment_id}/source.zip
    5. Clean up temp directory
    
    Each deployment gets its own S3 path!
    """
    
    print(f"[{deployment_id}] ========================================")
    print(f"[{deployment_id}] STEP 2: Uploading code to S3")
    print(f"[{deployment_id}] ========================================")
    
    temp_dir = None
    try:
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        repo_path = os.path.join(temp_dir, "repo")
        zip_base_path = os.path.join(temp_dir, "source")

        # Clone repository
        print(f"[{deployment_id}] Cloning {github_url}...")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", github_url, repo_path],
            check=True,
            capture_output=True,
            timeout=300
        )
        print(f"[{deployment_id}] Clone successful!")

        # Create zip file
        print(f"[{deployment_id}] Creating zip file...")
        zip_file_path = shutil.make_archive(zip_base_path, 'zip', repo_path)
        print(f"[{deployment_id}] Zip created: {zip_file_path}")

        # Upload to S3 with unique path
        s3_key = f"deployments/{deployment_id}/source.zip"
        print(f"[{deployment_id}] Uploading to s3://{S3_BUCKET_NAME}/{s3_key}")
        
        with open(zip_file_path, 'rb') as f:
            s3.upload_fileobj(f, S3_BUCKET_NAME, s3_key)
        
        print(f"[{deployment_id}] Upload complete!")
        
        return s3_key

    except subprocess.CalledProcessError as e:
        print(f"[{deployment_id}] Git clone failed: {e.stderr.decode()}")
        raise Exception(f"Failed to clone repository: {e.stderr.decode()}")
        
    finally:
        # Always clean up temp directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


# ========================================
# STEP 3: RUN CODEBUILD
# ========================================

def run_codebuild(deployment_id, s3_source_key):
    """
    Start CodeBuild with the user's source code.
    
    Overrides:
    - source: User's S3 path (not the default)
    - artifacts: Output to user's S3 path
    - environment variables: Pass DEPLOYMENT_ID to buildspec
    
    CodeBuild will:
    1. Download source from S3
    2. Install dependencies (npm install, pip install, etc.)
    3. Build the project (npm run build, etc.)
    4. Create appspec.yml and scripts
    5. Upload output to S3
    """
    
    print(f"[{deployment_id}] ========================================")
    print(f"[{deployment_id}] STEP 3: Running CodeBuild")
    print(f"[{deployment_id}] ========================================")
    
    print(f"[{deployment_id}] Starting CodeBuild project: {CODEBUILD_PROJECT}")
    print(f"[{deployment_id}] Source: s3://{S3_BUCKET_NAME}/{s3_source_key}")
    
    response = codebuild.start_build(
        projectName=CODEBUILD_PROJECT,
        
        # Use THIS user's source code
        sourceTypeOverride='S3',
        sourceLocationOverride=f"{S3_BUCKET_NAME}/{s3_source_key}",
        
        # Output to THIS user's path
        artifactsOverride={
            'type': 'S3',
            'location': S3_BUCKET_NAME,
            'path': f"deployments/{deployment_id}",
            'name': 'output',
            'packaging': 'ZIP'
        },
        
        # Pass deployment_id to buildspec
        environmentVariablesOverride=[
            {
                'name': 'DEPLOYMENT_ID',
                'value': deployment_id,
                'type': 'PLAINTEXT'
            }
        ]
    )
    
    build_id = response['build']['id']
    print(f"[{deployment_id}] CodeBuild started: {build_id}")
    
    return build_id


def wait_for_codebuild(deployment_id, build_id, timeout=600):
    """
    Wait for CodeBuild to complete.
    
    Polls every 15 seconds until:
    - SUCCEEDED: Build completed successfully
    - FAILED/FAULT/STOPPED/TIMED_OUT: Build failed
    - Timeout: We've waited too long
    """
    
    print(f"[{deployment_id}] Waiting for CodeBuild to complete...")
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Get build status
        response = codebuild.batch_get_builds(ids=[build_id])
        build = response['builds'][0]
        status = build['buildStatus']
        phase = build.get('currentPhase', 'UNKNOWN')
        
        print(f"[{deployment_id}] CodeBuild status: {status} (phase: {phase})")
        
        if status == 'SUCCEEDED':
            print(f"[{deployment_id}] CodeBuild completed successfully!")
            return True
            
        elif status in ['FAILED', 'FAULT', 'STOPPED', 'TIMED_OUT']:
            # Get error details
            phases = build.get('phases', [])
            for p in phases:
                if p.get('phaseStatus') == 'FAILED':
                    contexts = p.get('contexts', [])
                    for ctx in contexts:
                        print(f"[{deployment_id}] Error: {ctx.get('message', 'Unknown error')}")
            return False
        
        # Still in progress, wait and check again
        time.sleep(15)
    
    print(f"[{deployment_id}] CodeBuild timed out!")
    return False


# ========================================
# STEP 4: INVOKE LAMBDA TO RUN CODEDEPLOY
# ========================================

def invoke_lambda(deployment_id):
    """
    Invoke Lambda function to run CodeDeploy.
    
    Lambda will:
    1. Call CodeDeploy with specific tag filter
    2. Wait for CodeDeploy to complete
    3. Return success/failure
    
    Why Lambda instead of calling CodeDeploy directly?
    - Separation of concerns
    - Can be used with CodePipeline too
    - Easier to add retry logic later
    """
    
    print(f"[{deployment_id}] ========================================")
    print(f"[{deployment_id}] STEP 4: Invoking Lambda for CodeDeploy")
    print(f"[{deployment_id}] ========================================")
    
    # Prepare payload for Lambda
    payload = {
        'deployment_id': deployment_id,
        's3_bucket': S3_BUCKET_NAME,
        's3_key': f"deployments/{deployment_id}/output"
    }
    
    print(f"[{deployment_id}] Invoking Lambda: {LAMBDA_FUNCTION_NAME}")
    print(f"[{deployment_id}] Payload: {json.dumps(payload)}")
    
    # Invoke Lambda and wait for response
    response = lambda_client.invoke(
        FunctionName="Lambdafr-ec2",
        InvocationType='RequestResponse',  # Wait for response (synchronous)
        Payload=json.dumps(payload)
    )
    
    # Parse response
    response_payload = json.loads(response['Payload'].read().decode())
    print(f"[{deployment_id}] Lambda response: {json.dumps(response_payload, indent=2)}")
    
    # Check if successful
    status_code = response_payload.get('statusCode', 500)
    
    if status_code == 200:
        print(f"[{deployment_id}] Lambda completed successfully!")
        return True
    else:
        body = response_payload.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)
        error = body.get('error', 'Unknown error')
        print(f"[{deployment_id}] Lambda failed: {error}")
        return False


# ========================================
# TERMINATE EC2 (For delete deployment)
# ========================================

def terminate_ec2(instance_id):
    """
    Terminate an EC2 instance.
    
    Called when user deletes their deployment.
    This stops billing for that instance!
    """
    
    print(f"Terminating EC2 instance: {instance_id}")
    ec2.terminate_instances(InstanceIds=[instance_id])
    print(f"EC2 instance terminated!")


# ========================================
# FLASK ROUTES
# ========================================

@app.route('/')
def home():
    """Serve the home page"""
    return render_template('index.html')


@app.route('/deploy', methods=['POST'])
def deploy():
    """
    Main deployment endpoint.
    
    Flow:
    1. Validate GitHub URL
    2. Generate deployment_id
    3. Create EC2 from Launch Template
    4. Upload code to S3
    5. Run CodeBuild
    6. Invoke Lambda → CodeDeploy
    7. Return URL to user
    """
    
    deployment_id = None
    
    try:
        # Get GitHub URL from request
        data = request.get_json()
        github_url = data.get('github_url', '').strip()

        # Validate URL
        if not github_url:
            return jsonify({'success': False, 'error': 'GitHub URL is required'}), 400
            
        if not validate_github_url(github_url):
            return jsonify({'success': False, 'error': 'Invalid GitHub URL. Must be https://github.com/user/repo'}), 400

        # Generate unique IDs
        deployment_id = generate_deployment_id()
        subdomain = generate_subdomain(github_url)
        
        print("")
        print("=" * 70)
        print(f"NEW DEPLOYMENT: {deployment_id}")
        print(f"GitHub URL: {github_url}")
        print(f"Subdomain: {subdomain}")
        print("=" * 70)
        print("")

        # Initialize deployment record
        deployments[deployment_id] = {
            'deployment_id': deployment_id,
            'subdomain': subdomain,
            'github_url': github_url,
            'status': 'starting',
            'created_at': datetime.now().isoformat()
        }

        # ============================================
        # STEP 1: Create EC2 from Launch Template
        # ============================================
        deployments[deployment_id]['status'] = 'creating_ec2'
        ec2_info = create_ec2_instance(deployment_id)
        deployments[deployment_id]['ec2_instance_id'] = ec2_info['instance_id']
        deployments[deployment_id]['ec2_public_ip'] = ec2_info['public_ip']

        # ============================================
        # STEP 2: Upload code to S3
        # ============================================
        deployments[deployment_id]['status'] = 'uploading'
        s3_key = upload_to_s3(github_url, deployment_id)
        deployments[deployment_id]['s3_key'] = s3_key

        # ============================================
        # STEP 3: Run CodeBuild
        # ============================================
        deployments[deployment_id]['status'] = 'building'
        build_id = run_codebuild(deployment_id, s3_key)
        deployments[deployment_id]['build_id'] = build_id
        
        if not wait_for_codebuild(deployment_id, build_id):
            deployments[deployment_id]['status'] = 'build_failed'
            return jsonify({
                'success': False,
                'error': 'CodeBuild failed. Check AWS Console for details.',
                'deployment_id': deployment_id
            }), 500

        # ============================================
        # STEP 4: Invoke Lambda → CodeDeploy
        # ============================================
        deployments[deployment_id]['status'] = 'deploying'
        
        if not invoke_lambda(deployment_id):
            deployments[deployment_id]['status'] = 'deploy_failed'
            return jsonify({
                'success': False,
                'error': 'CodeDeploy failed. Check AWS Console for details.',
                'deployment_id': deployment_id
            }), 500

        # ============================================
        # SUCCESS!
        # ============================================
        deployments[deployment_id]['status'] = 'live'
        url = f"http://{ec2_info['public_ip']}"
        deployments[deployment_id]['url'] = url
        
        print("")
        print("=" * 70)
        print(f"DEPLOYMENT SUCCESSFUL!")
        print(f"Deployment ID: {deployment_id}")
        print(f"URL: {url}")
        print("=" * 70)
        print("")

        return jsonify({
            'success': True,
            'deployment_id': deployment_id,
            'subdomain': subdomain,
            'url': url,
            'ec2_instance_id': ec2_info['instance_id'],
            'ec2_public_ip': ec2_info['public_ip']
        })

    except Exception as e:
        print(f"[{deployment_id}] ERROR: {str(e)}")
        
        import traceback
        traceback.print_exc()
        
        if deployment_id and deployment_id in deployments:
            deployments[deployment_id]['status'] = 'failed'
            deployments[deployment_id]['error'] = str(e)
            
        return jsonify({
            'success': False,
            'error': str(e),
            'deployment_id': deployment_id
        }), 500


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
        return jsonify({
            'success': True,
            'deployment': deployments[deployment_id]
        })
    return jsonify({
        'success': False,
        'error': 'Deployment not found'
    }), 404


@app.route('/deployments/<deployment_id>', methods=['DELETE'])
def delete_deployment(deployment_id):
    """Delete deployment and terminate EC2"""
    
    if deployment_id not in deployments:
        return jsonify({
            'success': False,
            'error': 'Deployment not found'
        }), 404
    
    try:
        deployment = deployments[deployment_id]
        
        # Terminate EC2 (stops billing!)
        if 'ec2_instance_id' in deployment:
            terminate_ec2(deployment['ec2_instance_id'])
        
        # Remove from memory
        del deployments[deployment_id]
        
        return jsonify({
            'success': True,
            'message': 'Deployment deleted and EC2 terminated!'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========================================
# RUN THE APP
# ========================================

if __name__ == '__main__':
    print("")
    print("=" * 70)
    print("DEPLOYFAST - MULTI-USER DEPLOYMENT SERVICE")
    print("=" * 70)
    print(f"S3 Bucket:       {S3_BUCKET_NAME}")
    print(f"CodeBuild:       {CODEBUILD_PROJECT}")
    print(f"Lambda:          {LAMBDA_FUNCTION_NAME}")
    print(f"Launch Template: {LAUNCH_TEMPLATE_ID}")
    print("=" * 70)
    print("Open in browser: http://localhost:5000")
    print("=" * 70)
    print("")
    
    app.run(host='0.0.0.0', port=5000, debug=True)