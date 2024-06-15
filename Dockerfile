FROM jupyterhub/k8s-hub:3.3.7 AS builder

USER root

RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs

COPY ./bower-lite           \
     ./build.py             \
     ./package.json         \
     ./README.md            \
     ./requirements.txt     \
     ./pyproject.toml       \
     /build/
COPY ./dossier /build/dossier
COPY ./share/ /build/share

RUN cd /build \
    && pip install .

FROM jupyterhub/k8s-hub:3.3.7

COPY --from=builder /usr/local/bin/dossier /usr/local/bin/dossier
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/share/jupyterhub/static/dossier /usr/local/share/jupyterhub/static/dossier
COPY --from=builder /usr/local/share/jupyterhub/templates/dossier /usr/local/share/jupyterhub/templates/dossier

CMD ["dossier", "--config", "/usr/local/etc/jupyterhub/jupyterhub_config.py"]
