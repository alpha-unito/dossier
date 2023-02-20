# Dossier Authorization Plane

## Capsule

[Capsule](https://github.com/clastix/capsule) is a Kubernetes abstraction which helps in setting up multi-tenancy in a cluster by means of the `Tenant` resources. Within a tenant, users are free to create their namespaces and share all the assigned resources, while the Capsule Policy Engine keeps the different tenants isolated from each other.

Capsule can be installed through the official Helm chart, using the following commands:

```bash
helm repo add clastix https://clastix.github.io/charts
helm repo update

helm install capsule clastix/capsule    \
    --namespace capsule-system          \
    --create-namespace                  \
    --version 0.3.2                     \
    --values capsule-values.yaml
```

Then, it is necessary to manualyl patch all the `capsule.clastix.io` CRDs by adding the following `annotation`:

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  annotations:
    cert-manager.io/inject-ca-from: capsule-system/capsule-webhook-cert
    ...
```

## Tenant configuration

Tenants can be used to limit access to Cluster resources. In particular, they allow to:

- Enforce reosources quotas (e.g. RAM, cores, disk)
- Limit access to a subset of worker nodes
- Assign specific Ingress classes and hostnames for services
- Configure the available Storage classes
- Isolate different tenants through Network policies
- Limit the container registries available for downloading images
- Prevent privileged containers by enforcing Pod security policies

We chose to use `tenant-owners` as the group identifying Tenant administrators. Such group can be simply added to Keycloak users by creating a `Client Role` resource with the same name in the `kubernetes` client and assigning such role to the desired users. A new tenant can then be created with the following manifest:

```yaml
apiVersion: capsule.clastix.io/v1beta2
kind: Tenant
metadata:
  name: <Tenant Name>
spec:
  ingressOptions:
    allowedHostnames:
      allowed: []
  namespaceOptions:
    quota: <Number of manageable namespaces>
  networkPolicies:
    items:
      - policyTypes:
        - Ingress
        - Egress
        egress:
        - to:
          - ipBlock:
              cidr: 0.0.0.0/0
              except: <Blocked IPs>
        ingress:
        - from:
          - namespaceSelector:
              matchLabels:
                name: jhub
          - namespaceSelector:
              matchLabels:
                capsule.clastix.io/tenant: <Tenant Name>
          - podSelector:
              matchLabels:
                app: envoy
            namespaceSelector:
              matchLabels:
                name: projectcontour
          - podSelector: {}
        podSelector: {}
  nodeSelector:
    pool: <Tenant Name>
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