# Dossier Ingress Controller

## Contour

The [Contour](https://projectcontour.io/) Ingress Controller can be easily installed through the related Kubernetes Operator. First of all, it is necessary to install the operator using the following command:

``` bash
kubectl apply -f https://raw.githubusercontent.com/projectcontour/contour-operator/release-1.24/examples/operator/operator.yaml
```

Then, a Contour instance can be installed using the following manifest:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  labels:
    name: projectcontour
    role: ingress-controller
  name: projectcontour
---
apiVersion: operator.projectcontour.io/v1alpha1
kind: Contour
metadata:
  name: contour
  namespace: projectcontour
spec:
  networkPublishing:
    envoy:
      type: LoadBalancerService
  nodePlacement:
    contour:
      nodeSelector:
        node-role.kubernetes.io/control-plane: ''
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
  replicas: 3
```

## Cert-manager

The [cert-manager](https://cert-manager.io/) tool can be combined with Contour to deploy HTTPS services. The cert-manager application can be easily installed with Helm, but as a preliminary step it is necessary to install all the related [Custom Resource Definitions](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/) (CRDs) with the following command

```bash
kubectl apply -f https://github.com/jetstack/cert-manager/releases/download/v1.11.0/cert-manager.crds.yaml
```

It is worth noting that CRDs could also be installed directly with Helm, through the `installCRDs` option, but in this scenarion a removal of the Helm release also implies the deletion of all CRDs and all the related custom resources, which is not desirable.

The next step requires to configure the `JetStack` Helm repo and to install the desired version of `cert-manager` in a reserved `cert-manager` namespace

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update

helm install cert-manager jetstack/cert-manager  \
    --namespace cert-manager                     \
    --create-namespace                           \
    --version v1.11.0                            \
    --values certmanager-values.yaml
```

### Configure ClusterIssuer in Kubernetes

The `cert-manager` service supports [Let's Encrypt](https://letsencrypt.org/) certificate generation. To enable this feature in a Kubernetes cluster, it is necessary to create a `ClusterIssuer` resource as follows

```yaml
kind: ClusterIssuer
apiVersion: cert-manager.io/v1
metadata:
  name: letsencrypt-cluster-issuer
  namespace: cert-manager
spec:
  acme:
    email: ******
    privateKeySecretRef:
      name: letsencrypt
    server: https://acme-v02.api.letsencrypt.org/directory
    solvers:
    - http01:
        ingress:
          class: contour
          serviceType: ClusterIP
```
