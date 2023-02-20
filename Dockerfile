FROM jupyterhub/k8s-hub:2.0.0

USER root

COPY setup.py /tmp/setup.py
COPY dossier /tmp/dossier
COPY share /tmp/share
COPY README.md /tmp/README.md
RUN pip3 install /tmp

USER ${NB_USER}

CMD ["dossier", "--config", "/usr/local/etc/jupyterhub/jupyterhub_config.py"]
