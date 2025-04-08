# devexy

Local cluster management, and other tools to aid development.

## Usage

_Setup up [minikube](https://minikube.sigs.k8s.io/docs/start/) or another local cluster first!._

```sh
pip install git+https://github.com/sycdan/devexy

devexy --help

# Follow the logs
devexy logs -f

# Start forwarding ports from localhost to the cluster
devexy workon --apply
```

When you use the `--apply` flag, **devexy** will load your selected overlay's `kustomization.yaml` and create the resources in the cluster or apply any changes.

### Workon

The `workon` command tries to set up port forwarding for all scalable resources in the cluster (anything with `replicas`), use the local port defined by the `DEVEXY_LOCAL_PORT_ANNOTATION`.

You can toggle the working mode for the selected resource between _remote_ (the default) and _local_.

#### Remote

In _remote_ mode, **devexy** opens a port on `localhost` and forwards traffic to the resource running in the cluster.

#### Local

In _local_ mode, **devexy** will replace the running resource in the cluster with a reverse proxy that will forward any intra-cluster requests to the local port on `localhost`. This is useful when you want to run and debug an app locally instead of in the cluster, and need other parts of your system to still be able to communicate with it.

## Configuration

**devexy** will look for a `.env` file in the working directory.

These are the defaults, and how to override them:

```sh
export DEVEXY_KUSTOMIZE_ROOT=./k8s/
export DEVEXY_KUSTOMIZE_OVERLAY=local
export DEVEXY_LOCAL_PORT_ANNOTATION=devexy/local-port
```

## Caveats

**devexy** only works with `kustomize` at this time, and only with the the default `kubectl` cluster configuration.

Only 1 replica per service is allowed, to minimize resource usage and simplify port forwarding.

The local port annotation must exist on the scalable resource (Deployment / ReplicaSet / StatefulSet), not the Service.

For local mode to work, the app label and name must be the same for the Service & Scalable resource.

## TODO

- Allow more flexibility with resource naming in local mode
  - This may involve create Resource objects from the template YAML and then copying data from the real resources
- Support k8s secrets

## Contributing

### Code Style / Formatting

We use [Ruff](https://github.com/astral-sh/ruff), with the rules defined in [pyproject.toml](pyproject.toml).
