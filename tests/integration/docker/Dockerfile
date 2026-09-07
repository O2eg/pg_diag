ARG PG_IMAGE_TAG=18-bookworm
FROM postgres:${PG_IMAGE_TAG}

ARG PG_MAJOR

# Keep PG10's legacy packages and their indexes together after Bullseye LTS.
# Snapshot expiry is expected; APT signature verification remains enabled.
RUN if [ "$PG_MAJOR" = "10" ]; then \
        printf '%s\n' \
            'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260901T000000Z/ bullseye main' \
            'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260901T000000Z/ bullseye-updates main' \
            'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/20260901T000000Z/ bullseye-security main' \
            > /etc/apt/sources.list; \
    fi \
    && apt-get update \
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
