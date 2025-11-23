from flask import Flask, render_template, request, jsonify
import boto3
import re
import os
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)

# AWS Configuration (we'll set these up later)
AWS_REGION = 'us-east-1'  # Change to your preferred region
PIPELINE_NAME = 'UserDeploymentPipeline'

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
        # Get GitHub URL from the form
        data = request.get_json()
        github_url = data.get('github_url', '').strip()
        
        # Validate the URL
        if not github_url:
            return jsonify({
                'success': False,
                'error': 'Please provide a GitHub URL'
            }), 400
        
        if not validate_github_url(github_url):
            return jsonify({
                'success': False,
                'error': 'Invalid GitHub URL format. Use: https://github.com/username/repository'
            }), 400
        
        # Generate unique subdomain
        subdomain = generate_subdomain()
        
        # TODO: Trigger AWS CodePipeline (we'll implement this after AWS setup)
        # pipeline_response = trigger_pipeline(github_url, subdomain)
        
        # For now, return success with placeholder
        return jsonify({
            'success': True,
            'message': 'Deployment started!',
            'subdomain': subdomain,
            'deployment_url': f"http://{subdomain}.yourservice.com",
            'status': 'In Progress'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
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
    """
    Trigger AWS CodePipeline with the GitHub URL
    (We'll implement this after AWS setup)
    """
    try:
        response = codepipeline.start_pipeline_execution(
            name=PIPELINE_NAME,
            variables=[
                {
                    'name': 'GITHUB_URL',
                    'value': github_url
                },
                {
                    'name': 'SUBDOMAIN',
                    'value': subdomain
                }
            ]
        )
        return response
    except Exception as e:
        raise Exception(f"Failed to trigger pipeline: {str(e)}")

if __name__ == '__main__':
    # Run the Flask app in development mode
    app.run(debug=True, host='0.0.0.0', port=5000)