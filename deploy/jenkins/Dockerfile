# Jenkins for the Agency OS CI/CD: LTS base + Docker CLI + compose plugin + the
# pipeline/JCasC plugins. Run with the host Docker socket mounted, so it builds
# and deploys the app image on the VPS's own Docker.
FROM jenkins/jenkins:lts-jdk17
USER root

# Docker CLI + compose plugin (for `docker build` / `docker compose` from the pipeline) +
# rsync (deploy-from-checkout sync). arch is derived so this builds on both amd64 and the VPS's arm64.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin rsync \
 && rm -rf /var/lib/apt/lists/*

# Jenkins runs git as root over the bind-mounted repo → trust it (avoids "dubious ownership").
RUN git config --system --add safe.directory '*'

COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# Baked-in Config-as-Code: creates the `ppc-manager` job and admin user on boot.
COPY casc.yaml /usr/share/jenkins/ref/casc.yaml
ENV CASC_JENKINS_CONFIG=/usr/share/jenkins/ref/casc.yaml
