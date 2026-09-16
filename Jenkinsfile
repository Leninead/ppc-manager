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
  // The weekly cron exists so the Launch Score drift check runs even in a week
  // with no pushes; it never deploys (the CD stages gate on SCMTrigger).
  triggers {
    pollSCM('H/2 * * * *')
    cron('H 6 * * 1')
  }

  parameters {
    booleanParam(name: 'DEPLOY', defaultValue: false,
      description: 'true = also deploy to the VPS (docker compose up in DEPLOY_DIR).')
  }

  environment {
    IMAGE      = 'ppc-manager'
    RECEIVER_IMAGE = 'ppc-manager-receiver'             // OAuth callback + MELI webhooks
    DEPLOY_DIR = '/srv/ppc-manager'                      // compose bind-mount on the VPS
    APP_CONTAINER = 'ppc-manager'                        // gated via the container's own healthcheck
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
    stage('Build images') {
      // Two images, one tag. The receiver COPYs core/integrations/, so it has to
      // be rebuilt on the same commit or the deploy ships two versions of it.
      steps {
        sh 'docker build -t $IMAGE:$SHA -t $IMAGE:latest .'
        sh 'docker build -f services/integrations_receiver/Dockerfile -t $RECEIVER_IMAGE:$SHA -t $RECEIVER_IMAGE:latest .'
      }
    }

    stage('Test') {
      // tests/ is dockerignored and pytest isn't in requirements, so run on a
      // python:3.11 over the checkout. Tests needing client data skip themselves. Gates deploy.
      steps {
        sh '''
          docker run --rm -v "$WORKSPACE":/w -w /w -e AGENCY_OS_LOCAL_MODE=1 python:3.11-slim \
            bash -c "apt-get update -qq && apt-get install -y -qq git >/dev/null && pip install --no-cache-dir -q -r requirements.txt pytest && python -m pytest -q"
        '''
      }
    }

    stage('Launch Score drift') {
      // The Launch Score is not in DataDive's API: core/datadive.py replicates
      // their frontend formula, and a replica breaks silently when the original
      // changes. Both sources it checks are public, so this needs no secrets.
      // Never blocks a deploy — a third party changing a formula is news, not a
      // broken build, so it only marks the run UNSTABLE.
      steps {
        catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
          sh '''
            docker run --rm -v "$WORKSPACE":/w -w /w python:3.11-slim \
              bash -c "pip install --no-cache-dir -q requests && python scripts/check_launch_score_drift.py"
          '''
        }
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
          # The portal used to keep its vars in a second file. Compose never read
          # it for interpolation, so they moved into .env — refuse to deploy
          # against a host still on the old layout instead of starting a stack
          # whose worker and receiver silently lose their credentials.
          for v in INTEGRATIONS_RECEIVER_JWT INTEGRATIONS_WORKER_JWT INTEGRATIONS_PUBLIC_KEY INTEGRATIONS_REDIRECT_URI; do
            grep -qE "^$v=.+" "$DEPLOY_DIR/.env" || {
              echo "$v missing from $DEPLOY_DIR/.env — move the portal vars out of .env.integrations (see deploy/integrations/env.example), then delete that file."; exit 1;
            }
          done
          # .env.integrations is deliberately kept: deleting a host file that
          # holds secrets is the operator's call, not the pipeline's.
          rsync -a --delete --exclude='.git' --exclude='.env' --exclude='.env.integrations' --exclude='.streamlit/secrets.toml' \
            "$WORKSPACE"/ "$DEPLOY_DIR"/
        '''
        // ai-net is external: compose refuses to start if it is missing.
        sh 'docker network inspect ai-net >/dev/null 2>&1 || docker network create ai-net'
        // Pin the tag in DEPLOY_DIR/.env before composing. The worker runs on a
        // cron, outside the pipeline, and resolves `${IMAGE_TAG:-latest}` from
        // this file: without the pin it rotates single-use seller refresh tokens
        // using `latest`, which the Build stage moves on EVERY build — including
        // builds whose tests fail, builds with DEPLOY=false, the weekly timer
        // build, and the build a health gate just rolled back. A burned token is
        // not recoverable by rolling back: that seller has to authorize again.
        // Rewritten whole rather than appended: `sed` always terminates the last
        // line it prints, so this cannot glue IMAGE_TAG onto a file that lacks a
        // trailing newline. No printf — Groovy eats backslash escapes inside ''' .
        sh '''
          { sed "/^IMAGE_TAG=/d" "$DEPLOY_DIR/.env"; echo "IMAGE_TAG=$SHA"; } > "$DEPLOY_DIR/.env.next"
          chmod 600 "$DEPLOY_DIR/.env.next"
          mv "$DEPLOY_DIR/.env.next" "$DEPLOY_DIR/.env"
        '''
        dir("${DEPLOY_DIR}") { sh 'IMAGE_TAG=$SHA docker compose up -d' }
        // Caddy and the gateway take their config as a bind-mounted FILE. Compose
        // hashes the mount path, not the file's contents, so a routing change ships
        // in the rsync and never reaches the running process — /oauth/* would keep
        // going to Streamlit and every seller consent would die quietly, with the
        // health gate none the wiser (it checks containers, not routes).
        dir("${DEPLOY_DIR}") { sh 'IMAGE_TAG=$SHA docker compose up -d --force-recreate caddy rest-gateway' }
      }
    }

    stage('DB migrate') {
      when { anyOf { expression { params.DEPLOY }; triggeredBy 'SCMTrigger' } }
      // Schema first, health second: the new image can depend on a column the
      // migration adds. migrate.sh is idempotent and exits clean on a host
      // with no db overlay, so this is safe on every deployment shape.
      steps { dir("${DEPLOY_DIR}") { sh 'sh deploy/db/migrate.sh' } }
    }

    stage('Health gate') {
      when { anyOf { expression { params.DEPLOY }; triggeredBy 'SCMTrigger' } }
      steps {
        script {
          // Poll BOTH long-lived containers' own healthchecks (topology-independent).
          // Loopback-port curls would false-pass if base republished 8501/8600.
          // integrations-receiver is included so a broken OAuth callback breaks the deploy,
          // instead of silently reporting healthy while every seller consent attempt 502s.
          def healthy = sh(returnStatus: true, script: '''
            for i in $(seq 1 30); do
              a=$(docker inspect --format '{{.State.Health.Status}}' $APP_CONTAINER 2>/dev/null || echo none)
              r=$(docker inspect --format '{{.State.Health.Status}}' integrations-receiver 2>/dev/null || echo none)
              if [ "$a" = "healthy" ] && [ "$r" = "healthy" ]; then echo healthy; exit 0; fi
              sleep 5
            done
            echo "never became healthy (app: $a, receiver: $r)"; exit 1
          ''') == 0
          if (!healthy) {
            // 'latest' is a floating tag the Build stage just repointed at the NEW (failing) image, so it is
            // not a safe rollback target — treat it like 'none' and stop for manual intervention.
            if (env.PREV?.trim() && env.PREV != 'none' && env.PREV != 'latest') {
              // Roll the pin back too, or the cron worker keeps running the
              // image this gate just rejected.
              sh 'sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$PREV/" "$DEPLOY_DIR/.env"'
              dir("${DEPLOY_DIR}") { sh 'IMAGE_TAG=$PREV docker compose up -d' }
              // An image from before a worker has no module for it: stop the service instead of letting it crash-loop.
              dir("${DEPLOY_DIR}") {
                sh '''
                  if docker compose config --services | grep -qx ads-sync-worker; then
                    docker run --rm --entrypoint python "$IMAGE:$PREV" -c "import core.amazon_ads.worker" >/dev/null 2>&1 || docker compose stop ads-sync-worker
                  fi
                  if docker compose config --services | grep -qx ads-ai-worker; then
                    docker run --rm --entrypoint python "$IMAGE:$PREV" -c "import core.ai_analysis.worker" >/dev/null 2>&1 || docker compose stop ads-ai-worker
                  fi
                '''
              }
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
      // `--require` when the deployment has the db overlay, so a stack that lost
      // the overlay fails here instead of reporting a green gate over no database.
      steps {
        sh 'docker cp "$DEPLOY_DIR/deploy/db/smoke_readonly.py" $APP_CONTAINER:/tmp/smoke.py'
        dir("${DEPLOY_DIR}") {
          sh '''
            docker compose config --services | grep -qx postgrest && REQ=--require || REQ=
            docker exec -w /app -e PYTHONPATH=/app $APP_CONTAINER python /tmp/smoke.py $REQ
          '''
        }
      }
    }

    stage('Prune old images') {
      when { anyOf { expression { params.DEPLOY }; triggeredBy 'SCMTrigger' } }
      // Keep the 2 newest tags (current + previous = the rollback target) and drop older ones, so
      // images don't pile up one-per-build. Last: runs only after a healthy deploy, so PREV survives.
      steps {
        sh '''
          for repo in $IMAGE $RECEIVER_IMAGE; do
            docker images "$repo" --format '{{.Tag}}' | grep -vx latest | awk 'NR>2' \\
              | while read t; do docker rmi "$repo:$t" || true; done
          done
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
