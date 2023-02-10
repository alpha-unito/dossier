# Dossier Jupyter Stack

[JupyterHub](https://jupyter.org/hub) is a multi-tenant platform providing Jupyter Notebooks as a Service. It relies on an external database for persistence, e.g. PostgreSQL.

## Postgresql

A secret must be created to store PostgreSQL passwords:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  labels:
    name: jhub
  name: jhub
---
apiVersion: v1
kind: Secret
metadata:
  name: jhub-postgresql
  namespace: jhub
type: Opaque
stringData:
  password: <PostgreSQL user password>
  postgres-password: <PostgreSQL admin password>
  replication-password: <PostgreSQL admin password>
```

The [Postgresql](https://www.postgresql.org/) SQL database can be installed through the related Helm chart using the following command:

```bash
helm install jhub-postgresql bitnami/postgresql     \
    --namespace jhub                                \
    --create-namespace                              \
    --version 12.2.1                                \
    --values postgresql-config.yaml
```

## Jupyter Hub

Also Jupyter Hub can be installed as a Helm chart, but first it is necessary to configure Keycloack for authentication. To do that, it is necessary to create a `jupyter` client on the Keycloak `dossier` realm. Therefore, create a `Client` inside this realm with:

- Client ID: `jupyter`
- Client Protocol: `openid-connect`
- Access Type: `confidential`
- Valid Redirect URIs: ******

In order to trace the Keycloak groups a user belongs to, add a `Mapper` to the client with:

- Name: `tenants`
- Mapper Type: `User Client Role`
- Client ID: `jupyter`
- Multivalued: `True`
- Token Claim Name: `tenants`

If only certain nodes must be used to schedule user and core pods, these nodes must be tagged as follows:

```bash
kubectl label node <node-name> hub.jupyter.org/node-purpose=user
kubectl label node <node-name> hub.jupyter.org/node-purpose=core
```

Plus, it isnecessary to create a Tenant to integrate JupyterHub with the multi-tenacy mechanisms provided by Capsule:

```yaml
apiVersion: capsule.clastix.io/v1beta2
kind: Tenant
metadata:
  name: jhub
spec:
  ingressOptions:
    allowedHostnames:
      allowed: []
  namespaceOptions:
    quota: 100
  networkPolicies:
    items:
      - policyTypes:
        - Ingress
        - Egress
        egress:
        - to:
          - ipBlock:
              cidr: 0.0.0.0/0
              except:
                - 252.0.0.0/8
                - 172.17.7.0/24
                - 172.20.7.0/24
        ingress:
        - from:
          - namespaceSelector:
              matchLabels:
                name: jhub
          - podSelector:
              matchLabels:
                app: envoy
            namespaceSelector:
              matchLabels:
                name: projectcontour
          - podSelector: {}
        podSelector: {}
  owners:
    - name: system:serviceaccount:jhub:hub
      kind: ServiceAccount
  serviceOptions:
    allowedServices:
      loadBalancer: false
      nodePort: false
    externalIPs:
      allowed: []
```

In order to support websockets with Contour, it is necessary to create a `HTTPProxy` resource:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: <Dossier FQDN>-tls
  namespace: jhub
spec:
  dnsNames:
  - <Dossier FQDN>
  issuerRef:
    group: cert-manager.io
    kind: ClusterIssuer
    name: letsencrypt-cluster-issuer
  secretName: <Dossier FQDN>-tls
---
apiVersion: projectcontour.io/v1
kind: HTTPProxy
metadata:
  name: <Dossier FQDN>
  namespace: jhub
spec:
  virtualhost:
    fqdn: <Dossier FQDN>
    tls:
      secretName: <Dossier FQDN>-tls
  routes:
  - conditions:
    - prefix: /
    enableWebsockets: true
    services:
    - name: proxy-public
      port: 80
    timeoutPolicy:
      response: 650s
```

Then, it is sufficient to install the Helm chart with the following command:

```bash
helm install jhub jupyterhub/jupyterhub             \
    --namespace jhub                                \
    --create-namespace                              \
    --version=2.0.0                                 \
    --values jupyterhub-config.yaml
```

Since the JupyterHub application must create pods in different namespaces, it is necessary to create a `ClusterRole` resource and bind it with the hub `ServiceAccount`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: hub
  namespace: jhub
  labels:
    app: jupyterhub
    component: hub
rules:
  - verbs:
      - get
      - watch
      - list
      - create
      - delete
    apiGroups:
      - ''
    resources:
      - pods
      - persistentvolumeclaims
      - secrets
      - services
  - verbs:
      - get
      - watch
      - list
    apiGroups:
      - ''
    resources:
      - events
  - verbs:
      - list
    apiGroups:
      - ''
    resources:
      - namespaces
  - verbs:
      - get
      - list
    apiGroups:
      - capsule.clastix.io
    resources:
      - tenants
  - verbs:
      - get
      - list
    apiGroups:
      - dossier.unito.it
    resources:
      - spawners
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: hub
  namespace: jhub
  labels:
    app: jupyterhub
    component: hub
subjects:
  - kind: ServiceAccount
    name: hub
    namespace: jhub
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: hub
```
