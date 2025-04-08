# devexy

Local cluster management, and other tools to aid development.

## Usage

```sh
pip install git+https://github.com/sycdan/devexy

dev --help

# Follow the logs
dev logs -f

# Manage the cluster
dev mk i
```

## Configuration

**devexy** will look for a `.env` file in the working directory.

These are the defaults, and how to override them:

```sh
export DEVEXY_KUSTOMIZE_ROOT=./k8s/
export DEVEXY_KUSTOMIZE_OVERLAY=local
export DEVEXY_LOCAL_PORT_ANNOTATION=devexy/local-port
```

## Caveats

**devexy** only works with `minikube` and `kustomize` at this time.

Only 1 replica per service is allowed, to minimize resource usage and simplify port forwarding.

The local port annotation must exist on the scalable resource (Deployment / ReplicaSet / StatefulSet), not the Service.

## Contributing

### Code Style / Formatting

We use [Ruff](https://github.com/astral-sh/ruff), with the rules defined in [pyproject.toml](pyproject.toml).
