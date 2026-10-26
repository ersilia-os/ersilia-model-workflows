import sys
import os
import requests

from ersilia_pack.parsers import DockerfileInstallParser, YAMLInstallParser

REPO_PATH  = sys.argv[1]

PY_VERSION_MAP = {
    '3.8': 'py38', 
    '3.9': 'py39',
    '3.10': 'py310',
    '3.11': 'py311',
    '3.12': 'py312'
}

model_id = sys.argv[2]
# cpu (default) uses the 'commands' of install.yml, gpu its 'gpu' section
DEVICE = sys.argv[3] if len(sys.argv) > 3 else "cpu"
# Overridable to test templates that are not on ersilia master yet
TEMPLATES_URL = os.environ.get(
    "ERSILIA_DOCKERFILES_URL",
    "https://raw.githubusercontent.com/ersilia-os/ersilia/master/dockerfiles/dockerize-ersiliapack/model",
)

def resolve_parser(device="cpu"):
    if os.path.exists(os.path.abspath(os.path.join(REPO_PATH, "Dockerfile"))):
        return DockerfileInstallParser(file_dir=REPO_PATH, device=device)
    elif os.path.exists(os.path.join(REPO_PATH, "install.yml")):
        return YAMLInstallParser(file_dir=REPO_PATH, device=device)
    else:
        raise ValueError("No install file found")

def set_gpu_output(has_gpu):
    # Lets the workflow skip the GPU build for models without a gpu section
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"gpu={str(has_gpu).lower()}\n")
    
def resolve_python_version(parser):
    return parser._get_python_version()

def read_dockerfile(parser):
    commands = parser._get_commands()
    has_conda = parser._has_conda(commands)
    flavor = "conda" if has_conda else "pip"
    suffix = "-gpu" if parser.device == "gpu" else ""
    file_url = f"{TEMPLATES_URL}/Dockerfile.{flavor}{suffix}"
    response = requests.get(file_url)
    response.raise_for_status()
    return response.text

def write_version_and_model_id(file_content, python_version):
    python_version = PY_VERSION_MAP[python_version]
    file_content = file_content.replace("eos_identifier", model_id)
    lines = file_content.split("\n")
    lines[0] = lines[0].replace("VERSION", python_version)
    with open(os.path.join(REPO_PATH, "../", "Dockerfile"), "w") as f:
        print("### START OF DOCKERFILE ###\n\n")
        text = "\n".join(lines)
        print(text)
        print("\n")
        print("### END OF DOCKERFILE ###\n")
        f.write(text)

if __name__ == "__main__":
    if DEVICE == "gpu":
        has_gpu = resolve_parser().has_gpu()
        set_gpu_output(has_gpu)
        if not has_gpu:
            print(f"{model_id} has no gpu section in install.yml: no GPU image to build")
            sys.exit(0)
    parser = resolve_parser(DEVICE)
    python_version = resolve_python_version(parser)
    dockerfile = read_dockerfile(parser)
    write_version_and_model_id(dockerfile, python_version)
