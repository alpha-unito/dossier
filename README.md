# JupyterHub Dossier

Dossier is a [JupyterHub](https://jupyterhub.readthedocs.io/en/stable) extension that provides multi-tenant distributed [Jupyter Notebooks](https://jupyter.org/) as a Service on [Kubernetes](https://kubernetes.io/). In particular, it provides a Kubernetes-centric management of multi-user, distributed eScience platforms that leverage Jupyter Notebooks as their primary user interface.

The [Capsule](https://capsule.clastix.io/) platform implements a multi-tenant, policy-based environment on a Kubernetes cluster. It logically groups namespaces in `Tenants` to easily manage authorization, accounting, and resource segmentation. Dossier extends the JupyterHub [KubeSpawner](https://github.com/jupyterhub/kubespawner) library, which can spawn per-user Jupyter Notebooks on a Kubernetes cluster, to support `Tenants` and spawn user-requested Jupyter Notebooks accordingly.

In this setting, a Kubernetes `Tenant` becomes the central point where system administrators can configure all aspects of Jupyter Notebooks spawning through Kubernetes `annotations`, e.g., resource requests and limits, access to GPUs and persistent volumes, Jupyter-based container images, and even custom `Spawner` classes to access remote resources (like private clouds or queue-based HPC facilities).
