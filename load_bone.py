import requests
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass, field

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

session = requests.Session()

@dataclass
class ScriptUpdater:
    file_name_source_code: str = "source_code.py"
    base_url: str = "https://raw.githubusercontent.com/nhphuc2210/jes_cs2/refs/heads/master/"
    offsets_url: str = "https://raw.githubusercontent.com/a2x/cs2-dumper/main/output/offsets.json"
    client_dll_url: str = "https://raw.githubusercontent.com/a2x/cs2-dumper/main/output/client_dll.json"
    current_path: Path = field(default_factory=lambda: Path(__file__).parent)

    # The following attributes are initialized in __post_init__
    local_file: Path = field(init=False)
    venv_path: Path = field(init=False)
    python_executable: Path = field(init=False)
    local_offsets_file: Path = field(init=False)
    local_client_dll_file: Path = field(init=False)

    def __post_init__(self):
        self.local_file = self.current_path / self.file_name_source_code
        self.venv_path = self.current_path / ".env" / "Scripts" / "activate"
        self.python_executable = self.current_path / ".env" / "Scripts" / "python.exe"
        self.local_offsets_file = self.current_path / "offsets.json"
        self.local_client_dll_file = self.current_path / "client_dll.json"

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.file_name_source_code}"

    def download_file(self, url: str, local_file: Path) -> None:
        # logging.info(f"Downloading {url} to {local_file}...")
        response = session.get(url)
        response.raise_for_status()
        local_file.write_text(response.text, encoding="utf-8")
        logging.info(f"Downloaded new version to {local_file}")

    def download_dependencies(self) -> None:
        logging.info("Downloading required dependencies...")
        self.download_file(self.offsets_url, self.local_offsets_file)
        self.download_file(self.client_dll_url, self.local_client_dll_file)

    def get_remote_version(self, url: str) -> str:
        response = session.get(url)
        response.raise_for_status()
        for line in response.text.splitlines():
            if line.strip().startswith("__version__"):
                return line.split("=")[-1].strip().strip('"').strip("'")
        return None

    def get_local_version(self, local_file: Path) -> str:
        if not local_file.exists():
            return None
        for line in local_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("__version__"):
                return line.split("=")[-1].strip().strip('"').strip("'")
        return None

    def trigger_script(self, is_trigger_from_env: bool) -> None:
        logging.info(f"Executing {self.local_file}...")
        try:
            if is_trigger_from_env:
                subprocess.run([str(self.python_executable), str(self.local_file)],
                               check=True, cwd=str(self.current_path))
            else:
                subprocess.run(["python", str(self.local_file)],
                               check=True, cwd=str(self.current_path))
            logging.info(f"Successfully executed {self.local_file}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error while executing {self.local_file}: {e}")

    def run(self, is_trigger_from_env: bool = True) -> None:
        logging.info("Checking for script updates...")

        # Download required JSON dependencies
        self.download_dependencies()

        remote_version = self.get_remote_version(self.url)
        local_version = self.get_local_version(self.local_file)

        if remote_version and (local_version is None or remote_version > local_version):
            logging.info(f"New version found: {remote_version}. Downloading update...")
            self.download_file(self.url, self.local_file)
        else:
            logging.info("You already have the latest version.")

        # Execute the updated script
        self.trigger_script(is_trigger_from_env)


if __name__ == "__main__":
    updater = ScriptUpdater()
    updater.run(is_trigger_from_env=True)




