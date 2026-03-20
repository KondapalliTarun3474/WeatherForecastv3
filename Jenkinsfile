// Define global variables to hold deployment decisions
// This avoids scoping issues with 'env' variables inside 'when' blocks
def AUTH_CHANGED = false
def INFERENCE_CHANGED = false
def FRONTEND_CHANGED = false
def MLOPS_CHANGED = false
def ansibleTagsString = ""

pipeline {
    agent any

    environment {
        // Credentials ID as configured in Jenkins
        DOCKER_CREDENTIALS_ID = 'docker-credentials'
        // DOCKER_USER = 'kondapallitarun3474' // Removed: Provided by Vault Credentials
        
        // Dynamic Image Tag
        DOCKER_Tag = "v${env.BUILD_NUMBER}"

        // Set Kubeconfig explicitly for kubectl commands
        KUBECONFIG = "/home/tarun-3474/.kube/config"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }



        stage('Detect Changes') {
            steps {
                script {
                    def tagsList = []
                    def gitDiff = ""

                    // Print changes for visibility
                    try {
                        gitDiff = sh(script: 'git diff --name-only HEAD~1 HEAD', returnStdout: true).trim()
                        echo "Changed files:\n${gitDiff}"
                    } catch (Exception e) {
                        echo "Listing changes failed (first run?), proceeding with detection..."
                        // If git diff fails (e.g. first run), assume all changed
                        AUTH_CHANGED = true
                        INFERENCE_CHANGED = true
                        FRONTEND_CHANGED = true
                        MLOPS_CHANGED = true
                    }

                    // Helper to check changes via shell (robust against string formatting issues)
                    // If git diff fails (e.g. first run), we default to 'true' (deploy match)
                    def checkChange = { pattern ->
                        if (gitDiff.isEmpty()) return true // Assume changed if git diff failed
                        return gitDiff.contains(pattern)
                    }

                    if (checkChange('mlops-llm4ts/model-service/auth-service/')) {
                        AUTH_CHANGED = true
                        if (!tagsList.contains('auth')) tagsList.add('auth')
                    }
                    if (checkChange('mlops-llm4ts/model-service/inference-service/')) {
                        INFERENCE_CHANGED = true
                        if (!tagsList.contains('inference')) tagsList.add('inference')
                    }
                    if (checkChange('frontend-new/')) {
                        FRONTEND_CHANGED = true
                        if (!tagsList.contains('frontend')) tagsList.add('frontend')
                    }
                    if (checkChange('MLOps-automation-service/')) {
                        MLOPS_CHANGED = true
                        if (!tagsList.contains('retrainer')) tagsList.add('retrainer')
                    }
                    
                    ansibleTagsString = tagsList.join(',')
                    
                    if (AUTH_CHANGED || INFERENCE_CHANGED || FRONTEND_CHANGED || MLOPS_CHANGED) {
                        // This variable is no longer needed as we use the individual _CHANGED flags
                        // but keeping it for the ansible stage's 'when' condition for now.
                        // The ansible stage's 'when' condition should ideally check if ansibleTagsString is not empty.
                    }
                    
                    echo "Deploy Decisions -> Auth: ${AUTH_CHANGED}, Inference: ${INFERENCE_CHANGED}, Frontend: ${FRONTEND_CHANGED}, MLOps: ${MLOPS_CHANGED}"
                    echo "Ansible Tags: ${ansibleTagsString}"
                }
            }
        }

        stage('Test Auth') {
            when { expression { return AUTH_CHANGED } }
            steps {
                echo "Running Unit Tests for Auth Service..."
                script {
                    sh "pip install -r mlops-llm4ts/model-service/auth-service/requirements_auth.txt"
                    sh "python3 -m unittest mlops-llm4ts/model-service/auth-service/test_auth.py"
                }
            }
        }

        stage('Test Inference') {
            when { expression { return INFERENCE_CHANGED } }
            steps {
                echo "Running Unit Tests for Inference Service..."
                script {
                    // Inference requirements might be needed if they differ
                    sh "pip install -r mlops-llm4ts/model-service/inference-service/requirements_param.txt"
                    sh "python3 -m unittest mlops-llm4ts/model-service/inference-service/test_inference.py"
                }
            }
        }

        stage('Test Frontend') {
            when { expression { return FRONTEND_CHANGED } }
            steps {
                echo "Running Smoke Tests for Frontend..."
                script {
                    // Simple python validation since node might not be available or slow to install
                    sh "python3 frontend-new/test_frontend.py"
                }
            }
        }

        stage('Test MLOps') {
            when { expression { return MLOPS_CHANGED } }
            steps {
                echo "Running Component Tests for MLOps..."
                script {
                    sh "pip install -r MLOps-automation-service/requirements.txt"
                    sh "python3 -m unittest MLOps-automation-service/test_mlops.py"
                }
            }
        }

        stage('Build & Push Auth') {
            when { expression { return AUTH_CHANGED } }
            steps {
                withCredentials([usernamePassword(
                    credentialsId: DOCKER_CREDENTIALS_ID,
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh """
                        echo \$DOCKER_PASS | docker login -u \$DOCKER_USER --password-stdin
                        docker build -t \${DOCKER_USER}/weather-auth:\${DOCKER_Tag} -f mlops-llm4ts/model-service/auth-service/Dockerfile.auth mlops-llm4ts/model-service/auth-service/
                        docker push \${DOCKER_USER}/weather-auth:\${DOCKER_Tag}
                    """
                }
            }
        }

        stage('Build & Push Inference') {
            when { expression { return INFERENCE_CHANGED } }
            steps {
                withCredentials([usernamePassword(
                    credentialsId: DOCKER_CREDENTIALS_ID,
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh """
                        echo \$DOCKER_PASS | docker login -u \$DOCKER_USER --password-stdin
                        docker build -t \${DOCKER_USER}/weather-inference:\${DOCKER_Tag} -f mlops-llm4ts/model-service/inference-service/Dockerfile.param mlops-llm4ts/model-service/inference-service/
                        docker push \${DOCKER_USER}/weather-inference:\${DOCKER_Tag}
                    """
                }
            }
        }

        stage('Build & Push Frontend') {
            when { expression { return FRONTEND_CHANGED } }
            steps {
                withCredentials([usernamePassword(
                    credentialsId: DOCKER_CREDENTIALS_ID,
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh """
                        echo \$DOCKER_PASS | docker login -u \$DOCKER_USER --password-stdin
                        docker build -t \${DOCKER_USER}/weather-frontend:\${DOCKER_Tag} frontend-new/
                        docker push \${DOCKER_USER}/weather-frontend:\${DOCKER_Tag}
                    """
                }
            }
        }
        
        stage('Build and Push MLOps Retrainer') {
            when {
                expression { return MLOPS_CHANGED }
            }
            steps {
                withCredentials([usernamePassword(
                    credentialsId: DOCKER_CREDENTIALS_ID,
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh """
                        echo \$DOCKER_PASS | docker login -u \$DOCKER_USER --password-stdin
                        docker build -t \${DOCKER_USER}/weather-retrainer:\${DOCKER_Tag} -f MLOps-automation-service/Dockerfile.retrainer MLOps-automation-service/
                        docker push \${DOCKER_USER}/weather-retrainer:\${DOCKER_Tag}
                    """
                }
            }
        }
        
        stage('Deploy with Ansible') {
            when { expression { return ansibleTagsString != '' } } // Deploy only if there are changes to deploy
            steps {
                // Execute Ansible Playbook from the root
                // We pass dynamic tags so Ansible deploys the version we just built
                sh "ansible-playbook ansible/deploy.yml --tags '${ansibleTagsString}' -e 'auth_tag=${DOCKER_Tag} inference_tag=${DOCKER_Tag} frontend_tag=${DOCKER_Tag} retrainer_tag=${DOCKER_Tag}'"
            }
        }
    }
}
