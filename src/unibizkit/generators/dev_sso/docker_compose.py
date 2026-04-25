from pathlib import Path
from .constants import KDC_PORT, KADMIN_PORT, KC_PORT


def generate(sso_dir: Path):
    (sso_dir / 'docker-compose.yml').write_text(_content(), encoding='utf-8')


def _content() -> str:
    return f"""\
services:
  kdc:
    build: ./kdc
    hostname: kdc.dev.local
    volumes:
      - ./krb5.conf:/etc/krb5.conf:ro
      - ./kdc.conf:/etc/krb5kdc/kdc.conf:ro
      - kdc-data:/var/lib/krb5kdc
      - keytabs:/keytabs
      - ./caches:/caches
    ports:
      - "{KDC_PORT}:88/udp"
      - "{KDC_PORT}:88/tcp"
      - "{KADMIN_PORT}:749"
    networks:
      sso-net:
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
    hostname: keycloak.dev.local
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD: admin
      KC_HEALTH_ENABLED: "true"
      JAVA_OPTS_APPEND: "-Dsun.security.krb5.debug=true -Dsun.security.jgss.debug=true"
    volumes:
      - ./krb5.conf:/etc/krb5.conf:ro
      - keytabs:/keytabs:ro
      - keycloak-data:/opt/keycloak/data
    ports:
      - "{KC_PORT}:8080"
      - "19000:9000"
    networks:
      sso-net:
        aliases:
          - keycloak.dev.local
    depends_on:
      kdc:
        condition: service_healthy

volumes:
  kdc-data:
  keytabs:
  keycloak-data:

networks:
  sso-net:
    driver: bridge
"""
