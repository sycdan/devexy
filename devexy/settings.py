from castaway import config

NOISY = config("DEVEXY_NOISY", default=False, cast=bool)

KUSTOMIZE_ROOT = config("DEVEXY_KUSTOMIZE_ROOT", default="./k8s/")
KUSTOMIZE_OVERLAY = config("DEVEXY_KUSTOMIZE_OVERLAY", default="local")
