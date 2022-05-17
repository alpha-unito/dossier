FROM jupyterhub/k8s-hub:1.2.0

USER root

COPY setup.py /tmp/setup.py
COPY dossier /tmp/dossier
COPY share /tmp/share
COPY README.md /tmp/README.md
RUN pip3 install jupyter-workflow==0.1.0.dev3 /tmp \
    && python3 -m jupyter_workflow.ipython.install

USER ${NB_USER}
CMD ["dossier", "--config", "/usr/local/etc/jupyterhub/jupyterhub_config.py"]