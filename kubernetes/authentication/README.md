# Dossier Authentication

## Keycloak

[Keycloak](https://www.keycloak.org/) is a standalone Identity Manager that can be used to store Open Deep Health users. Two secrets must be created to store Keycloak and PostgreSQL passwords:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  labels:
    name: keycloak
    role: identity
  name: keycloak
---
apiVersion: v1
kind: Secret
metadata:
  name: keycloak
  namespace: keycloak
type: Opaque
stringData:
  admin-password: <Keycloak admin password>
  database-password: <PostgreSQL user password>
  management-password: <Keycloak management password>
---
apiVersion: v1
kind: Secret
metadata:
  name: keycloak-postgresql
  namespace: keycloak
type: Opaque
stringData:
  password: <PostgreSQL user password>
  postgres-password: <PostgreSQL admin password>
  replication-password: <PostgreSQL admin password>
```

After that, a Keycloak cluster can be installed using an Helm Chart, as follows

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

helm install keycloak bitnami/keycloak  \
    --namespace keycloak                \
    --version 13.0.4                    \
    --values keycloak-values.yaml
```

In order to enable Keycloak internal metrics, it is necessary to add additional `ServiceMonitor` resources pointing to `/auth/realms/master/metrics`:

```yaml
kind: ServiceMonitor
apiVersion: monitoring.coreos.com/v1
metadata:
  name: keycloak-realms
  namespace: monitoring
spec:
  endpoints:
    - interval: 10s
      path: /auth/realms/master/metrics
      port: http
  namespaceSelector:
    matchNames:
      - keycloak
  selector:
    matchLabels:
      app.kubernetes.io/component: keycloak
      app.kubernetes.io/instance: keycloak
      app.kubernetes.io/name: keycloak
```

### Connect Keycloak with Dossier

When Keycloak is ready, the first step is to create a new `Realm` called `dossier` to store platform users.
