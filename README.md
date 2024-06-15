# Dossier

**Dossier** provides multi-tenant distributed [Jupyter Notebooks](https://jupyter.org/) as a Service on [Kubernetes](https://kubernetes.io/). In particular, it leverages on three existing technological stacks, integrating them in a coherent and user-friendly environment:

- [JupyterHub](https://jupyterhub.readthedocs.io/en/stable/) can spawn per-user Jupyter Notebooks on Kubernetes through the [KubeSpawner](https://github.com/jupyterhub/kubespawner) library;
- The [Capsule](https://capsule.clastix.io/) Operator implements a multi-tenant, policy-based environment on a Kubernetes cluster, logically grouping namespaces in `Tenants` to easily manage authorization and accounting;
- The [Jupyter-workflow](https://github.com/alpha-unito/jupyter-workflow) kernel enables Jupyter Notebooks to describe complex workflows and to execute them in a distributed fashion on hybrid HPC-Cloud infrastructures, following a Bring Your Own Device (BYOD) approach.