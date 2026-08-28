// Jenkinsfile — Amazon PPC Manager (Agency OS)
// CI (Checkout → Build → Test) always runs and needs no VPS.
// CD (Deploy → Health) runs only with DEPLOY=true, so the pipeline stays green
// before a target exists. Assumes Jenkins on the VPS (local Docker, no SSH);
// for Jenkins elsewhere see the footer.
pipeline {
  agent any
  options { timestamps(); disableConcurrentBuilds() }

  // Poll the repo every ~2 min and build on new HEAD — works behind NAT (no public IP).
  // For instant builds, swap for a GitHub webhook (github plugin).
  triggers { pollSCM('H/2 * * * *') }

  parameters {
    booleanParam(name: 'DEPLOY', defaultValue: false,
      description: 'true = also deploy to the VPS (docker compose up in DEPLOY_DIR).')
  }

  environment {
    IMAGE      = 'ppc-manager'
    DEPLOY_DIR = '/srv/ppc-manager'                      // compose bind-mount on the VPS
    APP_CONTAINER = 'ppc-manager'                        // gated via the container's own healthcheck
    // Known environmental reds on a checkout with no client data / Supabase.
    DESELECTS  = '--deselect tests/test_m29_ui_e2e.py --deselect tests/test_datadive_to_v3_mapper.py --deselect tests/test_b7_importer.py'
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
        script { env.SHA = sh(returnStdout: true, script: 'git rev-parse --short HEAD').trim() }
        echo "commit ${env.SHA}"
      }
    }

    // ── CI — always, no VPS needed ────────────────────────────────────────
    stage('Build image') {
      steps { sh 'docker build -t $IMAGE:$SHA -t $IMAGE:latest .' }
    }

    stage('Test') {
      // tests/ is dockerignored and pytest isn't in requirements, so run on a
      // python:3.11 over the checkout, deselecting environmental reds. Gates deploy.
      steps {
        sh '''
          docker run --rm -v "$WORKSPACE":/w -w /w -e AGENCY_OS_LOCAL_MODE=1 python:3.11-slim \
            bash -c "apt-get update -qq && apt-get install -y -qq git >/dev/null && pip install --no-cache-dir -q -r requirements.txt pytest && python -m pytest -q $DESELECTS"
        '''
      }
    }

    // ── CD — only with DEPLOY=true and the VPS present ────────────────────
    stage('Record rollback target') {
      when { anyOf { expression { params.DEPLOY }; triggeredBy 'SCMTrigger' } }
      steps {
        script {
          env.PREV = sh(returnStdout: true, script:
            "docker inspect --format '{{.Config.Image}}' ppc-manager 2>/dev/null | sed 's/.*://' || echo none").trim()
          echo "rollback target: ${env.PREV}"
        }
      }
    }

    stage('Deploy') {
      when { anyOf { expression { params.DEPLOY }; triggeredBy 'SCMTrigger' } }
      // Sync the built commit into DEPLOY_DIR (keeping its host-only secrets), then compose up — so
      // DEPLOY_DIR always reflects the exact deployed commit (no drift). COMPOSE_FILE in the kept
      // .env selects the overlays (base + proxy + db).
      steps {
        // Fail fast if DEPLOY_DIR isn't provisioned with its host-only secrets — else a bare compose up
        // silently degrades to base-only (no proxy, no DB) and a missing secrets.toml becomes a dir (login breaks).
        sh '''
          test -f "$DEPLOY_DIR/.env" && grep -q '^COMPOSE_FILE=' "$DEPLOY_DIR/.env" && test -f "$DEPLOY_DIR/.streamlit/secrets.toml" || {
            echo "DEPLOY_DIR ($DEPLOY_DIR) not provisioned: seed .env (COMPOSE_FILE + POSTGRES_PASSWORD/PGADMIN_PASSWORD/SUPABASE_KEY/APP_DOMAIN/ACME_EMAIL) and .streamlit/secrets.toml first."; exit 1;
          }
          rsync -a --delete --exclude='.git' --exclude='.env' --exclude='.streamlit/secrets.toml' \
            "$WORKSPACE"/ "$DEPLOY_DIR"/
        '''
        // ai-net is external: compose refuses to start if it is missing.
        sh 'docker network inspect ai-net >/dev/null 2>&1 || docker network create ai-net'
        dir("${DEPLOY_DIR}") { sh 'IMAGE_TAG=$SHA docker compose up -d' }
      }
    }

    stage('Health gate') {
      when { anyOf { expression { params.DEPLOY }; triggeredBy 'SCMTrigger' } }
      steps {
        script {
          // Poll the app container's own healthcheck (topology-independent): a loopback-port curl
          // would false-pass if base republished 8501, hiding a broken proxy after an overlay deploy.
          def healthy = sh(returnStatus: true, script: '''
            for i in $(seq 1 30); do
              s=$(docker inspect --format '{{.State.Health.Status}}' $APP_CONTAINER 2>/dev/null || echo none)
              if [ "$s" = "healthy" ]; then echo healthy; exit 0; fi
              sleep 5
            done
            echo "never became healthy (last: $s)"; exit 1
          ''') == 0
          if (!healthy) {
            // 'latest' is a floating tag the Build stage just repointed at the NEW (failing) image, so it is
            // not a safe rollback target — treat it like 'none' and stop for manual intervention.
            if (env.PREV?.trim() && env.PREV != 'none' && env.PREV != 'latest') {
              dir("${DEPLOY_DIR}") { sh 'IMAGE_TAG=$PREV docker compose up -d' }
              error("Rolled back to ${env.PREV}: deploy of ${env.SHA} failed the health gate.")
            } else {
              error("No previous image to roll back to — manual intervention needed.")
            }
          }
        }
      }
    }

    stage('DB smoke') {
      when { anyOf { expression { params.DEPLOY }; triggeredBy 'SCMTrigger' } }
      // Read-only: confirm the self-hosted PostgREST answers for every table (no writes to prod).
      // Skips gracefully if the DB backend isn't active on this deploy.
      steps {
        sh 'docker cp "$DEPLOY_DIR/deploy/db/smoke_readonly.py" $APP_CONTAINER:/tmp/smoke.py'
        sh 'docker exec -w /app -e PYTHONPATH=/app $APP_CONTAINER python /tmp/smoke.py'
      }
    }

    stage('Prune old images') {
      when { anyOf { expression { params.DEPLOY }; triggeredBy 'SCMTrigger' } }
      // Keep the 2 newest tags (current + previous = the rollback target) and drop older ones, so
      // images don't pile up one-per-build. Last: runs only after a healthy deploy, so PREV survives.
      steps {
        sh '''
          docker images $IMAGE --format '{{.Tag}}' | grep -vx latest | awk 'NR>2' \
            | while read t; do docker rmi "$IMAGE:$t" || true; done
          docker image prune -f >/dev/null
        '''
      }
    }
  }

  post {
    success { echo "OK — SHA ${env.SHA}${params.DEPLOY ? ' + deploy' : ' (CI only)'}" }
    failure { echo 'Failed. If it tripped the health gate on deploy, the previous image was restored.' }
  }
}

// ── Jenkins on ANOTHER machine (not the VPS) ──────────────────────────────
// The Deploy stage becomes, with a Jenkins SSH credential:
//   sshagent(['vps-ssh']) {
//     sh 'docker save $IMAGE:$SHA | ssh user@vps "docker load"'
//     sh 'ssh user@vps "cd /srv/ppc-manager && IMAGE_TAG=$SHA docker compose up -d"'
//   }
// and the Health gate curls https://<domain>/_stcore/health.
