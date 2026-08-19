# Jenkins CI/CD — Agency OS

Setup de Jenkins (containerizado, desde `Dockerfile`) que ejecuta el [`Jenkinsfile`](../../Jenkinsfile)
del repo. Topología A: **Jenkins corre en la VPS**, con el Docker del host → build, test y
deploy son locales. Validado end-to-end en una VPS simulada (WSL2 Ubuntu): build #3 → SUCCESS
(checkout → build → test → deploy `IMAGE_TAG=<sha>` → health-gate).

## Qué hay acá
- `Dockerfile` — Jenkins LTS + Docker CLI + compose plugin + plugins (`plugins.txt`) + JCasC horneado.
- `plugins.txt` — pipeline (`workflow-aggregator`), `git`, `configuration-as-code`, `job-dsl`, `docker-workflow`, `timestamper`.
- `casc.yaml` — Config-as-Code: crea el user `admin` y el job `ppc-manager` (pipeline desde SCM, param `DEPLOY`).
- `docker-compose.yml` — corre Jenkins con `network_mode: host` + socket del host + `JENKINS_HOME=/srv/jenkins-home`.

## Correrlo (en la VPS)
```bash
# el job clona el repo desde /srv/ppc-repo (SIM). En prod, apuntá el SCM a GitHub (ver casc.yaml).
git clone -b <branch> <repo-url> /srv/ppc-repo
docker compose -f deploy/jenkins/docker-compose.yml up -d --build
# http://127.0.0.1:8080  (admin/admin en el sim — CAMBIALO)
```
Disparar el pipeline: en la UI, **Build with Parameters** → `DEPLOY=true` para incluir el deploy.

## SIM vs PROD (importante)
- **SIM** (VPS simulada, este repo): el job clona local (`file:///srv/ppc-repo`), por eso el
  `JAVA_OPTS` trae `-Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true`.
- **PROD**: en `casc.yaml`, cambiá el `remote` del job al repo real de GitHub y agregá una
  credencial (`credentials('...')`); **sacá** el flag `ALLOW_LOCAL_CHECKOUT` del `JAVA_OPTS`.
  Cambiá también el password de `admin` y considerá un webhook de GitHub en vez de disparo manual.

## Notas de seguridad (sim vs real)
- `admin/admin` y `useScriptSecurity: false` son para el sim. En real: password fuerte,
  credenciales en el store de Jenkins, y no exponer 8080 a internet (dejalo en loopback / detrás del proxy).
- `user: root` + socket del host le da a Jenkins control del Docker del host — aceptable para
  un nodo único dedicado; si no, usar un agente con menos privilegios.
