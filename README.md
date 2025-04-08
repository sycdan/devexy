# Devexy

Local cluster management, and other tools to aid development.

## Usage

```sh
pip install devexy

dev --help
```

## Configuration

Devexy will look for a `.env` file in the working directory.

These are the defaults, and how to override them:

```sh
export DEVEXY_KUSTOMIZE_ROOT=./k8s/
export DEVEXY_KUSTOMIZE_OVERLAY=local
```

## Caveats

Devexy only works with `minikube` and `kustomize` at this time.

Only 1 replica per service is allowed, to minimize resource usage and simplify port forwarding.

## Contributing

### Code Style

We use 2 spaces for indentation, enforced by Ruff.
