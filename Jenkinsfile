// Jenkins declarative pipeline for the gitops-demo Java application.
//
// Flow: checkout -> Maven build and unit tests -> SonarQube analysis and
// quality gate -> Docker build and push -> update the image tag in the Helm
// values file and commit it back so ArgoCD deploys the new version.
//
// REQUIRED JENKINS SETUP (see README.md for the full walkthrough):
//   - Tools: JDK 17 and Maven 3.9 configured in Jenkins global tools.
//   - Credentials:
//       'docker-hub-credentials' - Docker Hub (or other registry) username
//           and password, type "Username with password".
//       'github-credentials'     - GitHub username and personal access token,
//           type "Username with password". Used only to push the tag update.
//   - SonarQube server configured in Jenkins with the name 'sonarqube'
//     (Manage Jenkins -> System -> SonarQube servers).
//   - Job trigger: GitHub webhook on push to the main branch.
//
// PREVENTING BUILD LOOPS (important - read this before enabling the webhook):
//   1. The "Update GitOps Manifests" stage commits the new image tag with
//      the message "[skip ci]". Every build stage below is guarded by
//      `when { not { changelog '.*\\[skip ci\\].*' } }`, so a commit that
//      only carries the tag update does not start another build.
//   2. The Jenkins job should ALSO be configured to ignore manifest-only
//      changes: in a multibranch or GitHub Organisation job, add the
//      "Polling ignores commits in certain paths" behaviour (or the
//      equivalent "Included regions" setting) with excluded regions:
//          helm/.*
//          k8s/.*
//          argocd/.*
//      so the pipeline only triggers on changes under app/ (and this
//      Jenkinsfile). If your Jenkins version has no such behaviour, the
//      [skip ci] guard in (1) is the safety net.
//   3. The manifest-update stage only touches helm/app-chart/values.yaml
//      (the image tag). It never touches app/ source code.

pipeline {
    agent any

    options {
        // The 'Build and Test' stage does an explicit `checkout scm`, so
        // skip the default checkout to avoid checking out twice.
        skipDefaultCheckout(true)
    }

    parameters {
        string(name: 'REGISTRY', defaultValue: 'docker.io',
               description: 'Container registry host, e.g. docker.io')
        string(name: 'IMAGE_NAMESPACE', defaultValue: 'vinodg',
               description: 'Registry namespace / Docker Hub username that owns the image')
        string(name: 'IMAGE_NAME', defaultValue: 'gitops-demo',
               description: 'Image name (without registry or tag)')
    }

    environment {
        // GitHub noreply address for the vinod-codes account, used only for
        // the automated tag-update commit. No real email is invented here.
        // (Full noreply address, verified from the repository's commit history.)
        GIT_COMMIT_EMAIL = '164331435+vinod-codes@users.noreply.github.com'
        GIT_COMMIT_NAME = 'Vinod G'
    }

    stages {
        stage('Build and Test') {
            when { not { changelog '.*\\[skip ci\\].*' } }
            steps {
                checkout scm
                sh 'mvn -f app/pom.xml clean test'
            }
        }

        stage('SonarQube Analysis') {
            when { not { changelog '.*\\[skip ci\\].*' } }
            steps {
                withSonarQubeEnv('sonarqube') {
                    sh 'mvn -f app/pom.xml sonar:sonar -Dsonar.projectKey=gitops-demo'
                }
            }
        }

        stage('Quality Gate') {
            when { not { changelog '.*\\[skip ci\\].*' } }
            steps {
                timeout(time: 5, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('Docker Build and Push') {
            when { not { changelog '.*\\[skip ci\\].*' } }
            steps {
                script {
                    def imageTag = sh(
                        script: 'git rev-parse --short HEAD',
                        returnStdout: true
                    ).trim()
                    env.IMAGE_TAG = imageTag
                    def imageRef = "${params.REGISTRY}/${params.IMAGE_NAMESPACE}/${params.IMAGE_NAME}:${imageTag}"
                    env.IMAGE_REF = imageRef
                    docker.withRegistry('', 'docker-hub-credentials') {
                        def image = docker.build(imageRef, '.')
                        image.push()
                        echo "Pushed ${imageRef}"
                    }
                }
            }
        }

        stage('Update GitOps Manifests') {
            when { not { changelog '.*\\[skip ci\\].*' } }
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'github-credentials',
                    usernameVariable: 'GIT_USER',
                    passwordVariable: 'GIT_TOKEN')]) {
                    sh '''
                        set -e
                        # Update only the image tag in the Helm chart values.
                        sed -i "s/^  tag: .*/  tag: \\"${IMAGE_TAG}\\"/" helm/app-chart/values.yaml
                        grep -q "tag: \\"${IMAGE_TAG}\\"" helm/app-chart/values.yaml
                        git config user.name "${GIT_COMMIT_NAME}"
                        git config user.email "${GIT_COMMIT_EMAIL}"
                        git add helm/app-chart/values.yaml
                        # [skip ci] stops this commit from triggering another build.
                        git commit -m "chore: update image tag to ${IMAGE_TAG} [skip ci]"
                        git push https://${GIT_USER}:${GIT_TOKEN}@github.com/vinod-codes/jenkins-argocd-gitops-pipeline.git HEAD:main
                    '''
                }
            }
        }
    }

    post {
        always {
            // allowEmptyResults: a [skip ci] build runs no stages, so
            // there are no test reports — that must not turn the build
            // red.
            junit allowEmptyResults: true, testResults: 'app/target/surefire-reports/*.xml'
        }
        failure {
            echo 'Pipeline failed. Check the stage logs; see README.md Troubleshooting.'
        }
    }
}
