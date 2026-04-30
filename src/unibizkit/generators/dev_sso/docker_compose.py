from pathlib import Path
from .. import dev_ports


def generate(sso_dir: Path):
    (sso_dir / 'docker-compose.yml').write_text(_content(), encoding='utf-8')


def _content() -> str:
    n = f"{dev_ports.ENV_NUM:02d}"
    return f"""\
services:
  kdc:
    build: ./kdc
    image: unibizkit-sso-kdc-{n}:latest
    container_name: kdc_{n}
    hostname: kdc.dev.local
    volumes:
      - ./krb5.conf:/etc/krb5.conf:ro
      - ./kdc.conf:/etc/krb5kdc/kdc.conf:ro
      - kdc-data-{n}:/var/lib/krb5kdc
      - keytabs-{n}:/keytabs
      - ./caches:/caches
    ports:
      - "{dev_ports.KDC_PORT}:88/udp"
      - "{dev_ports.KDC_PORT}:88/tcp"
      - "{dev_ports.KADMIN_PORT}:749"
    networks:
      sso-net-{n}:
        aliases:
          - kdc.dev.local
    healthcheck:
      test: ["CMD", "test", "-f", "/keytabs/keycloak.keytab"]
      interval: 5s
      timeout: 3s
      retries: 20
      start_period: 10s

  keycloak:
    image: quay.io/keycloak/keycloak:26.0
    command: start-dev
    container_name: keycloak_{n}
    hostname: keycloak.dev.local
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD: admin
      KC_HEALTH_ENABLED: "true"
      JAVA_OPTS_APPEND: "-Dsun.security.krb5.debug=true -Dsun.security.jgss.debug=true"
    volumes:
      - ./krb5.conf:/etc/krb5.conf:ro
      - keytabs-{n}:/keytabs:ro
      - keycloak-data-{n}:/opt/keycloak/data
    ports:
      - "{dev_ports.KC_PORT}:8080"
      - "{dev_ports.KC_MGMT_PORT}:9000"
    networks:
      sso-net-{n}:
        aliases:
          - keycloak.dev.local
    depends_on:
      kdc:
        condition: service_healthy

volumes:
  kdc-data-{n}:
  keytabs-{n}:
  keycloak-data-{n}:

networks:
  sso-net-{n}:
    driver: bridge
"""
