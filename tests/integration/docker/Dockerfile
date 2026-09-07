ARG PG_IMAGE_TAG=18-bookworm
FROM postgres:${PG_IMAGE_TAG}

ARG PG_MAJOR

# Bullseye LTS ended on 2026-08-31; PG10 needs its frozen security index.
# Relax only that index's expiry check, retaining signature verification.
RUN if [ "$PG_MAJOR" = "10" ]; then \
        sed -i '/^deb .* bullseye-security /s/^deb /deb [check-valid-until=no] /' /etc/apt/sources.list; \
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
