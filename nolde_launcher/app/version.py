"""Application version. Keep in sync with packaging metadata."""

__version__ = "0.3.1"
APP_NAME = "Nolde Launcher"
NOLDE_WEBSITE = "https://nolde.pages.dev/"
NOLDE_CATALOG_URL = "https://nolde.pages.dev/data/projects.json"
EARLY_ACCESS = True
VERSION_LABEL = f"Early Access {__version__}" if EARLY_ACCESS else f"Version {__version__}"

# Launcher releases are read from the public GitHub repository.
REPO_OWNER = "NoldeTeam"
REPO_NAME = "nolde-launcher"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
