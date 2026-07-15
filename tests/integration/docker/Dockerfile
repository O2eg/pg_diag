ARG PG_IMAGE_TAG=18-bookworm
FROM postgres:${PG_IMAGE_TAG}

ARG PG_MAJOR

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iproute2 \
        lshw \
        openssh-server \
        procps \
        postgresql-${PG_MAJOR}-pg-wait-sampling \
        sysstat \
        util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -m 0755 /run/sshd \
    && install -d -m 0700 /root/.ssh \
    && passwd -d root \
    && rm -f /etc/ssh/ssh_host_* \
    && printf '%s\n' \
        'PasswordAuthentication no' \
        'KbdInteractiveAuthentication no' \
        'PermitRootLogin prohibit-password' \
        'PubkeyAuthentication yes' \
        > /etc/ssh/sshd_config.d/pg_diag_integration.conf
