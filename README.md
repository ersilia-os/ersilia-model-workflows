# Ersilia Model Workflows

Repository containing all the workflows to update and maintain the models in the [Ersilia Model Hub](https://github.com/ersilia-os/ersilia).

## Background

This repository contains reusable workflows that are called by the workflows present in each model repository, as specified in the [eos-template](https://github.com/ersilia-os/eos-template). These workflows are intended to be run at model incorporation time, whenever there is a change in the model (push or PR) and during model maintenance. Note that workflows in the current repository **cannot be run directly from the Actions panel**. This is simply a directory of workflows to be run from each model repository individually.

## Workflows

Below is a high-level summary of the workflows contained in this repository.

| Step | Workflow File               | Description |
|------|-----------------------------|-------------|
| 1    | `test-model-pr.yml`         | Tests the code in the PR branch using the `ersilia test --shallow` command to ensure the new code is not breaking the model. |
| 2    | `test-model-source.yml`     | Tests the model code as available in GitHub using the `ersilia test --shallow` command and updates (a) the model metadata in Airtable, and (b) the README file of the model. |
| 3    | `upload-model-to-s3.yml`    | Uploads the model to the S3 bucket as a persistent copy and updates the Metadata file, Airtable, and README file with the following variables: directory size, environment size, and S3 URL. |
| 4    | `upload-ersilia-pack.yml`   | Builds the Docker images of the model using the FastAPI-based packaging available at [ersilia-pack](https://github.com/ersilia-os/ersilia-pack). Builds both AMD64 and ARM64 images, tagged as dev to avoid overwriting previous working images. |
| 5    | `upload-bentoml.yml`        | If the image cannot be built with ersilia-pack, defaults to BentoML images. Tries AMD64 and ARM64 builds and tags them as dev. |
| 6    | `test-model-image.yml`      | Uses `ersilia test --deep` to test development images of the model and, if successful, retags them as latest in Ersilia's [Docker repository](https://hub.docker.com/orgs/ersiliaos). If only one image (AMD64 or ARM64) is built successfully, only that one is tagged as latest. |
| 7    | `post-model-upload.yml`     | After dev images are retagged as latest, updates the metadata file, README, and Airtable with the Docker URL, image size, and computational performance from `test --deep`. |
| 8    | `build-upload-sif.yml`      | If the AMD64 image passed `test-model-image.yml`, converts it into an Apptainer (Singularity) `.sif` image with [ersilia-apptainer](https://github.com/ersilia-os/ersilia-apptainer), runs a smoke test, uploads it to the `models-sif` S3 bucket, and updates the metadata file, Airtable, and README with the Apptainer URL. Runs after a new release (`retag-release-docker.yml`) and for new models (v1.0.0). |
| 9    | `post-to-slack.yml`         | Posts a comment on Slack when a new issue is opened in the model repository. |
| 10   | `create-new-issue.yml`      | Creates an issue when a model is updated to assign a tester. This workflow is currently unused and will only be activated during intense model refactoring or incorporation periods. |

## GPU Images

A model can declare a GPU install with a `gpu:` key in its `install.yml`. `.github/scripts/resolve_dockerfile.py` prepares the Dockerfile for either image:

```bash
python resolve_dockerfile.py <repo_path> <model_id> [cpu|gpu]   # cpu by default
```

- `cpu` uses the `commands:` of `install.yml` and the `Dockerfile.pip` / `Dockerfile.conda` templates, as before.
- `gpu` uses the `gpu:` list and the `Dockerfile.pip-gpu` / `Dockerfile.conda-gpu` templates from [ersilia](https://github.com/ersilia-os/ersilia), which pack the model with `ersilia_model_pack --device gpu` and set `ERSILIA_DEVICE=gpu`.
- If the model has no `gpu:` key, `gpu` mode writes no Dockerfile and exits with code 0. In GitHub Actions it writes `gpu=true` or `gpu=false` to `GITHUB_OUTPUT`, so a workflow can skip the GPU build.
- `ERSILIA_DOCKERFILES_URL` overrides where the templates are downloaded from (ersilia `master` by default), to test templates before they are merged.

The `Device` metadata field (`CPU`, `GPU`) is accepted by `add_field_to_metadata.py` and placed after `Docker Architecture`.

No workflow calls the `gpu` mode yet: building and publishing `-gpu` images in CI is still to be added.

## License

The code in this repository is available under a GPLv3 License. 

## About Us

The [Ersilia Open Source Initiative](https://ersilia.io) is a Non Profit Organization with the mission is to equip labs, universities and clinics in LMIC with AI/ML tools for infectious disease research.
[Help us](https://www.ersilia.io/donate) achieve our mission!